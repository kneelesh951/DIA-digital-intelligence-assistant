/* ARIA HUD — app.js */

window.onerror = function(msg, src, line) {
  const el = document.getElementById("log-feed");
  if (el) {
    const d = document.createElement("div");
    d.className = "log-entry error";
    d.textContent = "JS ERROR: " + msg + " (" + line + ")";
    el.appendChild(d);
  }
  return true;
};
window.addEventListener("unhandledrejection", function(ev) {
  const el = document.getElementById("log-feed");
  if (el) {
    const d = document.createElement("div");
    d.className = "log-entry error";
    d.textContent = "ASYNC: " + ev.reason;
    el.appendChild(d);
  }
});

// ── DOM refs ──────────────────────────────────────────────────────────────────
const els = {
  appName:     document.getElementById("app-name"),
  statusPill:  document.getElementById("status-pill"),
  statusText:  document.getElementById("status-text"),
  agentDock:   document.getElementById("agent-dock"),
  logFeed:     document.getElementById("log-feed"),
  coreButton:  document.getElementById("core-button"),
  coreLabel:   document.getElementById("core-label"),
  waveform:    document.getElementById("waveform"),
  textForm:    document.getElementById("text-form"),
  textInput:   document.getElementById("text-input"),
  stopBtn:     document.getElementById("stop-btn"),
  langBtns:    document.querySelectorAll(".lang-btn"),
  genderBtns:  document.querySelectorAll(".gender-btn"),
  overlay:     document.getElementById("confirm-overlay"),
  modalBadge:  document.getElementById("modal-agent-badge"),
  modalTitle:  document.getElementById("modal-title"),
  modalPlan:   document.getElementById("modal-plan"),
  modalConfirm:document.getElementById("modal-confirm"),
  modalCancel: document.getElementById("modal-cancel"),
  calFeed:     document.getElementById("calendar-feed"),
  clockEl:     document.getElementById("clock"),
  dateLine:    document.getElementById("date-line"),
  // Gauges
  cpuArc:    document.getElementById("cpu-arc"),
  ramArc:    document.getElementById("ram-arc"),
  batArc:    document.getElementById("bat-arc"),
  diskArc:   document.getElementById("disk-arc"),
  cpuVal:    document.getElementById("cpu-val"),
  ramVal:    document.getElementById("ram-val"),
  batVal:    document.getElementById("bat-val"),
  diskVal:   document.getElementById("disk-val"),
  ramDetail: document.getElementById("ram-detail"),
  diskDetail:document.getElementById("disk-detail"),
  uptimeVal: document.getElementById("uptime-val"),
  netUp:     document.getElementById("net-up"),
  netDn:     document.getElementById("net-dn"),
  // Weather
  weatherIcon: document.getElementById("weather-icon"),
  weatherTemp: document.getElementById("weather-temp"),
  weatherDesc: document.getElementById("weather-desc"),
  weatherCity: document.getElementById("weather-city"),
  // Speech bubble
  speechText:  document.getElementById("speech-text"),
  ariaSpeech:  document.getElementById("aria-speech"),
  // Ticker
  ticker:      document.getElementById("agent-ticker"),
  tickerAgent: document.getElementById("ticker-agent"),
  tickerText:  document.getElementById("ticker-text"),
};

let currentLang   = "en";
let currentGender = "female";
let activePendingId = null;
let _cmdCount = 0;

function api() { return window.pywebview.api; }

// ── Status ────────────────────────────────────────────────────────────────────
function setStatus(state, label) {
  els.statusPill.className = "status-pill " + state;
  els.statusText.textContent = label;
}

function addLog(text, type = "agent") {
  const d = document.createElement("div");
  d.className = "log-entry " + type;
  const t = new Date().toLocaleTimeString([], {hour12:false});
  d.textContent = "[" + t + "] " + text;
  els.logFeed.appendChild(d);
  els.logFeed.scrollTop = els.logFeed.scrollHeight;
}

// ── Gauge update ──────────────────────────────────────────────────────────────
const CIRC = 201.06; // 2π × 32

