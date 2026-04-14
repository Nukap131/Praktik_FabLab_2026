from picamera2 import Picamera2
from picamera2.devices import IMX500
from datetime import datetime
import sqlite3
import time
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

print("FABLAB PERSON TÆLLER V2.1 HORIZONTAL (IMX500 + MQTT + SQLite + RELÆ)")

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
frame_height = 480
print("Camera ready")

# ---------------- DOOR ZONES ----------------
# Vandret tællelinje

line_y = 240
margin = 50

TOP = line_y - margin
BOTTOM = line_y + margin

# ---------------- COUNTERS ----------------

total_crossings = 0
current_inside = 0

# ---------------- TRACKING ----------------

tracks = {}
next_track_id = 1

max_distance = 100
track_timeout = 1.2
min_track_hits = 3

def get_zone(cy):
    if cy < TOP:
        return "TOP"
    if cy > BOTTOM:
        return "BOTTOM"
    return "CENTER"

def append_zone(track, zone):
    if len(track["zones"]) == 0 or track["zones"][-1] != zone:
        track["zones"].append(zone)
    if len(track["zones"]) > 8:
        track["zones"].pop(0)

def is_in_sequence(zones):
    # TOP -> CENTER -> BOTTOM
    seq = "".join(z[0] for z in zones)   # T, C, B
    return "TCB" in seq or "TTCB" in seq or "TCCB" in seq

def is_out_sequence(zones):
    # BOTTOM -> CENTER -> TOP
    seq = "".join(z[0] for z in zones)   # B, C, T
    return "BCT" in seq or "BBCT" in seq or "BCCT" in seq

# ---------------- LOOP ----------------

try:
    while True:
        metadata = picam2.capture_metadata()
        outputs = imx500.get_outputs(metadata)

        if outputs is None:
            time.sleep(0.01)
            continue

        boxes, scores, classes, num = outputs
        detections = []

        for i in range(int(num)):
            score = float(scores[i])
            cls = int(classes[i])

            if cls != 0:
                continue
            if score < 0.35:
                continue

            box = boxes[i]

            ymin = float(box[0])
            ymax = float(box[2])

            cy = int(((ymin + ymax) / 2) * frame_height)
            detections.append({"cy": cy, "score": score})

        now = time.time()

        # Ryd gamle tracks
        alive_tracks = {}
        for tid, track in tracks.items():
            if now - track["last"] < track_timeout:
                alive_tracks[tid] = track
        tracks = alive_tracks

        updated_tracks = {}
        used_track_ids = set()

        # Match hver detection til nærmeste eksisterende track
        for det in detections:
            cy = det["cy"]
            best_tid = None
            best_dist = None

            for tid, track in tracks.items():
                if tid in used_track_ids:
                    continue

                dist = abs(cy - track["y_smooth"])
                if dist <= max_distance and (best_dist is None or dist < best_dist):
                    best_dist = dist
                    best_tid = tid

            if best_tid is None:
                tid = next_track_id
                next_track_id += 1

                updated_tracks[tid] = {
                    "y": cy,
                    "y_smooth": cy,
                    "zones": [],
                    "last": now,
                    "counted": False,
                    "hits": 1
                }
            else:
                track = tracks[best_tid]
                track["y"] = cy
                track["y_smooth"] = int(0.7 * track["y_smooth"] + 0.3 * cy)
                track["last"] = now
                track["hits"] += 1
                updated_tracks[best_tid] = track
                used_track_ids.add(best_tid)

        # Behold tracks som ikke blev opdateret i dette frame
        for tid, track in tracks.items():
            if tid not in updated_tracks and now - track["last"] < track_timeout:
                updated_tracks[tid] = track

        tracks = updated_tracks

        # Zone-logik
        for tid, track in tracks.items():
            zone = get_zone(track["y_smooth"])
            append_zone(track, zone)

            if track["counted"]:
                continue

            if track["hits"] < min_track_hits:
                continue

            zones = track["zones"]
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # -------- IND --------
            if is_in_sequence(zones):
                total_crossings += 1
                current_inside += 1

                cursor.execute(
                    "INSERT INTO people VALUES(NULL,?,?,?,?)",
                    (timestamp, tid, "IN", total_crossings)
                )
                conn.commit()

                mqtt_client.publish("fablab/person/in", current_inside)
                relay_pulse()

                print("IND | Track", tid, "| Inside:", current_inside, "| Zones:", zones)
                track["counted"] = True
                continue

            # -------- UD --------
            if is_out_sequence(zones):
                current_inside = max(current_inside - 1, 0)

                cursor.execute(
                    "INSERT INTO people VALUES(NULL,?,?,?,?)",
                    (timestamp, tid, "OUT", total_crossings)
                )
                conn.commit()

                mqtt_client.publish("fablab/person/out", current_inside)

                print("UD | Track", tid, "| Inside:", current_inside, "| Zones:", zones)
                track["counted"] = True

        time.sleep(0.01)

except KeyboardInterrupt:
    print("Stopped")

finally:
    picam2.stop()
    conn.close()
    GPIO.cleanup()
    print("Database closed")
