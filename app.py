from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
import pytz
import os
import re

# Load env
load_dotenv()

app = Flask(__name__)

tz = pytz.timezone("Asia/Kolkata")
now = datetime.now(tz).strftime("%H:%M")

# MongoDB connection
try:
    client = MongoClient(
        os.getenv("MONGO_URI"),
        serverSelectionTimeoutMS=5000
    )
    client.server_info()
    print("✅ MongoDB Connected")
except Exception as e:
    print("❌ MongoDB Connection Failed:", e)

db = client["chatbot_db"]
reminders_collection = db["reminders"]

# Conversation state
user_state = {"step": None, "task": None}


# ===================== PARSERS =====================

# Format: remind me to study at 21:30
def parse_reminder(message):
    pattern = r"remind me to (.+) at (\d{1,2}:\d{2})"
    match = re.search(pattern, message)

    if match:
        task = match.group(1)
        time = match.group(2)

        try:
            datetime.strptime(time, "%H:%M")
            return task, time
        except:
            return None

    return None


# Format: remind me in 5 minutes
def parse_in_minutes(message):
    match = re.search(r"remind me in (\d+) minute", message)

    if match:
        minutes = int(match.group(1))
        now = datetime.now()
        future = now + timedelta(minutes=minutes)

        time = future.strftime("%H:%M")
        task = "Reminder"

        return task, time

    return None


# ===================== ROUTES =====================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"].lower()

    # 🔥 Smart parsing (AI-like behavior)
    parsed = parse_reminder(user_message)

    if not parsed:
        parsed = parse_in_minutes(user_message)

    if parsed:
        task, time = parsed

        reminders_collection.insert_one({
            "task": task,
            "time": time
        })

        return jsonify(reply=f"✅ Reminder set: {task} at {time}")

    # Manual flow fallback
    if user_message == "add reminder":
        user_state["step"] = "task"
        return jsonify(reply="What should I remind you about?")

    if user_state["step"] == "task":
        user_state["task"] = user_message
        user_state["step"] = "time"
        return jsonify(reply="When should I remind you? (HH:MM)")

    if user_state["step"] == "time":
        try:
            datetime.strptime(user_message, "%H:%M")

            reminders_collection.insert_one({
                "task": user_state["task"],
                "time": user_message
            })

            user_state["step"] = None
            return jsonify(reply="✅ Reminder set successfully!")

        except:
            return jsonify(reply="❌ Please enter time in HH:MM format.")

    # Show reminders
    if user_message == "show reminders":
        all_reminders = list(reminders_collection.find())

        if len(all_reminders) == 0:
            return jsonify(reply="You have no reminders.")

        reply = "📋 Your reminders:<br>"
        for r in all_reminders:
            reply += f"• {r['task']} at {r['time']}<br>"

        return jsonify(reply=reply)

    return jsonify(reply="I can help you set reminders. Try 'remind me to study at 21:00'")


@app.route("/check_reminder")
def check_reminder():
    from datetime import datetime
    import pytz

    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz).strftime("%H:%M")

    reminder = reminders_collection.find_one({
        "time": {"$lte": now}
    })

    if reminder:
        reminders_collection.delete_one({"_id": reminder["_id"]})
        return jsonify(reminder=reminder["task"])

    return jsonify(reminder=None)


# ===================== RUN =====================

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000)