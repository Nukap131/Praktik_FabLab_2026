import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict

# Indlæs YOLOv8 med tracker
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(0)

# Frame info og linje
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
line_x = frame_width // 2
line_y1, line_y2 = 0, frame_height

# Tællere
total_crossings = 0
cross_history = defaultdict(list)  # track_id -> liste af X-positioner

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
            cx = (x1 + x2) // 2  # Centroid X
            cy = (y1 + y2) // 2
            
            # Gem position i historik (sidste 10 frames)
            cross_history[track_id].append(cx)
            if len(cross_history[track_id]) > 10:
                cross_history[track_id].pop(0)
            
            # Tjek krydsning: Sammenlign nuværende vs forrige position
            if len(cross_history[track_id]) > 1:
                prev_cx = cross_history[track_id][-2]
                
                # Krydsning fra venstre -> højre (eller omvendt)
                if (prev_cx < line_x and cx >= line_x) or (prev_cx > line_x and cx <= line_x):
                    total_crossings += 1
                    direction = "→" if prev_cx < line_x else "←"
                    print(f"ID {track_id} krydsede {direction}! Total: {total_crossings}")
            
            # Vis person
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID:{track_id}", (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

    # Tegn linje og tælling
    cv2.line(frame, (line_x, line_y1), (line_x, line_y2), (0, 0, 255), 3)
    cv2.putText(frame, f"TOTAL: {total_crossings}", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    cv2.imshow("Flere Krydsninger pr. Person", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# Gem detaljeret log
with open("krydsninger_log.txt", "w") as f:
    f.write(f"Total krydsninger om dagen: {total_crossings}\n")
    f.write("Total krydsninger med timestamp kommer her i fremtidige versioner\n")
print(f"Færdig! {total_crossings} krydsninger registreret.")