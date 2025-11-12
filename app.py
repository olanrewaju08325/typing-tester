# app.py – TypeForge (merged, non-destructive, multiplayer rooms + promotions)
# -----------------------------------------------------
import os
import json
import time
import random
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from markupsafe import escape
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request as flask_request  # used for SocketIO sid
from functools import wraps

# -----------------------------------------------------
# Paths & Configuration
# -----------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SENTENCES_FILE = os.path.join(DATA_DIR, "sentences.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
LEVELS_FILE = os.path.join(DATA_DIR, "levels.json")

ADMIN_USERNAME = "abdulmuiz"
ADMIN_PASSWORD = "muizudeen"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "typeforge_dev_secret_key")

# allow CORS for socket clients during development
socketio = SocketIO(app, cors_allowed_origins="*")


# -------------------------
# Safer Socket.IO multiplayer handlers (inserted by patch)
# -------------------------

# In-memory room state (for small deployments). For production, use persistent storage.
_rooms = {}  # rooms[room_id] = {'sentence': str, 'started_at': ts, 'finished': bool, 'players': {username: {...}}}

def _normalize_for_compare(s):
    if not isinstance(s, str):
        return ""
    return s.strip().replace('\u2013','-').replace('\u2014','-').replace('\u2026','...').replace('“','"').replace('”','"').replace("‘","'").replace("’","'")

def _compute_accuracy(target, typed):
    t_words = [w for w in target.strip().split() if w]
    i_words = [w for w in typed.strip().split() if w]
    if not t_words:
        return 0
    correct = 0
    for i in range(min(len(t_words), len(i_words))):
        if t_words[i] == i_words[i]:
            correct += 1
    return round((correct / len(t_words)) * 100)

@socketio.on("join_room")
def _handle_join(data):
    room = data.get("room")
    username = data.get("username", "anonymous").strip()[:32]
    if not room:
        return
    username = escape(username)
    join_room(room)
    r = _rooms.setdefault(room, {"sentence": None, "started_at": None, "finished": False, "players": {}})
    r["players"].setdefault(username, {"progress": 0, "connected": True, "last_update": time.time()})
    # broadcast current players progress to the room
    emit("update_progress", {"players": {u: r["players"][u]["progress"] for u in r["players"]}}, room=room) #type: ignore

@socketio.on("new_sentence_request")
def _handle_new_sentence_request(data):
    room = data.get("room")
    sentence = data.get("sentence")
    if not room or not sentence:
        return
    r = _rooms.setdefault(room, {"players": {}})
    r["sentence"] = sentence
    # server time start slightly in future to allow sync on clients
    r["started_at"] = time.time() + 1.5
    r["finished"] = False
    emit("new_sentence", {"sentence": sentence, "start_at": r["started_at"]}, room=room) #type: ignore

@socketio.on("progress_update")
def _handle_progress_update(data):
    room = data.get("room")
    username = data.get("username")
    progress = data.get("progress")
    if not room or room not in _rooms or not username:
        return
    try:
        progress = float(progress)
    except:
        return
    # clamp progress and basic anti-cheat
    progress = max(0.0, min(100.0, progress))
    player = _rooms[room]["players"].setdefault(username, {"progress": 0, "connected": True, "last_update": time.time()})
    # ignore impossible drops
    if progress < player.get("progress", 0) - 25:
        return
    player["progress"] = progress
    player["last_update"] = time.time()
    emit("update_progress", {"players": {u: _rooms[room]["players"][u]["progress"] for u in _rooms[room]["players"]}}, room=room) #type: ignore