function setGauge(arcEl, valEl, pct, label) {
  if (!arcEl) return;
  const dash = (Math.min(pct, 100) / 100 * CIRC).toFixed(2);
  arcEl.style.setProperty("stroke-dasharray", dash + " " + CIRC);
  if (valEl) valEl.textContent = label;
}

// ── Agent dock — animated robot cards ────────────────────────────────────────
function agentCircleId(id) { return "ac-" + id; }

// Per-agent chest badge (small icon on robot body)
const AGENT_BADGE = {
  system:    "⛨",   // shield  → SENTRY
  web:       "⊕",   // globe   → SCOUT
  files:     "⊠",   // folder  → VAULT
  reminders: "◎",   // bell    → ECHO
  jobs:      "◈",   // case    → HERALD
};

function makeRobotSVG(agentId, color) {
  const badge = AGENT_BADGE[agentId] || "◉";
  // viewBox 0 0 32 44 — head at top, body, arms, legs
  return `<svg viewBox="0 0 32 44" width="36" height="49" class="robot-svg" xmlns="http://www.w3.org/2000/svg">
    <line x1="16" y1="0" x2="16" y2="5" stroke="${color}" stroke-width="1.4" stroke-linecap="round"/>
    <circle cx="16" cy="0" r="2.2" fill="${color}" class="r-antenna"/>
    <rect x="5" y="5" width="22" height="15" rx="3.5"
      fill="rgba(0,0,0,0.75)" stroke="${color}" stroke-width="1.5"/>
    <rect x="8"  y="10" width="6" height="4" rx="1.5"
      fill="${color}" class="r-eye" style="transform-origin:11px 12px"/>
    <rect x="18" y="10" width="6" height="4" rx="1.5"
      fill="${color}" class="r-eye" style="transform-origin:21px 12px"/>
    <line x1="11" y1="17.5" x2="21" y2="17.5" stroke="${color}" stroke-width="1" opacity="0.55" stroke-dasharray="2 1.5"/>
    <line x1="12" y1="20" x2="12" y2="23" stroke="${color}" stroke-width="1.6"/>
    <line x1="20" y1="20" x2="20" y2="23" stroke="${color}" stroke-width="1.6"/>
    <rect x="3" y="23" width="26" height="14" rx="3"
      fill="rgba(0,0,0,0.75)" stroke="${color}" stroke-width="1.5"/>
    <circle cx="16" cy="30" r="3.5" fill="${color}" opacity="0.4" class="r-chest"/>
    <text x="16" y="31.8" text-anchor="middle" font-size="4.5"
      fill="${color}" opacity="0.95">${badge}</text>
    <line x1="3"  y1="26" x2="-1" y2="31" stroke="${color}" stroke-width="1.8" stroke-linecap="round"/>
    <line x1="29" y1="26" x2="33" y2="31" stroke="${color}" stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="-1" cy="31" r="2" fill="${color}" opacity="0.55"/>
    <circle cx="33" cy="31" r="2" fill="${color}" opacity="0.55"/>
    <line x1="11" y1="37" x2="10" y2="44" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
    <line x1="21" y1="37" x2="22" y2="44" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
  </svg>`;
}

function renderAgentDock(agents) {
  els.agentDock.innerHTML = "";
  agents.forEach((a) => {
    const card = document.createElement("div");
    card.className = "agent-circle";
    card.id = agentCircleId(a.id);
    card.style.setProperty("--agent-color", a.color);
    card.innerHTML =
      `<div class="robot-wrap">${makeRobotSVG(a.id, a.color)}</div>` +
      `<span class="ac-name">${a.name}</span>` +
      `<span class="ac-status">IDLE</span>`;
    els.agentDock.appendChild(card);
  });
}

function setAgentState(agentId, state, label) {
  const el = document.getElementById(agentCircleId(agentId));
  if (!el) return;
  el.classList.remove("active", "done", "failed");
  if (state !== "idle") el.classList.add(state);
  el.querySelector(".ac-status").textContent = label || state.toUpperCase();
  if (state === "done" || state === "failed") {
    setTimeout(() => {
      el.classList.remove("done", "failed");
      el.querySelector(".ac-status").textContent = "IDLE";
    }, 4000);
  }
}

