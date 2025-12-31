# app.py – TypeForge (merged, non-destructive, multiplayer rooms + promotions)
# -----------------------------------------------------
import os
import json
import time
import random
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request as flask_request  # used for SocketIO sid

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
players = {}  # sid -> {name, username, level, wpm, progress}
tournaments = {}  # tournament_id -> {players: [], status: 'waiting|active|finished', rounds: [], current_round: 0}
active_tournaments = {}  # room -> tournament data

# -----------------------------------------------------
# Helpers: JSON utils
# -----------------------------------------------------
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path, default=None):
    ensure_data_dir()
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default or {}, f, indent=2)
        return default or {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
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

@app.route("/leaderboard")
def leaderboard():
    history = load_json(HISTORY_FILE, {})
    users_data = load_json(USERS_FILE, {})
    scores = []

    for uname, runs in history.items():
        if not runs:
            continue
        wpms = [r.get("wpm", 0) for r in runs if r.get("wpm") is not None]
        if not wpms:
            continue
        avg_wpm = sum(wpms) / len(wpms)
        best_wpm = max(wpms)
        avg_acc = round(sum(float(r.get("accuracy", 0)) for r in runs) / len(runs), 2)
        level = users_data.get(uname, {}).get("level", "beginner")
        total_tests = len(runs)
        
        scores.append({
            "username": uname,
            "level": level,
            "avg_wpm": round(avg_wpm, 2),
            "best_wpm": round(best_wpm, 2),
            "avg_accuracy": avg_acc,
            "total_tests": total_tests
        })

    scores = sorted(scores, key=lambda x: x["avg_wpm"], reverse=True)
    return render_template("leaderboard.html", leaderboard=scores[:50])  # top 50


@app.route("/profile")
def profile():
    user = current_user()
    if not user:
        flash("Login to view profile", "error")
        return redirect(url_for("login"))

    history = load_json(HISTORY_FILE, {})
    user_runs = history.get(user["username"], [])
    
    # Calculate detailed stats
    total_tests = len(user_runs)
    if total_tests > 0:
        avg_wpm = sum(r.get("wpm", 0) for r in user_runs) / total_tests
        avg_accuracy = sum(r.get("accuracy", 0) for r in user_runs) / total_tests
        best_wpm = max(r.get("wpm", 0) for r in user_runs)
        best_accuracy = max(r.get("accuracy", 0) for r in user_runs)
        total_time = sum(r.get("time", 0) for r in user_runs)
        total_chars = sum(r.get("characters", 0) for r in user_runs)
    else:
        avg_wpm = avg_accuracy = best_wpm = best_accuracy = total_time = total_chars = 0

    # Streaks and achievements
    streak = calculate_streak(user_runs)
    achievements = get_achievements(user_runs)

    # Global activity - recent tests from all users
    global_activity = []
    for username, user_runs in history.items():
        for run in user_runs[-5:]:  # last 5 runs per user
            global_activity.append({
                "username": username,
                "wpm": run.get("wpm", 0),
                "accuracy": run.get("accuracy", 0),
                "date": run.get("date", ""),
                "mode": run.get("mode", "time")
            })
    
    # Sort by date (most recent first) and take top 20
    global_activity.sort(key=lambda x: x["date"], reverse=True)
    global_activity = global_activity[:20]

    return render_template("profile.html", 
                         user=user, 
                         runs=user_runs[-20:],  # last 20 runs
                         stats={
                             "total_tests": total_tests,
                             "avg_wpm": round(avg_wpm, 2),
                             "avg_accuracy": round(avg_accuracy, 2),
                             "best_wpm": best_wpm,
                             "best_accuracy": best_accuracy,
                             "total_time": total_time,
                             "total_chars": total_chars
                         },
                         streak=streak,
                         achievements=achievements,
                         global_activity=global_activity)

def calculate_streak(runs):
    if not runs:
        return 0
    # Simple streak: consecutive days with tests
    dates = sorted(set(r["date"].split(" ")[0] for r in runs if "date" in r), reverse=True)
    streak = 0
    current_date = datetime.now().date()
    for date_str in dates:
        run_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if run_date == current_date:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            break
    return streak

def get_achievements(runs):
    achievements = []
    total_tests = len(runs)
    best_wpm = max((r.get("wpm", 0) for r in runs), default=0)
    avg_wpm = sum(r.get("wpm", 0) for r in runs) / max(total_tests, 1)
    total_chars = sum(r.get("characters", 0) for r in runs)
    best_accuracy = max((r.get("accuracy", 0) for r in runs), default=0)
    modes_used = set(r.get("mode", "time") for r in runs)
    
    # Basic achievements
    if total_tests >= 1: achievements.append("🚀 First Test")
    if total_tests >= 10: achievements.append("🔥 10 Tests")
    if total_tests >= 50: achievements.append("💯 50 Tests")
    if total_tests >= 100: achievements.append("🏆 Century Club")
    
    # Speed achievements
    if best_wpm >= 40: achievements.append("⚡ Speed Starter")
    if best_wpm >= 60: achievements.append("💨 Fast Fingers")
    if best_wpm >= 80: achievements.append("🌀 Typing Ninja")
    if best_wpm >= 100: achievements.append("🚀 Speed Demon")
    if best_wpm >= 120: achievements.append("👑 Typing Legend")
    
    # Accuracy achievements
    if best_accuracy >= 95: achievements.append("🎯 Accuracy Master")
    if best_accuracy >= 98: achievements.append("🔍 Perfectionist")
    if best_accuracy == 100: achievements.append("💎 Flawless")
    
    # Volume achievements
    if total_chars >= 10000: achievements.append("📚 Word Warrior")
    if total_chars >= 50000: achievements.append("📖 Book Reader")
    if total_chars >= 100000: achievements.append("🎓 Scholar")
    
    # Mode diversity
    if len(modes_used) >= 3: achievements.append("🎮 Mode Explorer")
    if len(modes_used) >= 5: achievements.append("🎪 Mode Master")
    if "puzzle" in modes_used: achievements.append("🧩 Puzzle Solver")
    if "code" in modes_used: achievements.append("💻 Code Warrior")
    if "quote" in modes_used: achievements.append("💭 Quote Master")
    
    # Consistency achievements
    if avg_wpm >= 50 and total_tests >= 20: achievements.append("📈 Consistent")
    if avg_wpm >= 70 and total_tests >= 20: achievements.append("📊 Reliable")
    
    # Special achievements
    high_score_games = sum(1 for r in runs if r.get("wpm", 0) >= 80)
    if high_score_games >= 10: achievements.append("🌟 High Scorer")
    
    return achievements


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
    mode = request.args.get("mode", "time")
    length = request.args.get("length", "30")
    language = request.args.get("language", "english")
    punctuation = request.args.get("punctuation", "false").lower() == "true"
    numbers = request.args.get("numbers", "false").lower() == "true"

    if mode == "time":
        # For time mode, return a sentence long enough for the time
        duration = int(length)
        # Estimate words needed (average 5 chars per word, 40 WPM = ~200 chars per minute)
        chars_needed = duration * 200
        sentences = load_sentences_all()
        sentence = get_random_sentence(sentences, chars_needed, language, punctuation, numbers)
        return jsonify({"text": sentence, "mode": mode, "length": length})
    elif mode == "words":
        word_count = int(length)
        sentences = load_sentences_all()
        sentence = get_words_sentence(sentences, word_count, language, punctuation, numbers)
        return jsonify({"text": sentence, "mode": mode, "length": length})
    elif mode == "quote":
        # Return a famous quote
        quote = get_random_quote(language)
        return jsonify({"text": quote, "mode": mode, "length": length})
    elif mode == "puzzle":
        # Return scrambled words to unscramble
        puzzle_text = get_puzzle_text(length, language)
        return jsonify({"text": puzzle_text, "mode": mode, "length": length})
    elif mode == "code":
        # Return programming code snippet
        code_text = get_code_snippet(language)
        return jsonify({"text": code_text, "mode": mode, "length": length})
    elif mode == "custom":
        custom_text = request.args.get("custom_text", "")
        if custom_text:
            return jsonify({"text": custom_text, "mode": mode, "length": length})
        else:
            return jsonify({"text": "Please enter custom text in settings.", "mode": mode, "length": length})

def get_random_sentence(sentences, min_chars, language, punctuation, numbers):
    # Simplified - in real implementation, filter by language and options
    all_sentences = []
    for level in sentences.values():
        if isinstance(level, list):
            all_sentences.extend(level)
    
    # Filter sentences based on criteria
    filtered = [s for s in all_sentences if len(s) >= min_chars // 2]
    
    if not filtered:
        return "The programmer writes code that makes the computer do amazing things."
    
    sentence = random.choice(filtered)
    
    # Add punctuation/numbers if requested
    if punctuation or numbers:
        sentence = enhance_sentence(sentence, punctuation, numbers)
    
    return sentence

def get_words_sentence(sentences, word_count, language, punctuation, numbers):
    all_sentences = []
    for level in sentences.values():
        if isinstance(level, list):
            all_sentences.extend(level)
    
    words = []
    while len(words) < word_count:
        sentence = random.choice(all_sentences)
        sentence_words = sentence.split()
        words.extend(sentence_words)
    
    words = words[:word_count]
    sentence = " ".join(words)
    
    if punctuation or numbers:
        sentence = enhance_sentence(sentence, punctuation, numbers)
    
    return sentence

def get_random_quote(language):
    quotes = {
        'english': [
            "The only way to do great work is to love what you do. - Steve Jobs",
            "Believe you can and you're halfway there. - Theodore Roosevelt",
            "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
            "You miss 100% of the shots you don't take. - Wayne Gretzky",
            "The best way to predict the future is to create it. - Peter Drucker",
            "The journey of a thousand miles begins with one step. - Lao Tzu",
            "That which does not kill us makes us stronger. - Friedrich Nietzsche",
            "The only impossible journey is the one you never begin. - Tony Robbins"
        ],
        'spanish': [
            "El único modo de hacer un gran trabajo es amar lo que haces. - Steve Jobs",
            "Cree que puedes y estarás a mitad de camino. - Theodore Roosevelt",
            "El futuro pertenece a quienes creen en la belleza de sus sueños. - Eleanor Roosevelt",
            "Fallas el 100% de los tiros que no intentas. - Wayne Gretzky",
            "La mejor manera de predecir el futuro es crearlo. - Peter Drucker"
        ],
        'french': [
            "Le seul moyen de faire du bon travail est d'aimer ce que vous faites. - Steve Jobs",
            "Crois que tu peux et tu es à mi-chemin. - Theodore Roosevelt",
            "L'avenir appartient à ceux qui croient à la beauté de leurs rêves. - Eleanor Roosevelt",
            "Tu rates 100% des tirs que tu n'essaies pas. - Wayne Gretzky",
            "La meilleure façon de prédire l'avenir est de le créer. - Peter Drucker"
        ],
        'german': [
            "Der einzige Weg, großartige Arbeit zu leisten, ist, das zu lieben, was man tut. - Steve Jobs",
            "Glaube, dass du kannst, und du bist schon halb da. - Theodore Roosevelt",
            "Die Zukunft gehört denen, die an die Schönheit ihrer Träume glauben. - Eleanor Roosevelt",
            "Du verfehlst 100% der Schüsse, die du nicht machst. - Wayne Gretzky",
            "Die beste Art, die Zukunft vorherzusagen, ist, sie zu erschaffen. - Peter Drucker"
        ]
    }
    lang_quotes = quotes.get(language.lower(), quotes['english'])
    return random.choice(lang_quotes)

def get_puzzle_text(length, language):
    # Generate scrambled words for puzzle mode
    words = [
        "python", "javascript", "algorithm", "database", "function", "variable", "array", "object",
        "class", "method", "inheritance", "polymorphism", "recursion", "iteration", "condition",
        "boolean", "string", "integer", "float", "character", "pointer", "memory", "stack", "queue"
    ]
    
    word_count = min(int(length) if length.isdigit() else 10, len(words))
    selected_words = random.sample(words, word_count)
    
    # Scramble each word
    scrambled = []
    for word in selected_words:
        scrambled_word = ''.join(random.sample(word, len(word)))
        scrambled.append(f"{scrambled_word} ({word})")
    
    return "Unscramble: " + " | ".join(scrambled)

def get_code_snippet(language):
    # Return programming code snippets
    code_snippets = {
        "python": [
            "def fibonacci(n):\n    if n <= 1:\n        return n\n    else:\n        return fibonacci(n-1) + fibonacci(n-2)",
            "class Rectangle:\n    def __init__(self, width, height):\n        self.width = width\n        self.height = height\n    \n    def area(self):\n        return self.width * self.height",
            "import requests\nresponse = requests.get('https://api.example.com/data')\nprint(response.json())",
            "numbers = [1, 2, 3, 4, 5]\nsquared = [x**2 for x in numbers if x % 2 == 0]\nprint(squared)"
        ],
        "javascript": [
            "function fetchData(url) {\n    return fetch(url)\n        .then(response => response.json())\n        .then(data => console.log(data));\n}",
            "const numbers = [1, 2, 3, 4, 5];\nconst evenNumbers = numbers.filter(num => num % 2 === 0);\nconsole.log(evenNumbers);",
            "class Person {\n    constructor(name, age) {\n        this.name = name;\n        this.age = age;\n    }\n    \n    greet() {\n        return `Hello, my name is ${this.name}`;\n    }\n}",
            "const promise = new Promise((resolve, reject) => {\n    setTimeout(() => resolve('Done!'), 1000);\n});\npromise.then(result => console.log(result));"
        ],
        "english": [
            "function calculateSum(a, b) {\n    return a + b;\n}\n\nconst result = calculateSum(5, 3);\nconsole.log(result);",
            "const users = [\n    { name: 'Alice', age: 25 },\n    { name: 'Bob', age: 30 }\n];\n\nconst names = users.map(user => user.name);\nconsole.log(names);",
            "try {\n    const data = JSON.parse(jsonString);\n    console.log(data);\n} catch (error) {\n    console.error('Invalid JSON:', error);\n}",
            "const button = document.querySelector('#myButton');\nbutton.addEventListener('click', () => {\n    alert('Button clicked!');\n});"
        ]
    }
    
    lang_snippets = code_snippets.get(language.lower(), code_snippets['english'])
    return random.choice(lang_snippets)

def enhance_sentence(sentence, punctuation, numbers):
    # Simple enhancement - add some punctuation and numbers
    if punctuation:
        # Add commas, periods, etc.
        words = sentence.split()
        enhanced = []
        for i, word in enumerate(words):
            enhanced.append(word)
            if i < len(words) - 1 and random.random() < 0.3:
                enhanced.append(random.choice([",", ";", ":"]))
        sentence = " ".join(enhanced)
        if not sentence.endswith((".", "!", "?")):
            sentence += "."
    
    if numbers:
        # Replace some words with numbers
        words = sentence.split()
        for i in range(len(words)):
            if random.random() < 0.2:
                words[i] = str(random.randint(1, 100))
        sentence = " ".join(words)
    
    return sentence


@app.route("/api/save_run", methods=["POST"])
def api_save_run():
    """Save a typing run and return updated summary."""
    data = request.get_json() or {}
    user = current_user()
    if not user:
        return jsonify({"error": "login required"}), 401

    wpm = int(float(data.get("wpm", 0)))
    accuracy = float(data.get("accuracy", 0))
    timestamp = int(time.time())

    history = load_json(HISTORY_FILE, {})
    history.setdefault(user["username"], []).append({
        "wpm": wpm,
        "accuracy": accuracy,
        "time": timestamp
    })
    save_json(HISTORY_FILE, history)

    # return updated recent summary for frontend dashboard refresh
    recent = history[user["username"]][-5:]
    avg = sum([r["wpm"] for r in history[user["username"]]]) / len(history[user["username"]])
    return jsonify({
        "ok": True,
        "recent_runs": recent[::-1],
        "average_wpm": round(avg, 2)
    })
from datetime import datetime

@app.route("/save_result", methods=["POST"])
def save_result():
    data = request.get_json()
    difficulty = data.get("difficulty")
    wpm = data.get("wpm")
    accuracy = data.get("accuracy")
    time_spent = data.get("time")

    if not all([difficulty, wpm, accuracy, time_spent is not None]):
        return jsonify({"error": "Missing data"}), 400

    user = current_user()
    if not user:
        return jsonify({"error": "login required"}), 401

    username = user["username"]
    history = load_json(HISTORY_FILE, {})

    new_run = {
        "difficulty": difficulty,
        "wpm": round(float(wpm), 2),
        "accuracy": round(float(accuracy), 2),
        "time": int(time_spent),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if username not in history:
        history[username] = []
    history[username].append(new_run)

    save_json(HISTORY_FILE, history)
    return jsonify({"success": True, "run": new_run})



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

@app.route("/tournament/<level>")
def tournament(level):
    user = current_user()
    if not user:
        flash("Login first", "error")
        return redirect(url_for("login"))

    # Only premium plus can access tournaments
    if user["plan"] != "premium_plus":
        flash("Tournaments are Premium Plus only", "error")
        return redirect(url_for("upgrade"))

    allowed_levels = ["beginner", "intermediate", "advanced", "expert"]
    if level not in allowed_levels:
        flash("Invalid tournament level", "error")
        return redirect(url_for("upgrade"))

    return render_template("tournament.html", level=level, user=user)



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

    # emit level update back to the single user (use room as sid)
    emit(
        "level_update",
        {
            "level": new_level,
            "reward": reward_text,
            "description": description,
            "leveled_up": leveled_up,
        },
        room=sid,
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

# -----------------------------------------------------
# Tournament SocketIO Events
# -----------------------------------------------------
@socketio.on("join_tournament")
def handle_join_tournament(data):
    sid = flask_request.sid
    level = data.get("level", "beginner")
    username = data.get("username")
    
    room = f"tournament_{level}"
    
    if room not in active_tournaments:
        active_tournaments[room] = {
            "players": [],
            "status": "waiting",
            "current_round": 0,
            "total_rounds": 3,
            "sentences": [],
            "results": []
        }
    
    tournament = active_tournaments[room]
    
    # Add player if not already in
    player_exists = any(p["username"] == username for p in tournament["players"])
    if not player_exists:
        tournament["players"].append({
            "username": username,
            "sid": sid,
            "wpm": 0,
            "status": "waiting",
            "ready": False
        })
    
    join_room(room)
    emit("tournament_update", tournament, room=room)
    emit("tournament_message", f"Welcome to {level} tournament! Waiting for players...", room=sid)

@socketio.on("tournament_ready")
def handle_tournament_ready(data):
    sid = flask_request.sid
    ready = data.get("ready", False)
    
    # Find player's tournament
    for room, tournament in active_tournaments.items():
        for player in tournament["players"]:
            if player["sid"] == sid:
                player["ready"] = ready
                
                # Check if all players are ready
                all_ready = all(p["ready"] for p in tournament["players"])
                if all_ready and len(tournament["players"]) >= 2 and tournament["status"] == "waiting":
                    start_tournament_round(room)
                break

@socketio.on("tournament_progress")
def handle_tournament_progress(data):
    sid = flask_request.sid
    progress = data.get("progress", 0)
    
    for room, tournament in active_tournaments.items():
        for player in tournament["players"]:
            if player["sid"] == sid:
                player["progress"] = progress
                emit("tournament_update", tournament, room=room)
                break

@socketio.on("tournament_finish")
def handle_tournament_finish(data):
    sid = flask_request.sid
    wpm = data.get("wpm", 0)
    
    for room, tournament in active_tournaments.items():
        for player in tournament["players"]:
            if player["sid"] == sid:
                player["wpm"] = wpm
                player["status"] = "finished"
                
                # Check if round is complete
                finished_players = [p for p in tournament["players"] if p["status"] == "finished"]
                if len(finished_players) == len(tournament["players"]):
                    end_tournament_round(room)
                break

@socketio.on("leave_tournament")
def handle_leave_tournament():
    sid = flask_request.sid
    
    for room, tournament in active_tournaments.items():
        tournament["players"] = [p for p in tournament["players"] if p["sid"] != sid]
        
        if len(tournament["players"]) == 0:
            del active_tournaments[room]
        else:
            emit("tournament_update", tournament, room=room)
        break
    
    leave_room(room)

def start_tournament_round(room):
    tournament = active_tournaments[room]
    tournament["status"] = "active"
    tournament["current_round"] += 1
    
    # Get a random sentence
    sentences = load_json(SENTENCES_FILE, {}).get("sentences", [])
    if sentences:
        sentence = random.choice(sentences).get("text", "The quick brown fox jumps over the lazy dog.")
    else:
        sentence = "The quick brown fox jumps over the lazy dog."
    
    tournament["current_sentence"] = sentence
    
    # Reset player status
    for player in tournament["players"]:
        player["status"] = "typing"
        player["progress"] = 0
        player["wpm"] = 0
    
    emit("round_start", {"sentence": sentence}, room=room)
    emit("tournament_message", f"Round {tournament['current_round']} starting!", room=room)

def end_tournament_round(room):
    tournament = active_tournaments[room]
    
    # Sort players by WPM
    sorted_players = sorted(tournament["players"], key=lambda p: p["wpm"], reverse=True)
    
    # Mark winner
    if sorted_players:
        sorted_players[0]["status"] = "winner"
    
    tournament["results"].append({
        "round": tournament["current_round"],
        "winners": [p["username"] for p in sorted_players[:len(sorted_players)//2]]
    })
    
    emit("tournament_update", tournament, room=room)
    
    # Check if tournament is complete
    if tournament["current_round"] >= tournament["total_rounds"]:
        end_tournament(room)
    else:
        # Start next round after delay
        socketio.sleep(5)
        start_tournament_round(room)

def end_tournament(room):
    tournament = active_tournaments[room]
    tournament["status"] = "finished"
    
    # Determine final winner
    final_scores = {}
    for result in tournament["results"]:
        for winner in result["winners"]:
            final_scores[winner] = final_scores.get(winner, 0) + 1
    
    final_winner = max(final_scores, key=final_scores.get) if final_scores else None
    
    emit("tournament_message", f"Tournament finished! Winner: {final_winner}", room=room)
    
    # Clean up after delay
    socketio.sleep(10)
    if room in active_tournaments:
        del active_tournaments[room]

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
def add_no_cache_headers(response):
    """Prevent caching on JSON routes so new sentences always load fresh."""
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
@app.route("/api/leaderboard")
def api_leaderboard():
    history = load_json(HISTORY_FILE, {})
    scores = []

    for uname, runs in history.items():
        wpms = [r.get("wpm", 0) for r in runs if r.get("wpm") is not None]
        if not wpms:
            continue
        avg_wpm = sum(wpms) / len(wpms)
        best_wpm = max(wpms)
        avg_acc = round(sum([r.get("accuracy", 0) for r in runs]) / len(runs), 2)
        scores.append({
            "username": uname,
            "wpm": round(avg_wpm, 2),
            "accuracy": avg_acc,
            "best": best_wpm,
        })

    scores = sorted(scores, key=lambda x: x["wpm"], reverse=True)
    return jsonify(scores)

@app.route("/api/history")
def api_history():
    user = current_user()
    if not user:
        return jsonify([]), 401
    history = load_json(HISTORY_FILE, {})
    runs = history.get(user["username"], [])
    return jsonify(runs[-20:][::-1])

# -----------------------------------------------------
# Run server
# -----------------------------------------------------
if __name__ == "__main__":
    print("Starting TypeForge with levels + multiplayer")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False)
