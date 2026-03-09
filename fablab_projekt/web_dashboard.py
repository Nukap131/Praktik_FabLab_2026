from flask import Flask, render_template, jsonify, send_file
import sqlite3
from datetime import datetime
import csv
import io

app = Flask(__name__)
DB_FILE = "fablab_people.db"

@app.route("/")
def dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM people WHERE direction='←'")
    total_ind = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT timestamp, track_id, direction, total FROM people ORDER BY id DESC LIMIT 20")
    events = cursor.fetchall()
    
    today = datetime.now().strftime('%d-%m-%y')
    cursor.execute("SELECT COUNT(*) FROM people WHERE direction='←' AND timestamp LIKE ?", (f"{today}%",))
    today_total = cursor.fetchone()[0] or 0
    
    conn.close()
    return render_template("dashboard.html", total=total_ind, today=today_total, events=events)

@app.route("/download/csv")
def download_csv():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.execute("SELECT * FROM people ORDER BY id")
    data = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'timestamp', 'track_id', 'direction', 'total'])
    writer.writerows(data)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"fablab_people_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
