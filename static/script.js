/* ═══════════════════════════════════════════════
   NEURAL — Frontend Logic
═══════════════════════════════════════════════ */

let sessionId   = "session_" + Date.now();
let isWaiting   = false;
let activeAlarm = null;
let recognition = null;
let isRecording = false;
let audioCtx    = null;
let alarmInterval = null;

// ── Audio unlock ───────────────────────────────
function getAudioCtx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
}
document.addEventListener("click",   () => getAudioCtx());
document.addEventListener("keydown", () => getAudioCtx());

// ── Alarm sound (Web Audio API — no autoplay block) ────────────
function playAlarmBeep() {
  try {
    const ctx = getAudioCtx();
    const t   = ctx.currentTime;
    [[880, 0], [660, 0.25]].forEach(([freq, delay]) => {
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = "sine"; osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, t + delay);
      gain.gain.linearRampToValueAtTime(0.7, t + delay + 0.05);
      gain.gain.linearRampToValueAtTime(0,   t + delay + 0.35);
      osc.start(t + delay); osc.stop(t + delay + 0.4);
    });
  } catch(e) {}
}

function startAlarmSound() {
  stopAlarmSound();
  playAlarmBeep();
  alarmInterval = setInterval(playAlarmBeep, 1200);
}
function stopAlarmSound() {
  if (alarmInterval) { clearInterval(alarmInterval); alarmInterval = null; }
}

// ── DOM ────────────────────────────────────────
const chatBox    = document.getElementById("chatBox");
const msgInput   = document.getElementById("msgInput");
const sendBtn    = document.getElementById("sendBtn");
const alarmModal = document.getElementById("alarmModal");

// ── Send ───────────────────────────────────────
function send() {
  const text = msgInput.value.trim();
  if (!text || isWaiting) return;
  clearWelcome();
  addBubble(text, "user");
  msgInput.value = ""; autoResize(msgInput);
  setWaiting(true);
  const tid = addTyping();
  fetch("/chat", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({message: text, session_id: sessionId})
  })
  .then(r => r.json())
  .then(d => { removeTyping(tid); addBubble(d.reply,"bot"); setWaiting(false); loadReminders(); loadSessions(); })
  .catch(() => { removeTyping(tid); addBubble("⚠️ Error. Try again.","bot"); setWaiting(false); });
}

function quick(cmd) { msgInput.value = cmd; send(); }

function quickTask(taskName) {
  clearWelcome();
  addBubble("add reminder","user"); setWaiting(true);
  const t1 = addTyping();
  fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:"add reminder",session_id:sessionId})})
  .then(r=>r.json()).then(d=>{
    removeTyping(t1); addBubble(d.reply,"bot");
    addBubble(taskName,"user");
    const t2=addTyping();
    fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:taskName,session_id:sessionId})})
    .then(r=>r.json()).then(d2=>{ removeTyping(t2); addBubble(d2.reply,"bot"); setWaiting(false); msgInput.focus(); loadSessions(); });
  }).catch(()=>setWaiting(false));
}

function handleKey(e) { if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();} }
function autoResize(el) { el.style.height="auto"; el.style.height=Math.min(el.scrollHeight,160)+"px"; }

// ── Bubbles ────────────────────────────────────
function clearWelcome() { const w=chatBox.querySelector(".welcome-card"); if(w)w.remove(); }

function addBubble(text, role) {
  const row=document.createElement("div"); row.className="msg-row "+role;
  const av=document.createElement("div");  av.className="bubble-avatar"; av.textContent=role==="bot"?"N":"U";
  const bub=document.createElement("div"); bub.className="bubble"; bub.innerHTML=formatText(text);
  row.appendChild(av); row.appendChild(bub); chatBox.appendChild(row);
  chatBox.scrollTop=chatBox.scrollHeight; return row;
}

function formatText(t) {
  return t.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>").replace(/\*(.+?)\*/g,"<em>$1</em>").replace(/\n/g,"<br>");
}

