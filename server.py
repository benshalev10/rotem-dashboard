"""
Rotem Shani Dashboard Server
=============================
- Serves the dashboard with login
- Each user has username + hashed password
- /upload endpoint receives daily JSON from the .bat
- /admin page to add/remove users
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, session, redirect, abort
from functools import wraps
import json, os, hashlib, secrets, datetime

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_FILE  = os.path.join(BASE_DIR, "data", "rotem_shani_data.json")
USERS_FILE = os.path.join(BASE_DIR, "data", "users.json")
UPLOAD_KEY = os.environ.get("UPLOAD_KEY", "CHANGE_THIS_KEY")   # set in .env

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

# ── Helpers ──────────────────────────────────────────────────────────────────

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        # Create default admin on first run
        default = {"admin": {"password": hash_pw("admin123"), "role": "admin"}}
        save_users(default)
        return default
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        users = load_users()
        if users.get(session["user"], {}).get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return send_from_directory("static", "login.html")

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    users = load_users()

    user = users.get(username)
    if user and user["password"] == hash_pw(password):
        session["user"] = username
        session["role"] = user.get("role", "viewer")
        return jsonify({"ok": True, "role": session["role"]})
    return jsonify({"ok": False, "error": "שם משתמש או סיסמה שגויים"}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/api/me")
def me():
    if "user" not in session:
        return jsonify({"loggedIn": False}), 401
    return jsonify({"loggedIn": True, "user": session["user"], "role": session["role"]})

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return send_from_directory("static", "dashboard.html")

@app.route("/api/data")
@login_required
def get_data():
    if not os.path.exists(DATA_FILE):
        return jsonify({"error": "No data yet"}), 404
    return send_file(DATA_FILE, mimetype="application/json")

# ── Upload endpoint (called from .bat) ────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload():
    key = request.headers.get("X-Upload-Key", "")
    if key != UPLOAD_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    f = request.files["file"]
    try:
        data = json.loads(f.read())
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    with open(DATA_FILE, "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{ts}] Data uploaded OK ({os.path.getsize(DATA_FILE)//1024} KB)")
    return jsonify({"ok": True, "timestamp": ts})

# ── Admin: manage users ───────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_page():
    return send_from_directory("static", "admin.html")

@app.route("/api/users", methods=["GET"])
@admin_required
def list_users():
    users = load_users()
    return jsonify([
        {"username": u, "role": v.get("role", "viewer")}
        for u, v in users.items()
    ])

@app.route("/api/users", methods=["POST"])
@admin_required
def add_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    role     = data.get("role", "viewer")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    users = load_users()
    if username in users:
        return jsonify({"error": "User already exists"}), 409

    users[username] = {"password": hash_pw(password), "role": role}
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/users/<username>", methods=["DELETE"])
@admin_required
def delete_user(username):
    if username == session["user"]:
        return jsonify({"error": "Cannot delete yourself"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    del users[username]
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/users/<username>/password", methods=["PATCH"])
@admin_required
def change_password(username):
    data = request.get_json(silent=True) or {}
    password = data.get("password", "").strip()
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    users[username]["password"] = hash_pw(password)
    save_users(users)
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting server on port {port}")
    print(f"Default admin login: admin / admin123  ← CHANGE THIS IMMEDIATELY")
    app.run(host="0.0.0.0", port=port, debug=False)
