from flask import Flask, render_template, request, jsonify
from datetime import datetime
import threading
import time

app = Flask(__name__)

triggered_reminder=None
reminders = []
user_state = {"step": None, "task": None}

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/check_reminder")
def check_reminder():
    now=datetime.now().strftime("%H:%M")

    for reminder in reminders:
        if reminder[1] == now:
            reminders.remove(reminder)
            return jsonify(reminder=reminder[0])
    
    return jsonify(reminder=None)

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"].lower()

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
            reminders.append((user_state["task"], user_message))
            user_state["step"] = None
            return jsonify(reply="✅ Reminder set successfully!")
        except:
            return jsonify(reply="❌ Please enter time in HH:MM format.")

    if user_message == "show reminders":
        if not reminders:
            return jsonify(reply="You have no reminders.")
        reply = "📋 Your reminders:<br>"
        for r in reminders:
            reply += f"• {r[0]} at {r[1]}<br>"
        return jsonify(reply=reply)

    return jsonify(reply="I can help you set reminders. Type 'add reminder'.")

def check_reminder():
    global triggered_reminder
    if triggered_reminder:
        msg=triggered_reminder
        triggered_reminder=None
        return jsonify(reminder=msg)
    return jsonify(reminder=None)

def reminder_checker():
    global triggered_reminder
    while True:
        now = datetime.now().strftime("%H:%M")
        for reminder in reminders:
            if reminder[1] == now:
                print(f"\n⏰ REMINDER: {reminder[0]}")
                reminders.remove(reminder)
        time.sleep(60)

threading.Thread(target=reminder_checker, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)