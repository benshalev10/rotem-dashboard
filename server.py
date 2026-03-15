"""
Rotem Shani Dashboard Server v2
================================
- Data is stored on GitHub (permanent, free)
- Users are stored in memory + environment variable
- /upload endpoint updates GitHub directly
- /admin page to add/remove users
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, session, redirect, abort
from functools import wraps
import json, os, hashlib, secrets, datetime, urllib.request, urllib.error, base64

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

UPLOAD_KEY    = os.environ.get("UPLOAD_KEY", "CHANGE_THIS_KEY")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")   # e.g. benshalev10/rotem-dashboard
GITHUB_FILE   = "rotem_shani_data.json"
GITHUB_BRANCH = "main"

# Users stored in env var as JSON string, fallback to file
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")

# ── Helpers ───────────────────────────────────────────────────────────────────

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    # Try environment variable first (for Render)
    users_env = os.environ.get("USERS_JSON", "")
    if users_env:
        try:
            return json.loads(users_env)
        except Exception:
            pass
    # Fall back to file
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    # Default admin
    default = {"admin": {"password": hash_pw("admin123"), "role": "admin"}}
    save_users(default)
    return default

def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def github_api(method, path, body=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    req.method = method
    if body:
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def get_github_data():
    """Fetch the JSON data file from GitHub."""
    result = github_api("GET", GITHUB_FILE)
    if not result:
        return None
    content = base64.b64decode(result["content"]).decode("utf-8")
    return json.loads(content), result["sha"]

def push_github_data(data: dict, sha: str = None):
    """Push JSON data to GitHub."""
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode()
    ).decode()
    body = {
        "message": f"Update data {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        body["sha"] = sha
    return github_api("PUT", GITHUB_FILE, body)

# ── Auth ──────────────────────────────────────────────────────────────────────

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
    return jsonify({"ok": False, "error": "Wrong username or password"}), 401

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
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({"error": "GitHub not configured"}), 503
    try:
        result = get_github_data()
        if not result:
            return jsonify({"error": "No data yet"}), 404
        data, _ = result
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Upload endpoint ───────────────────────────────────────────────────────────

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

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return jsonify({"error": "GitHub not configured on server"}), 503

    try:
        existing = get_github_data()
        sha = existing[1] if existing else None
        push_github_data(data, sha)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"[{ts}] Data pushed to GitHub OK")
        return jsonify({"ok": True, "timestamp": ts, "storage": "github"})
    except Exception as e:
        return jsonify({"error": f"GitHub push failed: {str(e)}"}), 500

# ── Admin ─────────────────────────────────────────────────────────────────────

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
    app.run(host="0.0.0.0", port=port, debug=False)