// ── Ticker ────────────────────────────────────────────────────────────────────
let _tickerTimer = null;
function showTicker(agentName, message) {
  els.tickerAgent.textContent = agentName;
  els.tickerText.textContent  = message;
  els.ticker.classList.add("visible");
  clearTimeout(_tickerTimer);
}
function hideTicker(delay = 5000) {
  clearTimeout(_tickerTimer);
  _tickerTimer = setTimeout(() => els.ticker.classList.remove("visible"), delay);
}

// ── Mini bar helper ───────────────────────────────────────────────────────────
function _setBar(id, pct, colorClass) {
  const el = document.getElementById(id);
  if (!el || pct == null) return;
  el.style.width = Math.min(pct, 100) + "%";
  if (colorClass) el.className = "st-bar " + colorClass;
}

// ── System stats ──────────────────────────────────────────────────────────────
async function updateStats() {
  try {
    const s = await api().get_system_stats();
    if (!s || !Object.keys(s).length) return;
    setGauge(els.cpuArc,  els.cpuVal,  s.cpu,  s.cpu + "%");
    setGauge(els.ramArc,  els.ramVal,  s.ram,  s.ram + "%");
    if (s.battery !== null && s.battery !== undefined) {
      setGauge(els.batArc, els.batVal, s.battery, s.battery + (s.charging ? "⚡" : "%"));
    }
    if (s.disk !== undefined) {
      setGauge(els.diskArc, els.diskVal, s.disk, s.disk + "%");
    }
    if (els.ramDetail)  els.ramDetail.textContent  = s.ram_used + "/" + s.ram_total + "G";
    if (els.diskDetail) els.diskDetail.textContent = (s.disk_used || "—") + "/" + (s.disk_total || "—") + "G";
    if (els.uptimeVal)  els.uptimeVal.textContent  = s.uptime || "—";
    if (els.netUp)      els.netUp.textContent       = s.net_up || "—";
    if (els.netDn)      els.netDn.textContent       = s.net_dn || "—";
    const cpuEl = document.getElementById("lf-cpu");
    const batEl = document.getElementById("lf-bat");
    if (cpuEl) cpuEl.textContent = s.cpu + "%";
    if (batEl && s.battery != null) batEl.textContent = s.battery + (s.charging ? "⚡" : "%");
    // mini bars
    _setBar("bar-cpu",  s.cpu,      "cyan");
    _setBar("bar-ram",  s.ram,      "");
    _setBar("bar-bat",  s.battery,  "gold");
    _setBar("bar-disk", s.disk,     "purple");
  } catch (e) { /* silent */ }
}

// ── Weather ───────────────────────────────────────────────────────────────────
async function updateWeather() {
  try {
    const w = await api().get_weather();
    if (!w) return;
    if (els.weatherIcon) els.weatherIcon.textContent = w.icon;
    if (els.weatherTemp) els.weatherTemp.textContent = w.temp_c + "°C";
    if (els.weatherDesc) els.weatherDesc.textContent = w.desc;
    if (els.weatherCity) els.weatherCity.textContent = w.city;
  } catch (e) { /* silent */ }
}

// ── Calendar ──────────────────────────────────────────────────────────────────
async function updateCalendar() {
  try {
    const events = await api().get_calendar_events();
    if (!els.calFeed) return;
    if (!events || events.length === 0) {
      els.calFeed.innerHTML = '<div class="cal-empty">No upcoming events · Ensure Google Calendar is synced in macOS System Settings → Internet Accounts</div>';
      return;
    }
    els.calFeed.innerHTML = events.map(e =>
      `<div class="cal-event"><div class="cal-title">${e.title}</div><div class="cal-date">${e.date}</div></div>`
    ).join("");
  } catch (e) {
    if (els.calFeed) els.calFeed.innerHTML = '<div class="cal-empty">Calendar unavailable</div>';
  }
}

// ── Clock ─────────────────────────────────────────────────────────────────────
const DAYS   = ["SUNDAY","MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY"];
const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
function updateClock() {
  const now = new Date();
  if (els.clockEl) els.clockEl.textContent = now.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
  if (els.dateLine) els.dateLine.textContent = DAYS[now.getDay()] + "  " + now.getDate() + " " + MONTHS[now.getMonth()] + " " + now.getFullYear();
}

