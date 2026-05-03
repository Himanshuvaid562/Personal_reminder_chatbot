from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import os, sys, secrets

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ── MongoDB ────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    print("❌ MONGO_URI not set"); sys.exit(1)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    print("✅ MongoDB connected.")
except Exception as e:
    print(f"❌ MongoDB failed: {e}"); sys.exit(1)

db            = client["neuralDB"]
users_col     = db["users"]
reminders_col = db["reminders"]
history_col   = db["chat_history"]

# index for fast user-scoped queries
reminders_col.create_index([("user_id", 1), ("time", 1)])
users_col.create_index("username", unique=True)

def _now():
    return datetime.now(timezone.utc)

def _uid():
    """Return current logged-in user's id string, or None."""
    return session.get("user_id")

def _require_login():
    if not _uid():
        return jsonify(error="unauthorized"), 401
    return None


# ══════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════

@app.route("/")
def home():
    if not _uid():
        return redirect(url_for("login_page"))
    return render_template("index.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/api/register", methods=["POST"])
def register():
    data     = request.json
    username = data.get("username","").strip().lower()
    password = data.get("password","")
    if not username or not password:
        return jsonify(success=False, error="Username and password required")
    if len(password) < 6:
        return jsonify(success=False, error="Password must be at least 6 characters")
    if users_col.find_one({"username": username}):
        return jsonify(success=False, error="Username already taken")
    uid = str(users_col.insert_one({
        "username": username,
        "password": generate_password_hash(password),
        "created_at": _now()
    }).inserted_id)
    session["user_id"]  = uid
    session["username"] = username
    return jsonify(success=True, username=username)

@app.route("/api/login", methods=["POST"])
def login():
    data     = request.json
    username = data.get("username","").strip().lower()
    password = data.get("password","")
    user     = users_col.find_one({"username": username})
    if not user or not check_password_hash(user["password"], password):
        return jsonify(success=False, error="Invalid username or password")
    session["user_id"]  = str(user["_id"])
    session["username"] = username
    return jsonify(success=True, username=username)

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(success=True)

@app.route("/api/me")
def me():
    if not _uid():
        return jsonify(loggedIn=False)
    return jsonify(loggedIn=True, username=session.get("username"))


# ══════════════════════════════════════════════
#  CHAT
# ══════════════════════════════════════════════

# Per-user conversation state stored in memory dict keyed by user_id
# (fine for single worker; resets on redeploy which is acceptable)
user_states = {}

@app.route("/chat", methods=["POST"])
def chat():
    err = _require_login()
    if err: return err
    uid        = _uid()
    data       = request.json
    raw        = data.get("message", "")
    msg        = raw.strip().lower()
    session_id = data.get("session_id", uid)

    if uid not in user_states:
        user_states[uid] = {"step": None, "task": None}

    try:
        _save_msg(uid, session_id, "user", raw)
        reply = _process(uid, msg, session_id)
        _save_msg(uid, session_id, "bot", reply)
    except Exception as e:
        reply = f"⚠️ Error: {e}"
    return jsonify(reply=reply, session_id=session_id)


def _process(uid, msg, session_id):
    state = user_states[uid]

    if state["step"] == "task":
        state["task"] = msg
        state["step"] = "time"
        return "🕐 Got it! What time? (HH:MM, 24-hour)"

    if state["step"] == "time":
        try:
            datetime.strptime(msg, "%H:%M")
            reminders_col.insert_one({
                "user_id":    uid,
                "task":       state["task"],
                "time":       msg,
                "created_at": _now()
            })
            task = state["task"]
            user_states[uid] = {"step": None, "task": None}
            return f"✅ Reminder set! I'll alert you at **{msg}** for: *{task}*"
        except ValueError:
            return "❌ Use HH:MM format, e.g. `14:30`"

    if any(k in msg for k in ["add reminder","set reminder","new reminder","remind me"]):
        user_states[uid] = {"step": "task", "task": None}
        return "📝 What should I remind you about?"

    if any(k in msg for k in ["show reminder","list reminder","my reminder"]):
        docs = list(reminders_col.find({"user_id": uid}))
        if not docs: return "📭 No reminders yet. Type **add reminder**!"
        return "📋 Your reminders:\n" + "\n".join(f"• **{r['task']}** at {r['time']}" for r in docs)

    if "help" in msg:
        return "💡 Try: **add reminder** · **show reminders**"
    if any(k in msg for k in ["hello","hi","hey"]):
        return f"👋 Hey {session.get('username','there')}! I'm Neural. How can I help?"
    return "🤖 Try: **add reminder** · **show reminders** · **help**"


