from picamera2 import Picamera2
import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict
from datetime import datetime
import time
import os
import sqlite3

# Display fix
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["YOLO_VERBOSE"] = "False"
os.environ["ULTRALYTICS_SHOW"] = "False"

print(" FABLAB PERSON TÆLLER v3.1 - LIVE PREVIEW")
print("Tryk 'q' i vinduet eller Ctrl+C for at stoppe")

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
line_x = 320  # Rød linje - gå højre→venstre over = IND

# YOLO
model = YOLO("yolov8n.pt")
model.overrides['verbose'] = False
model.overrides['show'] = False

# ENKELT VINDUE SETUP
# cv2.namedWindow("FABLAB TÆLLER", cv2.WINDOW_NORMAL)
# cv2.resizeWindow("FABLAB TÆLLER", 640, 480)
# cv2.moveWindow("FABLAB TÆLLER", 10, 10)

# Counters
total_crossings = 0
cross_history = defaultdict(list)
last_cross_time = {}
cooldown_seconds = 1.5

print(f" Kamera OK | Linje x={line_x} | Database: {DB_FILE}")
print(" Se dig selv i 'FABLAB TÆLLER' vindue!")
print("-" * 50)

start_time = time.time()

try:
    while True:
        # Capture
        frame = picam2.capture_array()
        
        # Color fix
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        else:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Spejl
        frame = cv2.flip(frame, 1)
        
        # YOLO
        results = model.track(frame, persist=True, classes=[0], conf=0.35,
                            tracker="bytetrack.yaml", verbose=False)
        
        active_tracks = 0
        if results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)
            active_tracks = len(track_ids)

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                cx = (x1 + x2) // 2
                
                # Track positioner
                cross_history[track_id].append(cx)
                if len(cross_history[track_id]) > 10:
                    cross_history[track_id].pop(0)
                
                # Krydsning?
                if len(cross_history[track_id]) > 1:
                    prev_cx = cross_history[track_id][-2]
                    now = datetime.now()
                    
                    # IND: højre→venstre
                    if prev_cx > line_x and cx <= line_x:
                        direction = "←"
                        last_time = last_cross_time.get(track_id)
                        too_soon = last_time and (now - last_time).total_seconds() < cooldown_seconds
                        
                        if not too_soon:
                            last_cross_time[track_id] = now
                            total_crossings += 1
                            timestamp = now.strftime('%d-%m-%y %H:%M:%S')
                            
                            cursor.execute("INSERT INTO people VALUES (NULL, ?, ?, ?, ?)",
                                         (timestamp, track_id, direction, total_crossings))
                            conn.commit()
                            print(f" IND! {timestamp} | ID{track_id} | Total: {total_crossings}")
                
                # Bokse på skærm
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"ID:{track_id}", (x1, y1-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # RØD LINJE + INFO
        cv2.line(frame, (line_x, 0), (line_x, frame_height), (0, 0, 255), 3)
        cv2.putText(frame, f"TOTAL IND: {total_crossings}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(frame, f"Tracks: {active_tracks}", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(frame, f"Tid: {datetime.now().strftime('%H:%M:%S')}", 
                   (10, frame_height-20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # VIS ENKELT VINDUE
       # cv2.imshow("FABLAB TÆLLER", frame)
        
        # Status
        if time.time() - start_time > 5:
            print(f" {total_crossings} ind | {active_tracks} tracks")
            start_time = time.time()
        
        # Stop
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\n Stoppet")

finally:
    picam2.stop()
    cv2.destroyWindow("FABLAB TÆLLER")  # Kun ÉT vindue
    cv2.destroyAllWindows()
    conn.close()
    print(f"\n FÆRDIG! {total_crossings} personer | {DB_FILE}")