// ── Speech bubble ─────────────────────────────────────────────────────────────
function setSpeechBubble(text) {
  if (els.speechText) els.speechText.textContent = text;
}

// ── Confirmation modal ────────────────────────────────────────────────────────
function showConfirmModal(match) {
  activePendingId = match.pending_id;
  els.modalBadge.textContent = match.agent_name;
  els.modalBadge.style.color = match.agent_color;
  els.modalTitle.textContent = "CONFIRM ACTION";
  els.modalPlan.textContent  = match.plan;
  els.overlay.classList.add("visible");
  setAgentState(match.agent_id, "active", "AWAITING");
  showTicker(match.agent_name, "AWAITING CONFIRMATION — " + match.plan);
}

function updateConfirmModal(message) {
  els.modalTitle.textContent = "FINAL CONFIRMATION";
  els.modalPlan.textContent  = message;
}

function hideConfirmModal() {
  els.overlay.classList.remove("visible");
  activePendingId = null;
}

els.modalCancel.addEventListener("click", () => {
  if (activePendingId) api().cancel(activePendingId);
  hideConfirmModal();
  hideTicker(200);
  addLog("Action aborted.", "system");
});

els.modalConfirm.addEventListener("click", async () => {
  if (!activePendingId) return;
  const pid = activePendingId;
  let result;
  try { result = await api().confirm(pid); } catch (e) { hideConfirmModal(); addLog("Confirm error: " + e, "error"); return; }
  if (!result) { hideConfirmModal(); return; }
  if (result.status === "need_second_confirmation") { updateConfirmModal(result.message); return; }
  hideConfirmModal();
  if (result.status === "executed") {
    setAgentState(result.agent_id, result.success ? "done" : "failed");
    addLog(result.agent_name + ": " + result.message, result.success ? "agent" : "error");
    if (result.message) speak(result.message);
    if (result.success) {
      showTicker(result.agent_name, "COMPLETE — " + result.message);
      hideTicker(4000);
    } else {
      showTicker(result.agent_name, "FAILED — " + result.message);
      hideTicker(5000);
    }
  }
});

// ── Command handling ──────────────────────────────────────────────────────────
async function handleCommand(text) {
  if (!text || !text.trim()) return;
  addLog(text, "user");
  setStatus("thinking", "THINKING");
  _cmdCount++;
  const hc = document.getElementById("lf-cmds");
  if (hc) hc.textContent = _cmdCount;

  let result;
  try {
    result = await api().send_text(text);
  } catch (e) {
    setStatus("idle", "IDLE");
    addLog("Bridge error: " + e, "error");
    return;
  }
  setStatus("idle", "IDLE");

  if (!result) {
    addLog("No response — check ANTHROPIC_API_KEY in .env", "error");
    setSpeechBubble("I couldn't process that. Check your API key in .env");
    return;
  }
  if (result.type === "chat") {
    if (result.message) { addLog(result.message, "agent"); speak(result.message); }
    return;
  }
  showConfirmModal(result);
}

els.textForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const t = els.textInput.value.trim();
  els.textInput.value = "";
  handleCommand(t);
});

// Stop button
els.stopBtn.addEventListener("click", () => {
  api().stop_speaking();
  addLog("Speech stopped.", "system");
  els.coreButton.classList.remove("speaking", "thinking", "listening");
  els.coreLabel.textContent = "DIA";
  document.body.dataset.state = "idle";
  setStatus("idle", "IDLE");
});

// ── Push-to-talk ──────────────────────────────────────────────────────────────
let isHolding = false;

function beginListening() {
  if (isHolding) return;
  isHolding = true;
  els.coreButton.classList.add("listening");
  els.coreLabel.textContent = "…";
  els.waveform.classList.add("active");
  setStatus("listening", "LISTENING");
  document.body.dataset.state = "listening";
  api().start_recording();
}