@socketio.on("race_finished")
def _handle_race_finished(data):
    room = data.get("room")
    username = data.get("username")
    typed_text = data.get("text", "")
    client_time = data.get("time")
    if not room or room not in _rooms or not username:
        return
    r = _rooms[room]
    if r.get("finished"):
        emit("late_finish", {"username": username}, room=room) #type: ignore
        return
    server_sentence = r.get("sentence") or ""
    typed_norm = _normalize_for_compare(typed_text)
    sentence_norm = _normalize_for_compare(server_sentence)
    accuracy = _compute_accuracy(sentence_norm, typed_norm)
    started_at = r.get("started_at") or time.time()
    finish_time = time.time()
    duration = finish_time - started_at
    # sanity-check client_time
    if isinstance(client_time, (int, float)):
        if abs(client_time - duration) < 5.0:
            duration = client_time
    word_count = len(typed_text.strip().split())
    minutes = max(1/60, duration / 60.0)
    wpm = round(word_count / minutes) if minutes>0 else 0
    r["finished"] = True
    r["winner"] = username
    r["result"] = {"username": username, "wpm": wpm, "accuracy": accuracy, "time": duration}
    emit("race_finished", {"room": room, "username": username, "wpm": wpm, "accuracy": accuracy, "time": duration, "winner": username}, room=room) #type: ignore

@socketio.on("disconnect")
def _handle_disconnect():
    # optional: we could track socket->username mapping for cleanup, omitted for brevity
    return
# -------------------------

players = {}  # sid -> {name, username, level, wpm, progress}

# -----------------------------------------------------
# Helpers: JSON utils
# -----------------------------------------------------
import json, os

def load_data(filename):
    """Safely load a JSON file and return its contents or an empty list."""
    try:
        path = os.path.join("data", filename)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load {filename}: {e}")
        return []

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path, default=None):
    ensure_data_dir()
    if not os.path.exists(path):
        # create file with default content (non-destructive when file missing)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default or {}, f, indent=2)
        return default or {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            # if corrupted, return default but don't overwrite immediately
            return default or {}

def save_json(path, obj):
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)

# -----------------------------------------------------
# Levels & sentences
# -----------------------------------------------------
def load_levels():
    return load_json(LEVELS_FILE, {})

def get_level_sentences(level):
    levels = load_levels()
    return levels.get(level, {}).get("sentences", [])

def pick_level_sentence(level):
    sents = get_level_sentences(level) or []
    return random.choice(sents) if sents else None

def load_sentences_all():
    return load_json(SENTENCES_FILE, {
        "easy": [],
        "medium": [],
        "hard": [],
        "expert": []
    })

# -----------------------------------------------------
# User helpers
# -----------------------------------------------------
def current_user():
    uname = session.get("username")
    if not uname:
        return None
    users = load_json(USERS_FILE, {})
    meta = users.get(uname)
    if not meta:
        return None
    # ensure defaults
    meta.setdefault("role", "user")
    meta.setdefault("plan", "free")
    meta.setdefault("level", "beginner")
    meta.setdefault("beaten", {})  # beaten[level] = [usernames]
    return {"username": uname, "role": meta.get("role"), "plan": meta.get("plan"), "level": meta.get("level")}

def save_user_data(username, data):
    users = load_json(USERS_FILE, {})
    users[username] = data
    save_json(USERS_FILE, users)

def promote_user_if_eligible(username, last_wpm):
    """Check if user meets thresholds to promote; if premium user reaches > beginner, require premium_plus payment."""
    users = load_json(USERS_FILE, {})
    user = users.get(username)
    if not user:
        return False, None
    current_level = user.get("level", "beginner")
    levels = load_levels()
    lvl_meta = levels.get(current_level)
    if not lvl_meta:
        return False, None
    # check beaten opponents count at this level
    beaten = user.get("beaten", {}).get(current_level, [])
    unique_beaten = len(set(beaten or []))
    wins_needed = lvl_meta.get("requirement", {}).get("wins_needed", 3)
    min_wpm = lvl_meta.get("requirement", {}).get("min_wpm", 30)

    # promotion requires both unique beaten count >= wins_needed AND last_wpm >= min_wpm
    if unique_beaten >= wins_needed and last_wpm >= min_wpm:
        next_level = lvl_meta.get("next")
        if not next_level:
            return False, None
        # If user is premium (not plus) and next_level != beginner, require upgrade
        if user.get("plan") == "premium" and next_level != "beginner":
            # mark pending upgrade (admin action or payment)
            user.setdefault("pending_upgrade_to", "premium_plus")
            user.setdefault("pending_amount", 1000)
            user.setdefault("pending_status", "pending")
            save_user_data(username, user)
            return False, "premium_needed"
        # promote
        user["level"] = next_level
        # reset beaten list for new level
        user.setdefault("beaten", {})
        user["beaten"][next_level] = []
        save_user_data(username, user)
        return True, next_level
    return False, None

