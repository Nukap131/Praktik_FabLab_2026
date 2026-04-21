from picamera2 import Picamera2
from picamera2.devices import IMX500
from datetime import datetime
import sqlite3
import time
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

print("FABLAB PERSON TÆLLER V2.4 (VERTICAL - RIGHT TO LEFT = IND)")

# ---------------- RELÆ ----------------

RELAY_PIN = 17
RELAY_PULSE_SEC = 0.2
RELAY_COOLDOWN_SEC = 1.0
last_relay_time = 0.0

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, 0)

def relay_pulse():
    global last_relay_time
    now = time.time()
    if now - last_relay_time < RELAY_COOLDOWN_SEC:
        return

    GPIO.output(RELAY_PIN, 1)
    time.sleep(RELAY_PULSE_SEC)
    GPIO.output(RELAY_PIN, 0)
    last_relay_time = time.time()

# ---------------- DATABASE ----------------

DB_FILE = "/var/lib/grafana/fablab_people.db"

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("PRAGMA journal_mode=WAL;")

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
config = picam2.create_preview_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()

time.sleep(2)

frame_width = 640
print("Camera ready")

# ---------------- LINE ----------------
# IND = RIGHT -> LEFT

line_x = 433
cross_buffer = 8

# ---------------- COUNTERS ----------------

total_crossings = 0
current_inside = 0

# ---------------- TRACKING ----------------

tracks = {}
next_track_id = 1

max_distance = 70
track_timeout = 1.5
min_track_hits = 2
score_threshold = 0.20

# ---------------- LOOP ----------------

try:
    while True:
        left_line = line_x - cross_buffer
        right_line = line_x + cross_buffer

        metadata = picam2.capture_metadata()
        outputs = imx500.get_outputs(metadata)

        if outputs is None:
            time.sleep(0.01)
            continue

        boxes, scores, classes, num = outputs
        detections = []
        now = time.time()

        for i in range(int(num)):
            score = float(scores[i])
            cls = int(classes[i])

            if cls != 0:
                continue
            if score < score_threshold:
                continue

            box = boxes[i]
            xmin = float(box[1])
            xmax = float(box[3])

            cx = int(((xmin + xmax) / 2) * frame_width)
            detections.append(cx)

        # CLEAN TRACKS
        alive_tracks = {}
        for tid, track in tracks.items():
            if now - track["last"] < track_timeout:
                alive_tracks[tid] = track
        tracks = alive_tracks

        updated_tracks = {}
        used_track_ids = set()

        # MATCH
        for cx in detections:
            best_tid = None
            best_dist = None

            for tid, track in tracks.items():
                if tid in used_track_ids:
                    continue

                dist = abs(cx - track["x_smooth"])
                if dist <= max_distance and (best_dist is None or dist < best_dist):
                    best_dist = dist
                    best_tid = tid

            if best_tid is None:
                tid = next_track_id
                next_track_id += 1

                updated_tracks[tid] = {
                    "x": cx,
                    "x_smooth": cx,
                    "last": now,
                    "counted": False,
                    "hits": 1,
                    "seen_left": False,
                    "seen_right": False,
                    "start_side": None
                }
            else:
                track = tracks[best_tid]
                track["x"] = cx
                track["x_smooth"] = int(0.5 * track["x_smooth"] + 0.5 * cx)
                track["last"] = now
                track["hits"] += 1
                updated_tracks[best_tid] = track
                used_track_ids.add(best_tid)

        for tid, track in tracks.items():
            if tid not in updated_tracks and now - track["last"] < track_timeout:
                updated_tracks[tid] = track

        tracks = updated_tracks

        # COUNTING
        for tid, track in tracks.items():

            if track["counted"]:
                continue

            if track["hits"] < min_track_hits:
                continue

            x = track["x_smooth"]
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if track["start_side"] is None:
                if x < left_line:
                    track["start_side"] = "LEFT"
                elif x > right_line:
                    track["start_side"] = "RIGHT"

            if x < left_line:
                track["seen_left"] = True

            if x > right_line:
                track["seen_right"] = True

            # IND = RIGHT -> LEFT
            if track["start_side"] == "RIGHT" and track["seen_left"]:

                total_crossings += 1
                current_inside += 1

                cursor.execute(
                    "INSERT INTO people VALUES(NULL,?,?,?,?)",
                    (timestamp, tid, "IN", total_crossings)
                )
                conn.commit()

                mqtt_client.publish("fablab/person/in", current_inside)
                relay_pulse()

                print("IND | Track", tid, "| x:", x, "| Inside:", current_inside)

                track["counted"] = True

        time.sleep(0.01)

except KeyboardInterrupt:
    print("Stopped")

finally:
    picam2.stop()
    conn.close()
    GPIO.cleanup()
    print("Database closed")