async function endListening() {
  if (!isHolding) return;
  isHolding = false;
  els.coreButton.classList.remove("listening");
  els.coreButton.classList.add("thinking");
  els.coreLabel.textContent = "···";
  els.waveform.classList.remove("active");
  document.body.dataset.state = "thinking";
  setStatus("thinking", "PROCESSING");
  const transcript = await api().stop_recording();
  els.coreButton.classList.remove("thinking");
  els.coreLabel.textContent = "DIA";
  document.body.dataset.state = "idle";
  setStatus("idle", "IDLE");
  if (transcript && transcript.trim()) handleCommand(transcript);
  else addLog("(no speech detected)", "system");
}

els.coreButton.addEventListener("mousedown", beginListening);
els.coreButton.addEventListener("touchstart", (e) => { e.preventDefault(); beginListening(); });
window.addEventListener("mouseup", endListening);
window.addEventListener("touchend", endListening);
window.addEventListener("keydown", (e) => {
  if (e.code === "Space" && document.activeElement !== els.textInput) {
    e.preventDefault(); beginListening();
  }
  // ESC or Cmd+. → stop DIA speaking immediately
  if (e.key === "Escape" || (e.key === "." && e.metaKey)) {
    e.preventDefault();
    api().stop_speaking();
    els.coreButton.classList.remove("speaking", "thinking", "listening");
    els.coreLabel.textContent = "DIA";
    document.body.dataset.state = "idle";
    setStatus("idle", "IDLE");
    addLog("Speech stopped.", "system");
  }
});
window.addEventListener("keyup", (e) => { if (e.code === "Space" && document.activeElement !== els.textInput) { e.preventDefault(); endListening(); } });

// ── TTS ───────────────────────────────────────────────────────────────────────
function speak(text) {
  if (!text) return;
  setSpeechBubble(text);
  els.coreButton.classList.add("speaking");
  els.coreLabel.textContent = "···";
  document.body.dataset.state = "speaking";
  setStatus("thinking", "SPEAKING");
  api().speak(text, currentLang, currentGender).then(() => {
    els.coreButton.classList.remove("speaking");
    els.coreLabel.textContent = "DIA";
    document.body.dataset.state = "idle";
    setStatus("idle", "IDLE");
  });
}

// ── Language / gender ─────────────────────────────────────────────────────────
els.langBtns.forEach((btn) => btn.addEventListener("click", () => {
  els.langBtns.forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  currentLang = btn.dataset.lang;
  api().set_voice(currentLang, currentGender);
}));

els.genderBtns.forEach((btn) => btn.addEventListener("click", () => {
  els.genderBtns.forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  currentGender = btn.dataset.gender;
  api().set_voice(currentLang, currentGender);
}));

// ── Always-on VAD callbacks ───────────────────────────────────────────────────
window.ariaAutoState = function(state) {
  document.body.dataset.state = state;
  if (state === "listening") {
    els.coreButton.classList.remove("thinking","speaking");
    els.coreButton.classList.add("listening");
    els.coreLabel.textContent = "LISTEN";
    els.waveform.classList.add("active");
    setStatus("listening", "LISTENING");
  } else if (state === "processing") {
    els.coreButton.classList.remove("listening","speaking");
    els.coreButton.classList.add("thinking");
    els.coreLabel.textContent = "···";
    els.waveform.classList.remove("active");
    setStatus("thinking", "PROCESSING");
  } else {
    els.coreButton.classList.remove("listening","thinking","speaking");
    els.coreLabel.textContent = "DIA";
    els.waveform.classList.remove("active");
    document.body.dataset.state = "idle";
    setStatus("idle", "IDLE");
  }
};

window.ariaAutoTranscript = function(text) {
  if (text && text.trim()) handleCommand(text);
};

// ── Corner HUD animation ──────────────────────────────────────────────────────
function _rnd(a, b) { return Math.floor(Math.random() * (b - a + 1)) + a; }
function _bars(n, total=5) {
  return "█".repeat(n) + "░".repeat(total - n);
}

