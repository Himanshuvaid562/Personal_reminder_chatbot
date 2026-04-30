from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConfigurationError
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from dotenv import load_dotenv
import threading
import time
import os
import sys

load_dotenv()

app = Flask(__name__)

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    print("❌ MONGO_URI not set in .env"); sys.exit(1)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    print("✅ MongoDB connected.")
except Exception as e:
    print(f"❌ MongoDB failed: {e}"); sys.exit(1)

db            = client["neuralDB"]
reminders_col = db["reminders"]
history_col   = db["chat_history"]
triggered_col = db["triggered"]   # shared across processes via DB

user_state = {"step": None, "task": None, "session_id": None}

def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════
#  PAGES
# ══════════════════════════════════════
@app.route("/")
def home():
    return render_template("index.html")


# ══════════════════════════════════════
#  CHAT
# ══════════════════════════════════════
@app.route("/chat", methods=["POST"])
def chat():
    global user_state
    data       = request.json
    raw        = data.get("message", "")
    msg        = raw.strip().lower()
    session_id = data.get("session_id", "default")
    try:
        _save_msg(session_id, "user", raw)
        reply = _process(msg, session_id)
        _save_msg(session_id, "bot", reply)
    except Exception as e:
        reply = f"⚠️ Error: {e}"
    return jsonify(reply=reply, session_id=session_id)


def _process(msg, session_id):
    global user_state

    if user_state["step"] == "task":
        user_state["task"] = msg
        user_state["step"] = "time"
        return "🕐 Got it! What time? (HH:MM, 24-hour)"

    if user_state["step"] == "time":
        try:
            datetime.strptime(msg, "%H:%M")
            reminders_col.insert_one({"task": user_state["task"], "time": msg, "created_at": _now()})
            task = user_state["task"]
            user_state = {"step": None, "task": None, "session_id": None}
            return f"✅ Reminder set! I'll alert you at **{msg}** for: *{task}*"
        except ValueError:
            return "❌ Use HH:MM format, e.g. `14:30`"

    if any(k in msg for k in ["add reminder","set reminder","new reminder","remind me"]):
        user_state = {"step": "task", "task": None, "session_id": session_id}
        return "📝 What should I remind you about?"

    if any(k in msg for k in ["show reminder","list reminder","my reminder"]):
        docs = list(reminders_col.find())
        if not docs: return "📭 No reminders yet. Type **add reminder**!"
        return "📋 Your reminders:\n" + "\n".join(f"• **{r['task']}** at {r['time']}" for r in docs)

    if "help" in msg:
        return "💡 Try: **add reminder** · **show reminders**"

    if any(k in msg for k in ["hello","hi","hey"]):
        return "👋 Hey! I'm Neural. How can I help?"

    return "🤖 Try: **add reminder** · **show reminders** · **help**"


def _save_msg(session_id, role, text):
    history_col.update_one(
        {"session_id": session_id},
        {"$push": {"messages": {"role": role, "text": text, "ts": _now()}},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True
    )


# ══════════════════════════════════════
#  REMINDERS CRUD
# ══════════════════════════════════════
@app.route("/get_reminders")
def get_reminders():
    try:
        docs = list(reminders_col.find().sort("time", 1))
        return jsonify([{"id": str(r["_id"]), "task": r["task"], "time": r["time"]} for r in docs])
    except: return jsonify([])

@app.route("/delete_reminder", methods=["POST"])
def delete_reminder():
    try:
        reminders_col.delete_one({"_id": ObjectId(request.json["id"])})
        return jsonify(success=True)
    except Exception as e: return jsonify(success=False, error=str(e))

@app.route("/snooze_reminder", methods=["POST"])
def snooze_reminder():
    try:
        d        = request.json
        new_time = (datetime.now() + timedelta(minutes=int(d.get("minutes", 5)))).strftime("%H:%M")
        reminders_col.update_one({"_id": ObjectId(d["id"])}, {"$set": {"time": new_time}})
        return jsonify(success=True, new_time=new_time)
    except Exception as e: return jsonify(success=False, error=str(e))


# ══════════════════════════════════════
#  ALARM POLLING  — DB-backed so it
#  works across Flask's 2 processes
# ══════════════════════════════════════
@app.route("/check_triggered")
@app.route("/check_reminder")
def check_triggered():
    try:
        docs = list(triggered_col.find())
        if not docs:
            return jsonify(reminders=[])
        triggered_col.delete_many({})
        return jsonify(reminders=[{"id": str(d["_id"]), "task": d["task"], "time": d["time"]} for d in docs])
    except Exception as e:
        print(f"[check_triggered error] {e}")
        return jsonify(reminders=[])


# Instant test — open in browser to verify modal+sound works
@app.route("/test_alarm")
def test_alarm():
    triggered_col.insert_one({"task": "🧪 Test alarm!", "time": datetime.now().strftime("%H:%M"), "created_at": _now()})
    return "<h2>✅ Done! Switch to the app tab — modal should appear in ~3 seconds.</h2>"


# ══════════════════════════════════════
#  HISTORY
# ══════════════════════════════════════
@app.route("/get_sessions")
def get_sessions():
    try:
        sessions = list(history_col.find({}, {"session_id":1,"created_at":1,"messages":{"$slice":1}}))
        return jsonify([{
            "session_id": s["session_id"],
            "preview":    (s.get("messages",[{}])[0]).get("text","Chat")[:40],
            "created_at": s.get("created_at", _now()).isoformat()
        } for s in sessions])
    except: return jsonify([])

@app.route("/get_session/<session_id>")
def get_session(session_id):
    try:
        doc = history_col.find_one({"session_id": session_id})
        if not doc: return jsonify(messages=[])
        return jsonify(messages=[{"role": m["role"], "text": m["text"]} for m in doc.get("messages",[])])
    except: return jsonify(messages=[])


# ══════════════════════════════════════
#  BACKGROUND CHECKER
#  Writes to triggered_col (MongoDB)
#  so the Flask request process can
#  read it — no shared memory needed
# ══════════════════════════════════════
def reminder_checker():
    print("🔁 reminder_checker thread STARTED")
    fired_this_minute = set()

    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            due = list(reminders_col.find({"time": now}))

            for r in due:
                rid = str(r["_id"])
                if rid in fired_this_minute:
                    continue
                fired_this_minute.add(rid)
                triggered_col.insert_one({"task": r["task"], "time": r["time"], "created_at": _now()})
                reminders_col.delete_one({"_id": r["_id"]})
                print(f"🔔 FIRED → {r['task']} at {now}")

            # Reset each new minute
            current_min = datetime.now().strftime("%H:%M")
            if not any(r["time"] == current_min for r in due):
                fired_this_minute.clear()

        except Exception as e:
            print(f"[checker error] {e}")

        time.sleep(10)


# Always start — gunicorn MUST use --workers 1 so this thread
# lives in the same process as HTTP handlers
threading.Thread(target=reminder_checker, daemon=True).start()
print("🔁 Reminder checker started.")

if __name__ == "__main__":
    app.run(debug=False, port=5000, use_reloader=False)