def _save_msg(uid, session_id, role, text):
    history_col.update_one(
        {"session_id": session_id, "user_id": uid},
        {"$push": {"messages": {"role": role, "text": text, "ts": _now()}},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True
    )


# ══════════════════════════════════════════════
#  REMINDERS  (user-scoped)
# ══════════════════════════════════════════════

@app.route("/get_reminders")
def get_reminders():
    err = _require_login()
    if err: return err
    try:
        docs = list(reminders_col.find({"user_id": _uid()}).sort("time", 1))
        return jsonify([{"id": str(r["_id"]), "task": r["task"], "time": r["time"]} for r in docs])
    except: return jsonify([])

@app.route("/delete_reminder", methods=["POST"])
def delete_reminder():
    err = _require_login()
    if err: return err
    try:
        reminders_col.delete_one({"_id": ObjectId(request.json["id"]), "user_id": _uid()})
        return jsonify(success=True)
    except Exception as e: return jsonify(success=False, error=str(e))

@app.route("/snooze_reminder", methods=["POST"])
def snooze_reminder():
    err = _require_login()
    if err: return err
    try:
        d        = request.json
        new_time = (datetime.now() + timedelta(minutes=int(d.get("minutes", 5)))).strftime("%H:%M")
        reminders_col.update_one(
            {"_id": ObjectId(d["id"]), "user_id": _uid()},
            {"$set": {"time": new_time}}
        )
        return jsonify(success=True, new_time=new_time)
    except Exception as e: return jsonify(success=False, error=str(e))


# ══════════════════════════════════════════════
#  ALARM CHECK  — poll-based, no background thread
#  THE FIX: client sends its LOCAL time, not server time
#  so timezone mismatch on Render is impossible
# ══════════════════════════════════════════════

@app.route("/check_triggered", methods=["POST"])
@app.route("/check_reminder",  methods=["POST"])
def check_triggered():
    err = _require_login()
    if err: return err
    try:
        # Client sends its own local HH:MM — no server timezone guessing
        data     = request.json or {}
        now      = data.get("now")          # "HH:MM" from client JS
        uid      = _uid()
        if not now:
            return jsonify(reminders=[])

        due    = list(reminders_col.find({"user_id": uid, "time": now}))
        result = []
        for r in due:
            result.append({"id": str(r["_id"]), "task": r["task"], "time": r["time"]})
            reminders_col.delete_one({"_id": r["_id"]})
            print(f"🔔 [{session.get('username')}] TRIGGERED → {r['task']} at {now}")
        return jsonify(reminders=result)
    except Exception as e:
        print(f"[check_triggered error] {e}")
        return jsonify(reminders=[])


@app.route("/test_alarm")
def test_alarm():
    if not _uid(): return redirect(url_for("login_page"))
    now = datetime.now().strftime("%H:%M")
    reminders_col.insert_one({
        "user_id":    _uid(),
        "task":       "🧪 Test alarm — it works!",
        "time":       now,
        "created_at": _now()
    })
    return "<h2>✅ Done! Switch to app tab — alarm fires within 5 seconds.</h2>"


# ══════════════════════════════════════════════
#  HISTORY  (user-scoped)
# ══════════════════════════════════════════════

@app.route("/get_sessions")
def get_sessions():
    err = _require_login()
    if err: return err
    try:
        sessions = list(history_col.find(
            {"user_id": _uid()},
            {"session_id":1,"created_at":1,"messages":{"$slice":1}}
        ))
        return jsonify([{
            "session_id": s["session_id"],
            "preview":    (s.get("messages",[{}])[0]).get("text","Chat")[:40],
            "created_at": s.get("created_at", _now()).isoformat()
        } for s in sessions])
    except: return jsonify([])

@app.route("/get_session/<session_id>")
def get_session(session_id):
    err = _require_login()
    if err: return err
    try:
        doc = history_col.find_one({"session_id": session_id, "user_id": _uid()})
        if not doc: return jsonify(messages=[])
        return jsonify(messages=[{"role": m["role"], "text": m["text"]} for m in doc.get("messages",[])])
    except: return jsonify(messages=[])


if __name__ == "__main__":
    app.run(debug=False, port=5000, use_reloader=False)