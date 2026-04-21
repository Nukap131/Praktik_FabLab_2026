from picamera2 import Picamera2
from picamera2.devices import IMX500
import cv2
import time

print("FABLAB REVIEW MODE (VERTICAL - RIGHT TO LEFT = IND)")

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

# ---------------- LINE ----------------

line_x = 320
cross_buffer = 8

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

        frame = picam2.capture_array()
        metadata = picam2.capture_metadata()
        outputs = imx500.get_outputs(metadata)

        detections = []
        now = time.time()

        if outputs is not None:
            boxes, scores, classes, num = outputs

            for i in range(int(num)):
                score = float(scores[i])
                cls = int(classes[i])

                if cls != 0:
                    continue
                if score < score_threshold:
                    continue

                box = boxes[i]

                ymin = int(float(box[0]) * frame_height)
                xmin = int(float(box[1]) * frame_width)
                ymax = int(float(box[2]) * frame_height)
                xmax = int(float(box[3]) * frame_width)

                cx = int((xmin + xmax) / 2)
                cy = int((ymin + ymax) / 2)

                detections.append({
                    "cx": cx,
                    "cy": cy,
                    "xmin": xmin,
                    "ymin": ymin,
                    "xmax": xmax,
                    "ymax": ymax,
                    "score": score
                })

        # CLEAN
        alive_tracks = {}
        for tid, track in tracks.items():
            if now - track["last"] < track_timeout:
                alive_tracks[tid] = track
        tracks = alive_tracks

        updated_tracks = {}
        used_track_ids = set()

        # MATCH
        for det in detections:
            cx = det["cx"]

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
                    "hits": 1,
                    "seen_left": False,
                    "seen_right": False,
                    "start_side": None,
                    "counted": False
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

        # REVIEW LOGIC
        for tid, track in tracks.items():
            x = track["x_smooth"]

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
            if (
                not track["counted"]
                and track["hits"] >= min_track_hits
                and track["start_side"] == "RIGHT"
                and track["seen_left"]
            ):
                track["counted"] = True

        # DRAW
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        else:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        cv2.line(frame, (line_x, 0), (line_x, frame_height), (0, 255, 0), 2)
        cv2.line(frame, (left_line, 0), (left_line, frame_height), (255, 255, 0), 1)
        cv2.line(frame, (right_line, 0), (right_line, frame_height), (255, 255, 0), 1)

        cv2.putText(frame, "LEFT", (max(left_line - 50, 10), 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.putText(frame, "COUNT LINE", (max(line_x - 50, 10), 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, "RIGHT", (min(right_line + 10, frame_width - 70), 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        for det in detections:
            cv2.rectangle(
                frame,
                (det["xmin"], det["ymin"]),
                (det["xmax"], det["ymax"]),
                (0, 0, 255),
                2
            )
            cv2.circle(frame, (det["cx"], det["cy"]), 5, (255, 0, 255), -1)

        for tid, track in tracks.items():
            x = int(track["x_smooth"])
            y = frame_height // 2 + 40

            cv2.circle(frame, (x, y), 6, (255, 0, 0), -1)

            cv2.putText(
                frame,
                f'ID:{tid} x:{track["x_smooth"]} hits:{track["hits"]}',
                (20, 420 - (tid % 8) * 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1
            )

            if track["counted"]:
                cv2.putText(
                    frame,
                    "IND",
                    (x + 8, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )

        cv2.putText(frame, f"line_x: {line_x}", (10, 430),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"buffer: {cross_buffer}", (10, 455),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, "a/d=line  w/s=buffer  q=quit", (220, 455),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("FABLAB REVIEW MODE", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("a"):
            line_x = max(40, line_x - 5)
        elif key == ord("d"):
            line_x = min(frame_width - 40, line_x + 5)
        elif key == ord("w"):
            cross_buffer = min(50, cross_buffer + 1)
        elif key == ord("s"):
            cross_buffer = max(2, cross_buffer - 1)
        elif key == ord("q"):
            print(f"BRUG DISSE VÆRDIER I DRIFT-KODEN: line_x = {line_x}, cross_buffer = {cross_buffer}")
            break

        time.sleep(0.01)

except KeyboardInterrupt:
    print("Stopped")

finally:
    picam2.stop()
    cv2.destroyAllWindows()
    print("Review mode closed")