function animateCornerHUD() {
  const nn = document.getElementById("ch-neural");
  const sy = document.getElementById("ch-sync");
  const si = document.getElementById("ch-sig");
  const la = document.getElementById("ch-lat");
  const fr = document.getElementById("ch-freq");
  const th = document.getElementById("ch-thr");
  const pk = document.getElementById("ch-pkt");

  function tick() {
    if (nn) nn.textContent = _bars(_rnd(3, 5));
    if (sy) sy.textContent = (99 + Math.random() * 0.9).toFixed(1) + "%";
    if (si) si.textContent = "▓".repeat(_rnd(3,5)) + "░".repeat(Math.max(0, 5 - _rnd(3,5)));
    if (la) la.textContent = _rnd(8, 18) + "ms";
    if (fr) fr.textContent = (_rnd(22, 28) / 10).toFixed(1) + "GHz";
    if (th) th.textContent = _rnd(95, 128) + " THz";
    if (pk) pk.textContent = _rnd(120, 999) + " pkt/s";
  }
  tick();
  setInterval(tick, 2200);
}

// ── Side data streams ─────────────────────────────────────────────────────────
function fillDataStream(elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  const HEX = "0123456789ABCDEF";
  function randHex(len) {
    let s = "";
    for (let i = 0; i < len; i++) s += HEX[Math.floor(Math.random() * 16)];
    return s;
  }
  // Mix of hex data, addresses, and status tokens
  const TOKENS = ["SYN", "ACK", "RST", "DAT", "PKT", "CHK", "OK!", "ERR", "RDY"];
  let lines = [];
  for (let i = 0; i < 80; i++) {
    const r = Math.random();
    if (r < 0.6)      lines.push(randHex(4) + " " + randHex(4));
    else if (r < 0.8) lines.push("0x" + randHex(6));
    else               lines.push(TOKENS[Math.floor(Math.random() * TOKENS.length)] + " " + randHex(3));
  }
  // Duplicate for seamless loop
  const all = [...lines, ...lines];
  const inner = document.createElement("div");
  inner.className = "ds-inner";
  inner.innerHTML = all.map(l => `<span>${l}</span>`).join("");
  el.appendChild(inner);
}

// ── Particle starfield ────────────────────────────────────────────────────────
function initParticles() {
  const canvas = document.getElementById("particles");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const COLORS = [
    "rgba(0,255,106,",    // green
    "rgba(0,229,255,",    // cyan
    "rgba(217,102,255,",  // purple
    "rgba(100,255,218,",  // teal
  ];
  let W, H, particles = [];
  function resize() { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; }
  function mkP() {
    return {
      x:Math.random()*W, y:Math.random()*H,
      r:Math.random()*1.3+0.3,
      dx:(Math.random()-.5)*.11, dy:(Math.random()-.5)*.11,
      phase:Math.random()*Math.PI*2,
      col:COLORS[Math.floor(Math.random()*COLORS.length)]
    };
  }
  function draw(ts) {
    ctx.clearRect(0,0,W,H);
    const t = ts*.001;
    for (const p of particles) {
      p.x+=p.dx; p.y+=p.dy;
      if(p.x<-5)p.x=W+5; if(p.x>W+5)p.x=-5;
      if(p.y<-5)p.y=H+5; if(p.y>H+5)p.y=-5;
      const a = .14+.7*(.5+.5*Math.sin(t*.8+p.phase));
      ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle = p.col + a.toFixed(2) + ")";
      ctx.fill();
    }
    requestAnimationFrame(draw);
  }
  resize();
  for(let i=0;i<200;i++) particles.push(mkP());
  window.addEventListener("resize", resize);
  requestAnimationFrame(draw);
}

// ── Quick actions ─────────────────────────────────────────────────────────────
async function quickAction(action) {
  try {
    const r = await api().quick_action(action);
    if (r && r.msg) { addLog(r.msg, "system"); setSpeechBubble(r.msg); }
    else if (!r || !r.ok) addLog("Action failed: " + (r && r.error || action), "error");
    else addLog(action + " executed.", "system");
  } catch (e) { addLog("Quick action error: " + e, "error"); }
}

let _isMuted = false;
function toggleMute() {
  _isMuted = !_isMuted;
  api().quick_action(_isMuted ? "mute" : "unmute");
  const btn = document.getElementById("qa-mute");
  if (btn) {
    btn.innerHTML = _isMuted ? "&#9646; UNMUTE" : "&#9658; MUTE";
    btn.classList.toggle("qa-muted", _isMuted);
  }
  addLog(_isMuted ? "Volume muted." : "Volume unmuted.", "system");
}

