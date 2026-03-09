from flask import Flask, render_template, jsonify, send_file
import sqlite3, io, csv, json
from datetime import datetime

app = Flask(__name__)
DB_FILE = "fablab_people.db"

# --- Dashboard ---
@app.route("/")
def dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Total IND
    cursor.execute("SELECT COUNT(*) FROM people WHERE direction='←'")
    total_ind = cursor.fetchone()[0] or 0

    # Seneste 20 events
    cursor.execute("SELECT timestamp, track_id, direction, total FROM people ORDER BY id DESC LIMIT 20")
    events = cursor.fetchall()

    # Antal i dag
    today_iso = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM people WHERE direction='←' AND timestamp LIKE ?", (f"{today_iso}%",))
    today_total = cursor.fetchone()[0] or 0

    # Daglig statistik til graf (understøtter både gamle og nye timestamps)
    # ISO-timestamps: YYYY-MM-DD → dd-mm-yy
    cursor.execute("""
        SELECT 
            CASE 
                WHEN LENGTH(timestamp)=19 THEN substr(timestamp, 9, 2) || '-' || substr(timestamp, 6, 2) || '-' || substr(timestamp, 3, 2)
                ELSE substr(timestamp, 1, 8)
            END as day,
            COUNT(*) 
        FROM people 
        WHERE direction='←'
        GROUP BY day
        ORDER BY day ASC
    """)
    daily_counts = cursor.fetchall()
    conn.close()

    return render_template("dashboard.html",
                           total=total_ind,
                           today=today_total,
                           events=events,
                           daily_counts=daily_counts)

# --- Live API ---
@app.route("/api")
def api():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM people WHERE direction='←'")
    total_ind = cursor.fetchone()[0] or 0
    cursor.execute("SELECT timestamp, track_id, direction, total FROM people ORDER BY id DESC LIMIT 20")
    events = cursor.fetchall()
    conn.close()

    return jsonify({
        "total": total_ind,
        "events": [{"timestamp": e[0], "track_id": e[1], "direction": e[2], "total": e[3]} for e in events]
    })

# --- Download CSV ---
@app.route("/download/csv")
def download_csv():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.execute("SELECT * FROM people ORDER BY id")
    data = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','timestamp','track_id','direction','total'])
    writer.writerows(data)

    return send_file(io.BytesIO(output.getvalue().encode('utf-8')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f"fablab_people_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")

# --- Download JSON ---
@app.route("/download/json")
def download_json():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.execute("SELECT * FROM people ORDER BY id")
    data = cursor.fetchall()
    conn.close()

    return send_file(io.BytesIO(json.dumps([
        {"id": row[0], "timestamp": row[1], "track_id": row[2], "direction": row[3], "total": row[4]}
        for row in data], indent=2).encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f"fablab_people_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
