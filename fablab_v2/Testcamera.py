from picamera2 import Picamera2
from picamera2.devices import IMX500
from datetime import datetime
import sqlite3
import time
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
import cv2

print("FABLAB PERSON TÆLLER V2 (IMX500 + MQTT + SQLite + RELÆ + PREVIEW)")

# ---------------- RELÆ ----------------

RELAY_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, 0)

def relay_pulse():
    GPIO.output(RELAY_PIN, 1)
    time.sleep(0.2)
    GPIO.output(RELAY_PIN, 0)

# ---------------- DATABASE ----------------

DB_FILE = "/var/lib/grafana/fablab_people.db"

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS people (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 timestamp TEXT,
 track_id INTEGER,
 direction TEXT,
 total INTEGER
)
""")

conn.commit()

# ---------------- MQTT ----------------

mqtt_client = mqtt.Client()
mqtt_client.connect("localhost", 1883)
mqtt_client.loop_start()

print("MQTT connected")

# ---------------- MODEL ----------------

MODEL = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
imx500 = IMX500(MODEL)

# ---------------- CAMERA ----------------

picam2 = Picamera2()

config = picam2.create_preview_configuration(
    main={"size": (640, 480)}
)

picam2.configure(config)
picam2.start()

time.sleep(2)

frame_width = 640
frame_height = 480
SHOW_PREVIEW = True

print("Camera ready")

# ---------------- DOOR ZONES ----------------

line_x = 320
margin = 40

LEFT = line_x - margin
RIGHT = line_x + margin

# ---------------- COUNTERS ----------------

total_crossings = 0
current_inside = 0

# ---------------- TRACKING ----------------

tracks = {}
next_track_id = 1

max_distance = 160
track_timeout = 2

# ---------------- LOOP ----------------

try:

    while True:

        frame = None
        if SHOW_PREVIEW:
            frame = picam2.capture_array()

        metadata = picam2.capture_metadata()
        outputs = imx500.get_outputs(metadata)

        if outputs is None:
            if SHOW_PREVIEW and frame is not None:
                if frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                else:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                cv2.line(frame, (line_x, 0), (line_x, frame_height), (0, 0, 255), 2)
                cv2.line(frame, (LEFT, 0), (LEFT, frame_height), (0, 255, 255), 2)
                cv2.line(frame, (RIGHT, 0), (RIGHT, frame_height), (0, 255, 255), 2)

                cv2.putText(frame, "LEFT", (LEFT - 60, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, "CENTER", (line_x - 45, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, "RIGHT", (RIGHT + 10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                cv2.putText(frame, f"Inside: {current_inside}", (10, 460),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"Total: {total_crossings}", (180, 460),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                cv2.imshow("FABLAB Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(0.01)
            continue

        boxes, scores, classes, num = outputs

        detections = []

        for i in range(int(num)):

            score = float(scores[i])
            cls = int(classes[i])

            if cls != 0:
                continue

            if score < 0.40:
                continue

            box = boxes[i]

            xmin = float(box[1])
            xmax = float(box[3])

            cx = int(((xmin + xmax) / 2) * frame_width)

            detections.append(cx)

        print("Detections:", detections)

        now = time.time()

        updated_tracks = {}

        # MATCH

        for cx in detections:

            matched = None

            for tid, track in tracks.items():

                if abs(cx - track["x"]) < max_distance:
                    matched = tid
                    break

            if matched is None:

                tid = next_track_id
                next_track_id += 1

                updated_tracks[tid] = {
                    "x": cx,
                    "zones": [],
                    "last": now,
                    "counted": False
                }

            else:

                track = tracks[matched]
                track["x"] = cx
                track["last"] = now
                updated_tracks[matched] = track

        tracks = updated_tracks

        # ZONES

        for tid, track in tracks.items():

            cx = track["x"]

            if cx < LEFT:
                zone = "LEFT"
            elif cx > RIGHT:
                zone = "RIGHT"
            else:
                zone = "CENTER"

            if len(track["zones"]) == 0 or track["zones"][-1] != zone:
                track["zones"].append(zone)

            if len(track["zones"]) > 6:
                track["zones"].pop(0)

            if track["counted"]:
                continue

            zones = track["zones"]

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # -------- IND --------

            if "LEFT" in zones and "CENTER" in zones and "RIGHT" in zones:

                if zones.index("LEFT") < zones.index("RIGHT"):

                    total_crossings += 1
                    current_inside += 1

                    cursor.execute(
                        "INSERT INTO people VALUES(NULL,?,?,?,?)",
                        (timestamp, tid, "IN", total_crossings)
                    )
                    conn.commit()

                    mqtt_client.publish("fablab/person/in", current_inside)

                    relay_pulse()

                    print("IND | Track", tid, "Inside:", current_inside)

                    track["counted"] = True

            # -------- UD --------

            if "RIGHT" in zones and "CENTER" in zones and "LEFT" in zones:

                if zones.index("RIGHT") < zones.index("LEFT"):

                    current_inside = max(current_inside - 1, 0)

                    cursor.execute(
                        "INSERT INTO people VALUES(NULL,?,?,?,?)",
                        (timestamp, tid, "OUT", total_crossings)
                    )
                    conn.commit()

                    mqtt_client.publish("fablab/person/out", current_inside)

                    print("UD | Track", tid, "Inside:", current_inside)

                    track["counted"] = True

        # CLEAN

        clean_tracks = {}

        for tid, track in tracks.items():
            if now - track["last"] < track_timeout:
                clean_tracks[tid] = track

        tracks = clean_tracks

        # ---------------- PREVIEW ----------------

        if SHOW_PREVIEW and frame is not None:

            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            else:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            # Linjer
            cv2.line(frame, (line_x, 0), (line_x, frame_height), (0, 0, 255), 2)
            cv2.line(frame, (LEFT, 0), (LEFT, frame_height), (0, 255, 255), 2)
            cv2.line(frame, (RIGHT, 0), (RIGHT, frame_height), (0, 255, 255), 2)

            # Tekst
            cv2.putText(frame, "LEFT", (LEFT - 60, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, "CENTER", (line_x - 45, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, "RIGHT", (RIGHT + 10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # Grønne detections
            for cx in detections:
                cv2.circle(frame, (cx, frame_height // 2), 8, (0, 255, 0), -1)

            # Blå tracks
            for tid, track in tracks.items():
                cx = int(track["x"])
                cy = frame_height // 2 + 40
                cv2.circle(frame, (cx, cy), 6, (255, 0, 0), -1)
                cv2.putText(frame, f"ID {tid}", (cx + 8, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

            # Status
            cv2.putText(frame, f"Inside: {current_inside}", (10, 460),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Total: {total_crossings}", (180, 460),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("FABLAB Preview", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        time.sleep(0.01)

except KeyboardInterrupt:

    print("Stopped")

finally:

    picam2.stop()
    conn.close()
    GPIO.cleanup()
    cv2.destroyAllWindows()
    print("Database closed")