// ── World clocks ──────────────────────────────────────────────────────────────
const WORLD_CLOCKS = [
  { id: "wc-0", tz: "Asia/Kolkata" },
  { id: "wc-1", tz: "America/New_York" },
  { id: "wc-2", tz: "Europe/London" },
];
function updateWorldClocks() {
  const now = new Date();
  WORLD_CLOCKS.forEach(({ id, tz }) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = new Intl.DateTimeFormat("en-US", {
      timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false
    }).format(now);
  });
}

// ── Stocks ────────────────────────────────────────────────────────────────────
async function updateStocks() {
  try {
    const data = await api().get_stocks();
    const timeEl = document.getElementById("stocks-time");
    if (timeEl) {
      const now = new Date();
      timeEl.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }
    if (!data) return;
    const gEl = document.getElementById("gainers-items");
    const lEl = document.getElementById("losers-items");
    if (gEl && data.gainers) {
      gEl.innerHTML = data.gainers.slice(0, 5).map(s =>
        `<span class="ss-chip g">${s.sym} +${s.pct}%</span>`
      ).join("");
    }
    if (lEl && data.losers) {
      lEl.innerHTML = data.losers.slice(0, 5).map(s =>
        `<span class="ss-chip l">${s.sym} ${s.pct}%</span>`
      ).join("");
    }
  } catch (e) { /* silent — market may be closed */ }
}

// ── Clipboard ─────────────────────────────────────────────────────────────────
function _esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
let _lastClip = null;
async function updateClipboard() {
  try {
    const text = await api().get_clipboard();
    const el = document.getElementById("clip-feed");
    if (!el) return;
    if (!text) {
      if (_lastClip !== "") { el.innerHTML = '<span class="clip-empty">Empty</span>'; _lastClip = ""; }
      return;
    }
    if (text === _lastClip) return;
    _lastClip = text;
    const preview = text.length > 110 ? text.slice(0, 110) + "…" : text;
    el.innerHTML = `<span class="clip-text">${_esc(preview)}</span>`;
    const ask = document.createElement("span");
    ask.className = "clip-ask";
    ask.textContent = "ask DIA";
    const captured = text;
    ask.onclick = () => handleCommand("Summarize or explain this: " + captured.slice(0, 200));
    el.appendChild(ask);
  } catch (e) { /* silent */ }
}

// ── Watchlist ─────────────────────────────────────────────────────────────────
async function updateWatchlist() {
  try {
    const data = await api().get_watchlist_prices();
    const el = document.getElementById("watchlist-feed");
    if (!el) return;
    if (!data || data.length === 0) {
      el.innerHTML = '<div class="wl-empty">Say "watch AAPL" to track a stock</div>';
      return;
    }
    el.innerHTML = data.map(s => {
      const up   = s.pct >= 0;
      const cls  = up ? "wl-up" : "wl-dn";
      const sign = up ? "+" : "";
      return `<div class="wl-row">
        <span class="wl-sym">${s.sym}</span>
        <span class="wl-name">${_esc(s.name)}</span>
        <span class="wl-price">$${s.price}</span>
        <span class="wl-pct ${cls}">${sign}${s.pct}%</span>
      </div>`;
    }).join("");
  } catch (e) { /* silent */ }
}

// ── Now Playing ───────────────────────────────────────────────────────────────
let _lastTrack = "";
async function updateNowPlaying() {
  try {
    const r = await api().get_now_playing();
    const wrap = document.getElementById("now-playing");
    const sep  = document.getElementById("np-sep");
    const trk  = document.getElementById("np-track");
    if (!r || !r.track) {
      if (_lastTrack !== "") {
        if (wrap) wrap.style.display = "none";
        if (sep)  sep.style.display  = "none";
        _lastTrack = "";
      }
      return;
    }
    if (r.track !== _lastTrack) {
      _lastTrack = r.track;
      if (trk)  trk.textContent    = r.track;
      if (wrap) wrap.style.display  = "flex";
      if (sep)  sep.style.display   = "";
    }
  } catch (e) { /* silent */ }
}

// ── Focus / Pomodoro timer ────────────────────────────────────────────────────
const TIMER_WORK  = 25 * 60;
const TIMER_BREAK = 5  * 60;
let timerState    = "idle"; // idle | work | break
let timerEnd      = 0;
let timerInterval = null;

