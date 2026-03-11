from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)

DB_FILE = "fablab_people.db"


def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv


@app.route("/")
def index():

    total = query_db(
        "SELECT COUNT(*) FROM people WHERE direction='←'", 
        one=True
    )[0]

    today = query_db(
        "SELECT COUNT(*) FROM people WHERE direction='←' AND date(timestamp)=date('now','localtime')",
        one=True
    )[0]

    events = query_db(
        "SELECT timestamp, track_id, direction, total FROM people ORDER BY id DESC LIMIT 20"
    )

    daily_counts = query_db("""
        SELECT date(timestamp), COUNT(*)
        FROM people
        WHERE direction='←'
        GROUP BY date(timestamp)
        ORDER BY date(timestamp)
    """)

    return render_template(
        "dashboard.html",
        total=total,
        today=today,
        events=events,
        daily_counts=daily_counts
    )


@app.route("/api")
def api():

    total = query_db(
        "SELECT COUNT(*) FROM people WHERE direction='←'",
        one=True
    )[0]

    today = query_db(
        "SELECT COUNT(*) FROM people WHERE direction='←' AND date(timestamp)=date('now','localtime')",
        one=True
    )[0]

    rows = query_db(
        "SELECT timestamp, track_id, direction, total FROM people ORDER BY id DESC LIMIT 20"
    )

    events = []

    for r in rows:
        events.append({
            "timestamp": r[0],
            "track_id": r[1],
            "direction": r[2],
            "total": r[3]
        })

    return jsonify({
        "total": total,
        "today": today,
        "events": events
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
