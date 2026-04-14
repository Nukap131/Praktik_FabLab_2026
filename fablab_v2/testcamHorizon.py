from picamera2 import Picamera2
from picamera2.devices import IMX500
import time
import cv2

print("FABLAB REVIEW MODE (HORIZONTAL)")

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

# ---------------- HORIZONTAL LINE ----------------

line_y = 240
margin = 50

# ---------------- TRACKING ----------------

tracks = {}
next_track_id = 1

max_distance = 100
track_timeout = 1.2
min_track_hits = 1

def get_zone(cy, top, bottom):
    if cy < top:
        return "TOP"
    if cy > bottom:
        return "BOTTOM"
    return "CENTER"

def append_zone(track, zone):
    if len(track["zones"]) == 0 or track["zones"][-1] != zone:
        track["zones"].append(zone)
    if len(track["zones"]) > 8:
        track["zones"].pop(0)

try:
    while True:
        TOP = line_y - margin
        BOTTOM = line_y + margin

        frame = picam2.capture_array()

        metadata = picam2.capture_metadata()
        outputs = imx500.get_outputs(metadata)

        detections = []

        if outputs is not None:
            boxes, scores, classes, num = outputs

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

        # ryd gamle tracks
        alive_tracks = {}
        for tid, track in tracks.items():
            if now - track["last"] < track_timeout:
                alive_tracks[tid] = track
        tracks = alive_tracks

        updated_tracks = {}
        used_track_ids = set()

        # match
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

        for tid, track in tracks.items():
            if tid not in updated_tracks and now - track["last"] < track_timeout:
                updated_tracks[tid] = track

        tracks = updated_tracks

        # zoneopdatering
        for tid, track in tracks.items():
            zone = get_zone(track["y_smooth"], TOP, BOTTOM)
            append_zone(track, zone)

        # ---------- PREVIEW ----------

        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        else:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # vandrette linjer
        cv2.line(frame, (0, TOP), (frame_width, TOP), (0, 255, 255), 2)
        cv2.line(frame, (0, line_y), (frame_width, line_y), (0, 0, 255), 2)
        cv2.line(frame, (0, BOTTOM), (frame_width, BOTTOM), (0, 255, 255), 2)

        cv2.putText(frame, "TOP", (10, max(TOP - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame, "CENTER", (10, max(line_y - 10, 40)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, "BOTTOM", (10, min(BOTTOM + 25, frame_height - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # detections
        for det in detections:
            cy = det["cy"]
            cv2.circle(frame, (frame_width // 2, cy), 8, (0, 255, 0), -1)

        # tracks
        for tid, track in tracks.items():
            cy = int(track["y_smooth"])
            cx = frame_width // 2 + 40
            cv2.circle(frame, (cx, cy), 6, (255, 0, 0), -1)
            cv2.putText(frame, f"ID {tid}", (cx + 10, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            cv2.putText(frame, f"{track['zones']}", (220, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        cv2.putText(frame, f"line_y: {line_y}", (10, 430),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"margin: {margin}", (10, 455),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, "w/s=line  a/d=margin  q=quit", (240, 455),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("FABLAB REVIEW MODE", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("w"):
            line_y = max(50, line_y - 5)
            print(f"line_y = {line_y}, margin = {margin}")

        elif key == ord("s"):
            line_y = min(frame_height - 50, line_y + 5)
            print(f"line_y = {line_y}, margin = {margin}")

        elif key == ord("a"):
            margin = max(10, margin - 5)
            print(f"line_y = {line_y}, margin = {margin}")

        elif key == ord("d"):
            margin = min(200, margin + 5)
            print(f"line_y = {line_y}, margin = {margin}")

        elif key == ord("q"):
            print(f"BRUG DISSE VÆRDIER I HOVEDKODEN: line_y = {line_y}, margin = {margin}")
            break

        time.sleep(0.01)

except KeyboardInterrupt:
    print("Stopped")

finally:
    picam2.stop()
    cv2.destroyAllWindows()
    print("Review mode closed")