function addTyping() {
  const id="typing_"+Date.now(); const row=document.createElement("div");
  row.className="msg-row bot"; row.id=id;
  const av=document.createElement("div"); av.className="bubble-avatar"; av.textContent="N";
  const bub=document.createElement("div"); bub.className="typing-bubble";
  bub.innerHTML=`<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;
  row.appendChild(av); row.appendChild(bub); chatBox.appendChild(row);
  chatBox.scrollTop=chatBox.scrollHeight; return id;
}
function removeTyping(id) { const el=document.getElementById(id); if(el)el.remove(); }
function setWaiting(s) { isWaiting=s; sendBtn.disabled=s; }

// ── Reminders ──────────────────────────────────
function loadReminders() {
  fetch("/get_reminders").then(r=>r.json()).then(reminders=>{
    const list=document.getElementById("reminderList");
    const countEl=document.getElementById("reminderCount");
    countEl.textContent=reminders.length;
    if(!reminders.length){
      list.innerHTML=`<div class="empty-state"><div class="empty-icon">🗓</div><p>No reminders yet</p><small>Type "add reminder" to start</small></div>`;
      return;
    }
    list.innerHTML="";
    reminders.forEach(r=>{
      const card=document.createElement("div"); card.className="reminder-card"; card.id="card_"+r.id;
      card.innerHTML=`<div class="r-icon">🔔</div><div class="r-body"><div class="r-task" title="${r.task}">${r.task}</div><div class="r-time">${r.time}</div></div><button class="r-delete" onclick="delReminder('${r.id}')" title="Delete">✕</button>`;
      list.appendChild(card);
    });
  });
}

function delReminder(id) {
  const card=document.getElementById("card_"+id);
  if(card){card.style.opacity="0";card.style.transform="translateX(20px)";}
  setTimeout(()=>{
    fetch("/delete_reminder",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})}).then(loadReminders);
  },200);
}

// ── Alarm ──────────────────────────────────────
function showAlarm(reminder) {
  activeAlarm=reminder;
  document.getElementById("modalTask").textContent=reminder.task;
  document.getElementById("modalTime").textContent="Scheduled at "+reminder.time;
  alarmModal.classList.remove("hidden");
  startAlarmSound();
  // Notification — only works on HTTPS (Render provides this)
  if("Notification" in window && Notification.permission==="granted") {
    try {
      new Notification("🔔 Neural Reminder",{body:reminder.task+" — "+reminder.time,requireInteraction:true});
    } catch(e){}
  }
}

function stopAlarm() { stopAlarmSound(); alarmModal.classList.add("hidden"); activeAlarm=null; }

function snooze(minutes) {
  if(!activeAlarm) return;
  stopAlarmSound();
  fetch("/snooze_reminder",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:activeAlarm.id,minutes})})
  .then(()=>{ addBubble(`⏰ Snoozed for ${minutes} minutes.`,"bot"); loadReminders(); });
  alarmModal.classList.add("hidden"); activeAlarm=null;
}

// ── THE KEY FIX: send LOCAL time from browser ──
// Server is on UTC (Render), your reminders are saved in local HH:MM.
// By sending the browser's local time, timezone mismatch is impossible.
function getLocalTime() {
  const now = new Date();
  const hh  = String(now.getHours()).padStart(2,"0");
  const mm  = String(now.getMinutes()).padStart(2,"0");
  return `${hh}:${mm}`;
}

setInterval(() => {
  fetch("/check_triggered", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({now: getLocalTime()})   // ← client's local HH:MM
  })
  .then(r=>r.json())
  .then(d=>{ if(d.reminders&&d.reminders.length>0) d.reminders.forEach(r=>showAlarm(r)); })
  .catch(()=>{});
}, 3000);   // every 3s for snappy response

// ── Sessions ───────────────────────────────────
function loadSessions() {
  fetch("/get_sessions").then(r=>r.json()).then(sessions=>{
    const list=document.getElementById("sessionList"); list.innerHTML="";
    sessions.slice(0,12).forEach(s=>{
      const item=document.createElement("div");
      item.className="session-item"+(s.session_id===sessionId?" active":"");
      item.textContent=s.preview||"Conversation"; item.onclick=()=>loadSession(s.session_id);
      list.appendChild(item);
    });
  }).catch(()=>{});
}

function loadSession(sid) {
  sessionId=sid;
  fetch("/get_session/"+sid).then(r=>r.json()).then(d=>{
    chatBox.innerHTML=""; d.messages.forEach(m=>addBubble(m.text,m.role)); loadSessions();
  });
}

function newSession() {
  sessionId="session_"+Date.now();
  chatBox.innerHTML=`<div class="welcome-card"><div class="welcome-glow"></div><div class="welcome-emoji">🧠</div><h2>Hello! I'm Neural.</h2><p>Your intelligent reminder assistant.</p><div class="welcome-chips"><button onclick="quick('add reminder')">＋ Set a Reminder</button><button onclick="quick('show reminders')">📋 My Reminders</button><button onclick="quick('help')">💡 What can you do?</button></div></div>`;
  document.querySelectorAll(".session-item").forEach(el=>el.classList.remove("active"));
}

// ── Logout ─────────────────────────────────────
function logout() {
  fetch("/api/logout",{method:"POST"}).then(()=>window.location.href="/login");
}

// ── Voice ──────────────────────────────────────
function toggleVoice() {
  if(!("webkitSpeechRecognition" in window||"SpeechRecognition" in window)){addBubble("⚠️ Voice not supported. Try Chrome.","bot");return;}
  if(isRecording){recognition.stop();return;}
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  recognition=new SR(); recognition.continuous=false; recognition.interimResults=true; recognition.lang="en-US";
  recognition.onstart=()=>{isRecording=true;document.getElementById("micBtn").classList.add("recording");};
  recognition.onresult=(e)=>{msgInput.value=Array.from(e.results).map(r=>r[0].transcript).join("");autoResize(msgInput);};
  recognition.onend=()=>{isRecording=false;document.getElementById("micBtn").classList.remove("recording");if(msgInput.value.trim())send();};
  recognition.onerror=()=>{isRecording=false;document.getElementById("micBtn").classList.remove("recording");};
  recognition.start();
}

// ── Init ───────────────────────────────────────
window.onload = () => {
  loadReminders(); loadSessions();
  // Request notification permission on first load
  if("Notification" in window && Notification.permission==="default") {
    Notification.requestPermission();
  }
  // Show username in sidebar
  fetch("/api/me").then(r=>r.json()).then(d=>{
    if(d.loggedIn) {
      const el=document.querySelector(".avatar-name");
      if(el) el.textContent=d.username;
    } else {
      window.location.href="/login";
    }
  });
  msgInput.focus();
};