def record_win_and_opponents(winner_username, opponent_usernames, wpm):
    """Record that winner_username beat the listed opponent_usernames at their current level and attempt promotion."""
    users = load_json(USERS_FILE, {})
    user = users.get(winner_username)
    if not user:
        return False, None
    level = user.get("level", "beginner")
    beaten = user.setdefault("beaten", {}).setdefault(level, [])
    for opp in opponent_usernames:
        if opp not in beaten and opp != winner_username:
            beaten.append(opp)
    users[winner_username] = user
    save_json(USERS_FILE, users)
    return promote_user_if_eligible(winner_username, wpm)

# -----------------------------------------------------
# Initial data create if not present
# -----------------------------------------------------
ensure_data_dir()
# ensure there's an admin user saved (non-destructive)
load_json(USERS_FILE, {ADMIN_USERNAME: {"password": ADMIN_PASSWORD, "role": "admin", "plan": "premium_plus", "level": "expert"}})
load_json(HISTORY_FILE, {})
# create default sentences file if missing (single-player)
load_json(SENTENCES_FILE, {"easy": [], "medium": [], "hard": [], "expert": []})
# ensure levels file exists (user must place the levels.json from earlier)
if not os.path.exists(LEVELS_FILE):
    # write a minimal placeholder so server won't crash; recommend replacing with the full file
    save_json(LEVELS_FILE, {
        "beginner": {"sentences": [], "requirement": {"wins_needed": 3, "min_wpm": 30}, "next": "intermediate", "range": [0, 29], "reward": "", "description": ""},
        "intermediate": {"sentences": [], "requirement": {"wins_needed": 3, "min_wpm": 50}, "next": "advanced", "range": [30, 49], "reward": "", "description": ""},
        "advanced": {"sentences": [], "requirement": {"wins_needed": 3, "min_wpm": 60}, "next": "expert", "range": [50, 84], "reward": "", "description": ""},
        "expert": {"sentences": [], "requirement": {"wins_needed": 4, "min_wpm": 85}, "next": None, "range": [85, 9999], "reward": "", "description": ""}
    })
