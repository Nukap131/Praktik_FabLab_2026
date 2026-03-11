from picamera2 import Picamera2
from picamera2.devices import IMX500
from datetime import datetime
import sqlite3
import time

print("FABLAB PERSON TÆLLER V10")

# ---------------- DATABASE ----------------

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

# ---------------- MODEL ----------------

MODEL="/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
imx500 = IMX500(MODEL)

# ---------------- CAMERA ----------------

picam2 = Picamera2()

config = picam2.create_preview_configuration(
 main={"size":(640,480)}
)

picam2.configure(config)
picam2.start()

time.sleep(2)

frame_width = 640

print("Camera ready")

# ---------------- DOOR ZONES ----------------

line_x = 320
margin = 80

LEFT  = line_x - margin
RIGHT = line_x + margin

# ---------------- COUNTERS ----------------

total_crossings = 0
current_inside = 0

# ---------------- TRACKING ----------------

tracks = {}
next_track_id = 1

max_distance = 100
track_timeout = 2

# ---------------- LOOP ----------------

try:

 while True:

  metadata = picam2.capture_metadata()
  outputs = imx500.get_outputs(metadata)

  if outputs is None:
   continue

  boxes,scores,classes,num = outputs

  detections = []

  for i in range(int(num)):

   score=float(scores[i])
   cls=int(classes[i])

   if cls!=0:
    continue

   if score<0.55:
    continue

   box=boxes[i]

   xmin=float(box[1])
   xmax=float(box[3])

   cx=int(((xmin+xmax)/2)*frame_width)

   detections.append(cx)

  now=time.time()

  updated_tracks={}

  # -------- MATCH DETECTIONS --------

  for cx in detections:

   matched=None

   for tid,track in tracks.items():

    if abs(cx-track["x"])<max_distance:
     matched=tid
     break

   if matched is None:

    tid=next_track_id
    next_track_id+=1

    updated_tracks[tid]={
     "x":cx,
     "zones":[],
     "last":now,
     "counted":False
    }

   else:

    track=tracks[matched]

    track["x"]=cx
    track["last"]=now

    updated_tracks[matched]=track

  tracks=updated_tracks

  # -------- ZONE DETECTION --------

  for tid,track in tracks.items():

   cx=track["x"]

   if cx<LEFT:
    zone="LEFT"
   elif cx>RIGHT:
    zone="RIGHT"
   else:
    zone="CENTER"

   if len(track["zones"])==0 or track["zones"][-1]!=zone:
    track["zones"].append(zone)

   if len(track["zones"])>6:
    track["zones"].pop(0)

   if track["counted"]:
    continue

   zones=track["zones"]

   timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')

   # -------- IND --------
   if "LEFT" in zones and "CENTER" in zones and "RIGHT" in zones:

    if zones.index("LEFT") < zones.index("RIGHT"):

     total_crossings+=1
     current_inside+=1

     cursor.execute(
      "INSERT INTO people VALUES(NULL,?,?,?,?)",
      (timestamp,tid,"←",total_crossings)
     )

     conn.commit()

     print("IND | Track",tid,"Total:",total_crossings)

     track["counted"]=True

   # -------- UD --------
   if "RIGHT" in zones and "CENTER" in zones and "LEFT" in zones:

    if zones.index("RIGHT") < zones.index("LEFT"):

     current_inside=max(current_inside-1,0)

     cursor.execute(
      "INSERT INTO people VALUES(NULL,?,?,?,?)",
      (timestamp,tid,"→",total_crossings)
     )

     conn.commit()

     print("UD | Track",tid,"Inside:",current_inside)

     track["counted"]=True

  # -------- CLEAN TRACKS --------

  clean_tracks={}

  for tid,track in tracks.items():

   if now-track["last"]<track_timeout:
    clean_tracks[tid]=track

  tracks=clean_tracks

  time.sleep(0.03)

except KeyboardInterrupt:

 print("Stopped")

finally:

 picam2.stop()
 conn.close()