function timerToggle() {
  if (timerState === "idle") {
    timerState = "work";
    timerEnd   = Date.now() + TIMER_WORK * 1000;
    const btn  = document.getElementById("timer-btn");
    if (btn) { btn.classList.add("active"); btn.classList.remove("break"); }
    timerInterval = setInterval(timerTick, 500);
    addLog("Focus timer started — 25 minutes.", "system");
    setSpeechBubble("Focus session started. 25 minutes on the clock.");
  } else {
    timerStop();
  }
}

function timerStop() {
  timerState = "idle";
  clearInterval(timerInterval);
  timerInterval = null;
  const btn = document.getElementById("timer-btn");
  if (btn) { btn.classList.remove("active", "break"); }
  const disp = document.getElementById("timer-display");
  if (disp) disp.textContent = "25:00";
  addLog("Focus timer stopped.", "system");
}

function timerTick() {
  const rem  = Math.max(0, Math.ceil((timerEnd - Date.now()) / 1000));
  const m    = Math.floor(rem / 60);
  const s    = rem % 60;
  const disp = document.getElementById("timer-display");
  if (disp) disp.textContent = String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");

  if (rem === 0) {
    if (timerState === "work") {
      speak("Work session complete. Time for a 5 minute break.");
      timerState = "break";
      timerEnd   = Date.now() + TIMER_BREAK * 1000;
      const btn  = document.getElementById("timer-btn");
      if (btn) { btn.classList.remove("active"); btn.classList.add("break"); }
      addLog("Break time — 5 minutes.", "system");
    } else {
      speak("Break over. Starting next focus session.");
      timerState = "work";
      timerEnd   = Date.now() + TIMER_WORK * 1000;
      const btn  = document.getElementById("timer-btn");
      if (btn) { btn.classList.add("active"); btn.classList.remove("break"); }
      addLog("Next focus session started.", "system");
    }
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  try {
    initParticles();
    updateClock();
    setInterval(updateClock, 1000);

    const config = await api().get_config();
    if (!config) { addLog("Bridge config error.", "error"); return; }

    if (els.appName) els.appName.textContent = config.app_name || "ARIA";
    currentLang   = config.default_language || "en";
    currentGender = config.default_gender   || "female";

    const roster = await api().get_roster();
    if (roster) renderAgentDock(roster);

    const alwaysOn = config.activation_mode === "always_on";
    document.body.dataset.state = "idle";
    const modeEl = document.getElementById("lf-mode");
    if (modeEl) modeEl.textContent = alwaysOn ? "ALWAYS-ON" : "PUSH-TO-TALK";

    addLog((config.app_name || "DIA") + " online" + (alwaysOn ? " — speak freely." : " — press button or SPACE."), "system");
    setSpeechBubble("Systems online. " + (config.app_name || "DIA") + " is ready.");
    (config.voice_warnings || []).forEach((w) => addLog(w, "error"));

    // Sci-fi decorative elements
    animateCornerHUD();
    fillDataStream("ds-left");
    fillDataStream("ds-right");

    // World clocks — tick every second
    updateWorldClocks();
    setInterval(updateWorldClocks, 1000);

    // Load data panels
    updateStats();
    updateCalendar();
    updateWeather();
    updateStocks();
    updateWatchlist();
    updateClipboard();
    updateNowPlaying();

    // Polling intervals
    setInterval(updateStats,       10_000);   // every 10s
    setInterval(updateCalendar,   300_000);   // every 5min
    setInterval(updateWeather,    600_000);   // every 10min
    setInterval(updateStocks,     120_000);   // every 2min (market movers)
    setInterval(updateWatchlist,   60_000);   // every 60s (watchlist prices)
    setInterval(updateClipboard,    3_000);   // every 3s  (clipboard watcher)
    setInterval(updateNowPlaying,   5_000);   // every 5s  (now playing)

    // Start VAD after everything ready
    await api().start_always_on();

  } catch (err) {
    addLog("INIT ERROR: " + err, "error");
    console.error(err);
  }
}

window.addEventListener("pywebviewready", init);
