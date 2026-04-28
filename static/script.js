const chat = document.getElementById("chat");
const input = document.getElementById("msg");

if ("Notification" in window) {
    if (Notification.permission === "denied") {
        const prompt = document.getElementById("notifPrompt");
        if (prompt) {
            prompt.style.display = "block";
            prompt.innerHTML =
                "🔔 Notifications blocked. Click 🔒 in address bar → allow notifications.";
        }
    }
}

function enableNotifications() {
    Notification.requestPermission().then(permission => {
        if (permission === "granted") {
            document.getElementById("notifPrompt").style.display = "none";
        }
    });
}

function showNotification(message) {
    if (Notification.permission === "granted") {
        new Notification("⏰ Reminder", {
            body: message,
            icon: "/static/sounds/alarm.png",   // optional
            vibrate: [200, 100, 200],           // mobile vibration
            requireInteraction: true            // stays until clicked
        });
    }
}

let alarmAudio = new Audio("/static/sounds/alarm.mp3");
alarmAudio.loop = true;

// Add message
function addMessage(text, type) {
    const div = document.createElement("div");
    div.className = `msg ${type}`;
    div.innerHTML = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

// Quick buttons
function quickCommand(cmd) {
    input.value = cmd;
    sendMessage();
}

// Send message
function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addMessage(text, "user");
    input.value = "";

    fetch("/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ message: text })
    })
    .then(res => res.json())
    .then(data => addMessage(data.reply, "bot"));
}

document.getElementById("sendBtn").onclick = sendMessage;

input.addEventListener("keydown", e => {
    if (e.key === "Enter") sendMessage();
});

// Alarm trigger
setInterval(() => {
    fetch("/check_reminder")
    .then(res => res.json())
    .then(data => {
        if (data.reminder) {
            showAlarm(data.reminder);
        }
    });
}, 5000);

// Show alarm popup
function showAlarm(text) {
    document.getElementById("alarmText").innerText = text;
    document.getElementById("alarmBox").style.display = "block";

    alarmAudio.currentTime = 0;
    alarmAudio.play();

    // 🔔 Notification trigger
    showNotification(text);
}

// Stop alarm
function stopAlarm() {
    alarmAudio.pause();
    document.getElementById("alarmBox").style.display = "none";
}

// Snooze (5 min)
function snoozeAlarm(minutes) {
    const now = new Date();

    // add minutes dynamically
    now.setMinutes(now.getMinutes() + minutes);

    const hours = String(now.getHours()).padStart(2, '0');
    const mins = String(now.getMinutes()).padStart(2, '0');

    const snoozeTime = `${hours}:${mins}`;

    stopAlarm();

    // Update popup text
    document.getElementById("alarmText").innerText =
        `😴 Snoozed for ${minutes} min (until ${snoozeTime})`;

    document.getElementById("alarmBox").style.display = "block";

    // Show in chat
    addMessage(`😴 Snoozed for ${minutes} min (until ${snoozeTime})`, "bot");

    // Accurate delay
    const delay = now.getTime() - Date.now();

    setTimeout(() => {
    showAlarm("⏰ Snoozed Reminder");
    showNotification("⏰ Snoozed Reminder");
}, delay);
}

