import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict
from datetime import datetime

# Indlæs YOLOv8 med tracker
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(0)

# Frame info og linje
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
line_x = frame_width // 2
line_y1, line_y2 = 0, frame_height

# Tællere og log
total_crossings = 0
cross_history = defaultdict(list)  # track_id -> liste af X-positioner
cross_log = []  # Liste af alle krydsninger med timestamp

print(f"Startet kl. {datetime.now().strftime('%d-%m-%y %H:%M:%S')}")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # YOLO tracking
    results = model.track(frame, persist=True, classes=[0], conf=0.5, tracker="bytetrack.yaml")
    
    if results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        ids = results[0].boxes.id.cpu().numpy().astype(int)

        for box, track_id in zip(boxes, ids):
            x1, y1, x2, y2 = map(int, box)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            
            # Gem position i historik
            cross_history[track_id].append(cx)
            if len(cross_history[track_id]) > 10:
                cross_history[track_id].pop(0)
            
            # Tjek krydsning
            if len(cross_history[track_id]) > 1:
                prev_cx = cross_history[track_id][-2]
                current_time = datetime.now().strftime('%H:%M:%S')
                
                # Venstre -> højre ELLER højre -> venstre
                if (prev_cx < line_x and cx >= line_x) or (prev_cx > line_x and cx <= line_x):
                    total_crossings += 1
                    direction = "→" if prev_cx < line_x else "←"
                    
                    # Log krydsning med timestamp
                    timestamp = datetime.now().strftime('%d-%m-%y %H:%M:%S')
                    cross_log.append(f"{timestamp} | ID {track_id} | {direction} | Total: {total_crossings}")
                    
                    print(f"{timestamp} - ID {track_id} krydsede {direction}! Total: {total_crossings}")
            
            # Vis person
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID:{track_id}", (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

    # Tegn linje og info
    cv2.line(frame, (line_x, line_y1), (line_x, line_y2), (0, 0, 255), 3)
    cv2.putText(frame, f"TOTAL: {total_crossings}", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # Vis nuværende tid på video
    current_time = datetime.now().strftime('%H:%M:%S')
    cv2.putText(frame, f"Tid: {current_time}", (10, frame_height-20), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    cv2.imshow("Person Taeller med Timestamp", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# Gem detaljeret log med timestamps
filename = f"krydsninger_{datetime.now().strftime('%d%m%y_%H%M%S')}.txt"
with open(filename, "w", encoding='utf-8') as f:
    f.write(f"=== PERSON TÆLLER LOG ===\n")
    f.write(f"Slutdato: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n")
    f.write(f"Total krydsninger ved døren: {total_crossings}\n")
    f.write(f"Linje position: x={line_x} (frame: {frame_width}x{frame_height})\n")
    f.write("=" * 50 + "\n\n")
    
    for log_entry in cross_log:
        f.write(log_entry + "\n")

print(f"Færdig! {total_crossings} krydsninger gemt i {filename}")