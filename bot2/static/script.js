let audioContext;
let alarmReady=false;

function unlockAudio(){
    if(!alarmReady){
        audioContext=new (window.AudioContext || window.webkitAudioContext)();
        audioContext.resume();
        alarmReady=true;
        console.log("Audio unlocked");
    }
}

document.addEventListener("click",unlockAudio,{once:true});

function playAlarm() {
    if (!alarmReady) {
        console.log("Audio not unlocked yet");
        return;
    }

    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, audioContext.currentTime);

    gainNode.gain.setValueAtTime(0.5, audioContext.currentTime);

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.start();
    oscillator.stop(audioContext.currentTime + 2);
}

document.addEventListener("DOMContentLoaded", function () {

    document.getElementById("enableNotifications").addEventListener("click",function(){
        if("Notification" in window){
            Notification.requestPermission().then(permission=>{
                console.log("permission result:",permission);
            });
        }
    });

    document.body.addEventListener("click",()=>{
        new Audio().play().catch(()=>{});
    });

    if("Notification" in window && Notification.permission==="default"){
        Notification.requestPermission().then(permission=>{
            console.log("Notification permission:",permission)
        });
    }

    console.log("✅ script.js running after DOM load");

    const sendBtn = document.getElementById("sendBtn");
    const input = document.getElementById("msg");
    const chat = document.getElementById("chat");

    const notifyBtn=document.getElementById("enableNotifications");

    function updateNotificationButton(){
        if(Notification.permission==="granted"){
            notifyBtn.style.display="none";
        }else{
            notifyBtn.style.display="inline-block";
        }
    }

    updateNotificationButton();

    notifyBtn.addEventListener("click",function(){
        Notification.requestPermission().then(function(permission){
            console.log("Permission result:",permission);
            if(permission==="granted"){
                notifyBtn.style.display="none";
            }
        });
    });


    // Safety check
    if (!sendBtn || !input || !chat) {
        console.error("❌ DOM elements not found");
        return;
    }

    sendBtn.addEventListener("click", sendMessage);

    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });

    function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // Show user message
        chat.innerHTML += `<div class="user msg">${text}</div>`;

        // Send to backend
        fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ message: text })
        })
        .then(response => response.json())
        .then(data => {
            chat.innerHTML += `<div class="bot msg">${data.reply}</div>`;
            // playBeep();
            chat.scrollTop = chat.scrollHeight;
        })
        .catch(err => {
            console.error(err);
            chat.innerHTML += `<div class="bot msg">⚠️ Server error</div>`;
        });

        
        input.value = "";
    }
    setInterval(() => {
    fetch("/check_reminder")
        .then(res => res.json())
        .then(data => {
            if (data.reminder) {
                chat.innerHTML += `<div class="bot msg">🔔 Reminder: ${data.reminder}</div>`;
                playAlarm();
                if(Notification.permission==="granted"){
                    new Notification("Reminder",{
                        body:data.reminder
                    });
                }
                chat.scrollTop = chat.scrollHeight;
            }
        })
}, 5000); // check every 5 seconds

function showDesktopNotification(message){
    if(Notification.permission==="granted"){
        new Notification("Reminder Alert",{
            body:message,
            icon:"https://cdn-icons-png.flaticon.com/512/1827/1827392.png"
        });
    }
}

// const notifyBtn=document.getElementById("enableNotifications");

// function updateNotificationButton(){
//     if(Nortification.permission==="granted"){
//         notifyBtn.style.display="none";
//     }else{
//         notifyBtn.style.display="inline-block";
//     }
// }

updateNotificationButton();

});