# ============================================================
# ✅ LOGIN REQUIRED DECORATOR (for routes like /save_result)
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = current_user()
        if not user:
            # If this is an API/AJAX route, return JSON 401 to avoid the frontend receiving HTML (causes "Unexpected token '<'")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "login required"}), 401
            flash("You must log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# -----------------------------------------------------
# Context for templates
# -----------------------------------------------------
@app.context_processor
def inject_user():
    u = current_user()
    # make sure templates can access both username and plan easily
    return {"current_user": u, "app_name": "TypeForge", "maker": "Olanrewaju Halimot Adeola"}

# -----------------------------------------------------
# Routes (single-player & admin)
# -----------------------------------------------------
@app.route("/")
def index():
    user = current_user()
    history = load_json(HISTORY_FILE, {})
    runs = history.get(user["username"], [])[-10:] if user else []
    sentences = load_sentences_all()
    return render_template("index.html", sentences=sentences, runs=runs)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")
        users = load_json(USERS_FILE, {})
        u = users.get(uname)
        if u and u.get("password") == pwd:
            session["username"] = uname
            flash(f"Welcome back, {uname}!", "success")
            if u.get("role") == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("index"))
        flash("Invalid username or password", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")
        # optional plan field in admin form
        plan_form = request.form.get("plan", "free")
        if not uname or not pwd:
            flash("Enter username and password", "error")
            return redirect(url_for("register"))
        users = load_json(USERS_FILE, {})
        if uname in users:
            flash("User already exists", "error")
            return redirect(url_for("register"))
        # If an admin is creating the user, allow plan override
        creator = current_user()
        if creator and creator.get("role") == "admin":
            plan_to_set = plan_form
        else:
            plan_to_set = "free"
        users[uname] = {"password": pwd, "role": "user", "plan": plan_to_set, "level": "beginner", "beaten": {}}
        save_json(USERS_FILE, users)
        flash("Registered successfully! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/admin_dashboard")
def admin_dashboard():
    user = current_user()
    if not user or user.get("role") != "admin":
        flash("Admin access required", "error")
        return redirect(url_for("login"))
    users = load_json(USERS_FILE, {})
    history = load_json(HISTORY_FILE, {})
    # For payment table optional rendering: collect pending requests
    pending = []
    for uname, u in users.items():
        if u.get("pending_upgrade_to"):
            pending.append({
                "username": uname,
                "plan": u.get("pending_upgrade_to"),
                "amount": u.get("pending_amount", 1000),
                "status": u.get("pending_status", "pending")
            })
    return render_template("admin_dashboard.html", users=users, history=history, pending=pending)
# ============================================================
# ✅ LIVE JSON ENDPOINTS for AJAX updates (Leaderboard & History)
# ============================================================

@app.route("/api/leaderboard")
def api_leaderboard():
    """
    Returns the leaderboard as JSON for live updates.
    """
    try:
        # Load from the same file your /leaderboard route uses
        history = load_json(HISTORY_FILE, {})
        scores = []
        for uname, runs in history.items():
            # runs may be stored in different formats; ensure type-safety
            if not runs or not isinstance(runs, list):
                continue
            wpms = []
            for r in runs:
                try:
                    wpms.append(int(float(r.get("wpm", 0))))
                except Exception:
                    continue
            if not wpms:
                continue
            best = max(wpms)
            # pick last run's difficulty/accuracy if available, else safe defaults
            last = runs[-1] if runs else {}
            level = last.get("difficulty", last.get("level", "N/A"))
            accuracy = last.get("accuracy", 0)
            scores.append({
                "username": uname,
                "level": level,
                "wpm": best,
                "accuracy": accuracy
            })
        scores = sorted(scores, key=lambda x: x["wpm"], reverse=True)
        return jsonify(scores)
    except Exception as e:
        print(f"[ERROR] /api/leaderboard → {e}")
        return jsonify([]), 500



@app.route("/history")
def history_view():
    user = current_user()
    if not user:
        flash("Please log in to view history", "error")
        return redirect(url_for("login"))

    history = load_json(HISTORY_FILE, {})
    runs = history.get(user["username"], [])

    # Sort runs by timestamp descending (if timestamp key present)
    runs = sorted(runs, key=lambda x: x.get("timestamp", x.get("date", "")), reverse=True)

    return render_template("history.html", runs=runs)
@app.route("/leaderboard")
def leaderboard():
    leaderboard_data = load_data("leaderboard.json") or []
    return render_template("leaderboard.html", leaderboard=leaderboard_data)


@app.route("/api/history")
def api_history():
    """
    Returns the logged-in user's typing history as JSON.
    """
    user = current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401

    try:
        history = load_json(HISTORY_FILE, {})
        runs = history.get(user["username"], [])
        return jsonify(runs)
    except Exception as e:
        print(f"[ERROR] /api/history → {e}")
        return jsonify([]), 500

@app.route("/upgrade", methods=["GET", "POST"])
def upgrade():
    user = current_user()
    if not user:
        flash("Login to upgrade", "error")
        return redirect(url_for("login"))

    plans = [
        {"name": "Premium", "price": "₦2000", "features": ["Access to expert difficulty in single-player", "Better charts"]},
        {"name": "Premium Plus", "price": "₦1000", "features": ["Full multiplayer progression access", "Expert multiplayer pool"]}  # note: pricing per your UI
    ]

    if request.method == "POST":
        plan = request.form.get("plan", "premium")
        users = load_json(USERS_FILE, {})
        if user["username"] in users:
            users[user["username"]]["plan"] = plan
            # if they bought premium_plus manually, clear pending flag
            users[user["username"]].pop("pending_upgrade_to", None)
            users[user["username"]].pop("pending_amount", None)
            users[user["username"]].pop("pending_status", None)
            save_json(USERS_FILE, users)
            flash(f"Plan updated to {plan}. You’ll get full access once payment is confirmed.", "success")
        return redirect(url_for("index"))

    return render_template("upgrade.html", plans=plans)


# ✅ FIXED SENTENCES ROUTES (connects properly to data/sentences.json)
@app.route("/api/sentences/all")
def api_sentences_all():
    """Return all sentences grouped by difficulty for preloading."""
    sentences_file = os.path.join("data", "sentences.json")
    if not os.path.exists(sentences_file):
        return jsonify({"error": "missing_file"}), 404
    try:
        with open(sentences_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("[API] Sentences loaded successfully from data/sentences.json")
        return jsonify(data)
    except Exception as e:
        print("[API ERROR] Failed to load sentences:", e)
        return jsonify({"error": "load_failed", "message": str(e)}), 500


@app.route("/api/sentences", methods=["GET"])
def api_sentences():
    """Returns one random sentence by difficulty level."""
    difficulty = request.args.get("difficulty", "easy").lower()
    sentences_file = os.path.join("data", "sentences.json")

    if not os.path.exists(sentences_file):
        print("[WARN] sentences.json missing in data/")
        return jsonify({"sentence": "The programmer eats at school.", "offline": True})

    try:
        with open(sentences_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        sents = data.get(difficulty) or []
        if not sents:
            print(f"[WARN] No sentences found for {difficulty}")
            return jsonify({"sentence": "Typing practice makes perfect.", "offline": True})
        sentence = random.choice(sents)
        print(f"[OK] Serving {difficulty} sentence: {sentence}")
        return jsonify({"sentence": sentence, "difficulty": difficulty})
    except Exception as e:
        print("[ERROR] Could not load sentences:", e)
        return jsonify({"sentence": "The programmer eats at school.", "offline": True})


@app.route("/api/save_run", methods=["POST"])
def api_save_run():
    """Save a typing run and return updated summary."""
    data = request.get_json() or {}
    user = current_user()
    if not user:
        return jsonify({"error": "login required"}), 401

    # Allow frontend to optionally supply difficulty
    difficulty = data.get("difficulty", data.get("level", "unknown"))

    try:
        wpm = int(float(data.get("wpm", 0)))
    except Exception:
        wpm = 0
    try:
        accuracy = float(data.get("accuracy", 0))
    except Exception:
        accuracy = 0.0
    timestamp = int(time.time())

    history = load_json(HISTORY_FILE, {})
    # store as a consistent dict (includes difficulty)
    history.setdefault(user["username"], []).append({
        "wpm": wpm,
        "accuracy": accuracy,
        "time": timestamp,
        "difficulty": difficulty,
        "timestamp": timestamp
    })
    save_json(HISTORY_FILE, history)

    # return updated recent summary for frontend dashboard refresh
    recent = history[user["username"]][-5:]
    avg = sum([r.get("wpm", 0) for r in history[user["username"]]]) / max(1, len(history[user["username"]]))
    return jsonify({
        "ok": True,
        "recent_runs": recent[::-1],
        "average_wpm": round(avg, 2)
    })
from datetime import datetime
@app.route("/save_result", methods=["POST"])
@login_required
def save_result():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    difficulty = data.get("difficulty", "Unknown")
    wpm = data.get("wpm", 0)
    accuracy = data.get("accuracy", 0)
    time_spent = data.get("time", 0)

    user = current_user()
    username = user["username"] if user else "Anonymous"

    # Load history file
    history = load_json(HISTORY_FILE, {})

    if username not in history:
        history[username] = []

    history[username].append({
        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "difficulty": difficulty,
        "wpm": wpm,
        "accuracy": accuracy,
        "time": time_spent,
        "status": "completed",
        "timestamp": int(time.time())
    })

    save_json(HISTORY_FILE, history)

    print(f"[SAVE_RESULT] {username} — {wpm}WPM, {accuracy}% @ {difficulty}")
    return jsonify({"success": True})


# alias some clients expect /api/submit
@app.route("/api/submit", methods=["POST"])
def api_submit_alias():
    return api_save_run()

# -----------------------------------------------------
# User upgrade request endpoint (user-side)
# Stores request on users.json as pending_upgrade_to/pending_amount/pending_status
# -----------------------------------------------------
@app.route("/api/upgrade_request", methods=["POST"])
def api_upgrade_request():
    user = current_user()
    if not user:
        return jsonify({"error": "login required"}), 401
    data = request.get_json() or {}
    plan_req = data.get("plan", "premium_plus")
    # We'll only support premium_plus and premium
    if plan_req not in ("premium_plus", "premium"):
        return jsonify({"error": "invalid_plan"}), 400
    users = load_json(USERS_FILE, {})
    u = users.get(user["username"])
    if not u:
        return jsonify({"error": "user_not_found"}), 404

    # if already pending
    if u.get("pending_upgrade_to"):
        return jsonify({"error": "already_pending"}), 400

    # amount: use 1000 for premium_plus, 2000 for premium (matching UI)
    amount = 1000 if plan_req == "premium_plus" else 2000
    u["pending_upgrade_to"] = plan_req
    u["pending_amount"] = amount
    u["pending_status"] = "pending"
    users[user["username"]] = u
    save_json(USERS_FILE, users)
    return jsonify({"ok": True, "pending": {"plan": plan_req, "amount": amount}})

# -----------------------------------------------------
# Multiplayer routes & socket events (with room isolation)
# -----------------------------------------------------
@app.route("/multiplayer/<level>")
def multiplayer(level):
    user = current_user()
    if not user:
        flash("Login first", "error")
        return redirect(url_for("login"))

    # Define access levels by plan
    if user["plan"] == "premium_plus":
        allowed_levels = ["beginner", "intermediate", "advanced", "expert"]
    elif user["plan"] == "premium":
        allowed_levels = ["beginner"]
    else:
        flash("Multiplayer is Premium only", "error")
        return redirect(url_for("upgrade"))

    # If trying to open locked level
    if level not in allowed_levels:
        flash("🚫 You don’t have access to this level. Upgrade to unlock it!", "danger")
        return redirect(url_for("upgrade"))

    return render_template("multiplayer.html", level=level, allowed_levels=allowed_levels, user=user)



# helper to list players in a given room/level
def room_players(level):
    """Helper to get all players in a specific room."""
    return [p for p in players.values() if p.get("level") == level]

# SOCKET.IO CONNECTION HANDLING
@socketio.on("connect")
def handle_connect():
    sid = flask_request.sid  # type: ignore[attr-defined]
    uname = session.get("username")
    users = load_json(USERS_FILE, {})

    if not uname or uname not in users:
        display_name = f"Guest-{len(players) + 1}"
        level = "beginner"
        plan = "free"
    else:
        meta = users[uname]
        display_name = uname
        level = meta.get("level", "beginner")
        plan = meta.get("plan", "free")

        # Restrict premium (not plus) to beginner room
        if plan == "premium":
            level = "beginner"

    players[sid] = {"name": display_name, "username": uname, "level": level, "wpm": 0, "progress": 0}

    # Join the player's level room
    try:
        join_room(level)
    except Exception:
        pass

    print(f"[CONNECT] {display_name} joined {level} room")

    # Send player list only for that room (both event names for backward compatibility)
    emit("update_players", list(room_players(level)), to=level)
    emit("update_progress", {"players": {p["name"]: p.get("progress", 0) for p in room_players(level)}}, to=level)

@socketio.on("disconnect")
def handle_disconnect():
    sid = flask_request.sid  # type: ignore[attr-defined]
    player = players.pop(sid, None)
    if player:
        level = player.get("level", "beginner")
        try:
            leave_room(level)
        except Exception:
            pass
        emit("update_players", list(room_players(level)), to=level)
        emit("update_progress", {"players": {p["name"]: p.get("progress", 0) for p in room_players(level)}}, to=level)
        print(f"[DISCONNECT] {player['name']} left {level} room")

# When a client requests a race, server sends countdown then start_game for that specific room
@socketio.on("request_race")
def handle_request_race(data):
    sid = flask_request.sid  # type: ignore[attr-defined]
    user_info = players.get(sid)
    if not user_info:
        emit("error", {"msg": "player-not-found"})
        return

    level = data.get("level") or user_info.get("level", "beginner")
    username = user_info.get("username")

    # Enforce plan restriction
    if username:
        users = load_json(USERS_FILE, {})
        meta = users.get(username, {})
        if meta.get("plan") == "premium" and level != "beginner":
            level = "beginner"

    sentence = pick_level_sentence(level)
    if not sentence:
        sentence = random.choice(load_sentences_all().get("easy", ["Typing test sentence."]))

    # Broadcast countdown only to players in that level room
    emit("countdown", {"from": 5}, to=level)
    # Use socketio.sleep to avoid blocking main thread
    socketio.sleep(5)
    # emit both event names so all variants of your frontend receive the sentence
    emit("start_game", {"sentence": sentence, "level": level}, to=level)
    emit("new_sentence", {"sentence": sentence, "level": level}, to=level)
    print(f"[RACE START] Level {level} — Sentence sent to {len(room_players(level))} players")

@socketio.on("progress_update")
def handle_progress_update(data):
    sid = flask_request.sid  # type: ignore[attr-defined]
    p = players.get(sid)
    if not p:
        return

    # Accept progress either numeric or percentage
    try:
        progress = int(float(data.get("progress", 0)))
    except Exception:
        progress = 0
    try:
        wpm = int(float(data.get("wpm", p.get("wpm", 0))))
    except Exception:
        wpm = int(p.get("wpm", 0) or 0)

    p["progress"] = progress
    p["wpm"] = wpm

    level = p.get("level", "beginner")
    # emit both names for clients
    emit("update_players", list(room_players(level)), to=level)
    emit("update_progress", {"players": {pp["name"]: pp.get("progress", 0) for pp in room_players(level)}}, to=level)

@socketio.on("race_finished")
def handle_race_finished(data):
    sid = flask_request.sid  # type: ignore[attr-defined]
    user_info = players.get(sid)
    if not user_info:
        return

    username = user_info.get("username")
    if not username:
        return

    users = load_json(USERS_FILE, {})
    user = users.get(username, {})
    levels_data = load_json(LEVELS_FILE, {})

    wpm = int(data.get("wpm", 0) or 0)
    won = bool(data.get("won", False))

    # Update performance
    user["races_played"] = user.get("races_played", 0) + 1
    user["total_wpm"] = user.get("total_wpm", 0) + wpm
    user["avg_wpm"] = round(user["total_wpm"] / user["races_played"], 2)

    if won:
        user["wins"] = user.get("wins", 0) + 1

    old_level = user.get("level", "beginner")
    new_level = calculate_level(user, levels_data)
    leveled_up = new_level != old_level
    user["level"] = new_level

    users[username] = user
    save_json(USERS_FILE, users)

    reward_text = levels_data.get(new_level, {}).get("reward", "")
    description = levels_data.get(new_level, {}).get("description", "")

    # emit level update back to the single user (use to=sid for SocketIO)
    emit(
        "level_update",
        {
            "level": new_level,
            "reward": reward_text,
            "description": description,
            "leveled_up": leveled_up,
        },
        to=sid,
    )

    print(f"[FINISH] {username} finished race (WPM {wpm}) — Level: {new_level}")

# -----------------------------------------------------
# Level progression helper used above (keeps your original formula)
# --\`-------------------------------------------------
def calculate_level(user_data, levels_data):
    """Determine user's level based on WPM and wins."""
    wpm = user_data.get("avg_wpm", 0)
    wins = user_data.get("wins", 0)
    current = user_data.get("level", "beginner")

    # Go through levels in order
    for name, info in levels_data.items():
        # expect "range": [min, max]
        rng = info.get("range", [0, 9999])
        if len(rng) >= 2:
            min_wpm, max_wpm = rng[0], rng[1]
        else:
            min_wpm, max_wpm = rng[0], 9999
        if min_wpm <= wpm <= max_wpm and wins >= 3:
            return name
    return current or "beginner"

@app.route("/api/user")
def api_user():
    """Returns the currently logged-in user (for JS to sync state)."""
    u = current_user()
    if not u:
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "username": u["username"],
        "role": u["role"],
        "plan": u["plan"],
        "level": u["level"]
    })

# -----------------------------------------------------
# Admin API — Pending Upgrades Management
# -----------------------------------------------------
@app.route("/api/admin/pending_upgrades")
def api_pending_upgrades():
    user = current_user()
    if not user or user.get("role") != "admin":
        return jsonify([]), 403

    users = load_json(USERS_FILE, {})
    pending = [
        {"username": uname, "pending": u.get("pending_upgrade_to"), "amount": u.get("pending_amount", 0), "status": u.get("pending_status", "pending")}
        for uname, u in users.items() if u.get("pending_upgrade_to")
    ]
    return jsonify(pending)

@app.route("/api/admin/mark_paid", methods=["POST"])
def api_mark_paid():
    user = current_user()
    if not user or user.get("role") != "admin":
        return jsonify({"error": "unauthorized"}), 403

    data = request.get_json() or {}
    uname = data.get("username")
    users = load_json(USERS_FILE, {})
    if uname in users and users[uname].get("pending_upgrade_to"):
        # apply requested plan
        target = users[uname].pop("pending_upgrade_to", None)
        users[uname]["plan"] = target or users[uname].get("plan", "free")
        # clear pending metadata
        users[uname].pop("pending_amount", None)
        users[uname].pop("pending_status", None)
        save_json(USERS_FILE, users)
        return jsonify({"ok": True})
    return jsonify({"error": "invalid user"}), 400

@app.after_request
def add_no_cache_headers_api(response):
    """Prevent caching on JSON routes so new sentences always load fresh."""
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
# ============================================================
# ✅ ENHANCED HISTORY SAVER — includes username + plan + level
@app.route("/save_history", methods=["POST"])
def save_history():
    """Save typing test result to the user's history"""
    data = request.get_json()
    username = session.get("username", "Guest")
    plan = session.get("plan", "Free")

    entry = {
        "wpm": data.get("wpm", 0),
        "accuracy": data.get("accuracy", 0),
        "time": data.get("time", 0),
        "level": data.get("level", "Unknown"),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Create directory if not exists
    os.makedirs("data/history", exist_ok=True)

    # File per user
    user_file = os.path.join("data/history", f"{username}.json")
    history = []
    if os.path.exists(user_file):
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    # Append new entry
    history.append(entry)
    with open(user_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    # Debug log
    print(
        f"[SAVE_HISTORY] {username} ({plan}) — "
        f"{entry['wpm']} WPM, {entry['accuracy']}%, {entry['level']}"
    )

    return jsonify({"success": True, "message": "History saved!"})


# -----------------------------------------------------
# Run server
# -----------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting TypeForge with levels + multiplayer on port {port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)
