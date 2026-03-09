from picamera2 import Picamera2
import cv2
from ultralytics import YOLO
from collections import defaultdict
from datetime import datetime
import time
import os
import sqlite3

# Headless / miljøvariabler
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["YOLO_VERBOSE"] = "False"
os.environ["ULTRALYTICS_SHOW"] = "False"

print("FABLAB PERSON TÆLLER v4.2 - HEADLESS")

# Database
DB_FILE = "fablab_people.db"
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

# Kamera
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()
time.sleep(2)

frame_width, frame_height = 640, 480
line_x = 320  # linje midt i billedet

# YOLO model
model = YOLO("yolov8n.pt")
model.overrides['verbose'] = False
model.overrides['show'] = False

# Counters
total_crossings = 0
current_inside = 0
cross_history = defaultdict(list)
last_cross_time = {}
cooldown_seconds = 1.5

print(f"Kamera OK | Linje x={line_x} | Database: {DB_FILE}")
print("-"*50)

try:
    while True:
        frame = picam2.capture_array()

        # Farvefix
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        else:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        frame = cv2.flip(frame, 1)  # Spejl

        # YOLO tracking
        results = model.track(frame, persist=True, classes=[0], conf=0.35, tracker="bytetrack.yaml", verbose=False)
        if results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                cx = (x1 + x2)//2

                # Track historik
                cross_history[track_id].append(cx)
                if len(cross_history[track_id]) > 10:
                    cross_history[track_id].pop(0)

                # Krydsning
                if len(cross_history[track_id]) > 1:
                    prev_cx = cross_history[track_id][-2]
                    now = datetime.now()
                    last_time = last_cross_time.get(track_id)
                    too_soon = last_time and (now - last_time).total_seconds() < cooldown_seconds

                    # IND: højre→venstre
                    if prev_cx > line_x and cx <= line_x and not too_soon:
                        direction = "←"
                        last_cross_time[track_id] = now
                        total_crossings += 1
                        current_inside += 1
                        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')  # ISO-format
                        cursor.execute("INSERT INTO people VALUES (NULL, ?, ?, ?, ?)",
                                       (timestamp, track_id, direction, total_crossings))
                        conn.commit()
                        print(f"IND! {timestamp} | ID{track_id} | Total: {total_crossings} | Nu i rummet: {current_inside}")

                    # UD: venstre→højre
                    elif prev_cx < line_x and cx >= line_x and not too_soon:
                        direction = "→"
                        last_cross_time[track_id] = now
                        current_inside = max(current_inside - 1, 0)
                        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')  # ISO-format
                        cursor.execute("INSERT INTO people VALUES (NULL, ?, ?, ?, ?)",
                                       (timestamp, track_id, direction, total_crossings))
                        conn.commit()
                        print(f"UD! {timestamp} | ID{track_id} | Total: {total_crossings} | Nu i rummet: {current_inside}")

except KeyboardInterrupt:
    print("\n Stoppet manuelt")

finally:
    picam2.stop()
    conn.close()
    print(f"FÆRDIG! Total personer: {total_crossings}")
