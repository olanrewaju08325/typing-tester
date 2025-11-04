import os, json, random
from datetime import datetime
from io import BytesIO
from functools import wraps
from flask import Flask, flash, render_template, request, jsonify, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_in_production")

USER_FILE = "users.json"
HISTORY_FILE = "history.json"
ADMIN_FILE = "admin.json"
SENTENCE_FILE = "sentences.json"

# Time limits (seconds)
TIME_LIMITS = {"easy": 30, "medium": 45, "hard": 60}


def load_json(filename):
    if not os.path.exists(filename):
        default = {}
        if filename == ADMIN_FILE:
            default = {"admin": {"password": generate_password_hash("admin123")}}
        elif filename == SENTENCE_FILE:
            default = {"easy": [], "medium": [], "hard": []}
        save_json(filename, default)
    with open(filename, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def home_redirect():
    return redirect(url_for("index")) if "username" in session else redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username", "").strip().lower()
        pwd = request.form.get("password", "")
        users = load_json(USER_FILE)
        admins = load_json(ADMIN_FILE)
        if uname in users and check_password_hash(users[uname]["password"], pwd):
            session["username"] = uname
            return redirect(url_for("index"))
        if uname in admins and check_password_hash(admins[uname]["password"], pwd):
            session["username"] = uname
            session["role"] = "admin"
            return redirect(url_for("leaderboard"))
        return render_template("login.html", error="Invalid login.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/index")
@login_required
def index():
    return render_template("index.html", user=session["username"])


@app.route("/get_sentence/<level>")
@login_required
def get_sentence(level):
    data = load_json(SENTENCE_FILE)
    sentence_list = data.get(level, [])
    sentence = random.choice(sentence_list) if sentence_list else "The quick brown fox jumps over the lazy dog."
    return jsonify({"sentence": sentence, "time_limit": TIME_LIMITS.get(level, 30)})


@app.route("/submit_result", methods=["POST"])
@login_required
def submit_result():
    data = request.get_json() or {}
    username = session["username"]

    typed = data.get("typed", "")
    target = data.get("target", "")
    elapsed = float(data.get("elapsed", 0) or 0)
    level = data.get("level", "easy")

    correct_chars = sum(1 for i in range(min(len(typed), len(target))) if typed[i] == target[i])
    errors = abs(len(typed) - correct_chars)
    accuracy = round((correct_chars / len(target)) * 100, 2) if target else 0
    wpm = round((len(typed) / 5) / (elapsed / 60), 2) if elapsed > 0 else 0

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "wpm": wpm,
        "accuracy": accuracy,
        "level": level,
        "elapsed": round(elapsed, 2),
        "correct": int(correct_chars),
        "errors": int(errors)
    }

    history = load_json(HISTORY_FILE)
    history.setdefault(username, []).append(record)
    save_json(HISTORY_FILE, history)

    return jsonify(record)


@app.route("/leaderboard")
@login_required
def leaderboard():
    history = load_json(HISTORY_FILE)
    all_results = []
    for user, results in history.items():
        for r in results:
            entry = {"user": user}
            entry.update(r)
            all_results.append(entry)
    top = sorted(all_results, key=lambda x: x.get("wpm", 0), reverse=True)[:10]
    return render_template("leaderboard.html", top=top)


@app.route("/history")
@login_required
def history_page():
    return render_template("history.html", user=session["username"])


@app.route("/get_history")
@login_required
def get_history():
    history = load_json(HISTORY_FILE).get(session["username"], [])
    return jsonify(history)


@app.route("/download_report")
@login_required
def download_report():
    username = session["username"]
    history = load_json(HISTORY_FILE).get(username, [])
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, h - 50, f"{username}'s Typing Report")
    y = h - 100
    for r in reversed(history):
        if y < 100:
            c.showPage()
            y = h - 100
        c.drawString(60, y, f"{r.get('timestamp')} | {r.get('level')} | {r.get('wpm')} WPM | {r.get('accuracy')}%")
        y -= 16
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{username}_report.pdf")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # (You can save username and password here)

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

if __name__ == "__main__":
    app.run(debug=True)
