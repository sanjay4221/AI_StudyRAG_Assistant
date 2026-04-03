/**
 * app.js — v4 — Per-user docs + Streaming responses
 *
 * Key changes from v3:
 *   - handleSend() uses fetch() with ReadableStream to consume SSE
 *   - Tokens are appended to the bubble one by one as they arrive
 *   - Sources + model badge added after stream completes
 *   - Upload/documents/reset all send JWT (unchanged, Auth handles it)
 */

const API_BASE = "";   // relative — works for both localhost and 127.0.0.1
let activeSessionId = null;


/* ═══════════════════════════════════════════════════════════
   API
═══════════════════════════════════════════════════════════ */
async function apiFetch(path, options = {}) {
  options.headers = { ...Auth.headers(), ...(options.headers || {}) };
  if (options.body instanceof FormData) delete options.headers["Content-Type"];

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw { message: "Cannot reach the backend. Is uvicorn running?", status: 0 };
  }

  if (response.status === 401) { Auth.logout(); return; }
  if (response.status === 429) {
    throw { message: "⏱ Too many requests. Please wait a moment and try again.", status: 429 };
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw { message: data.detail || `Request failed (HTTP ${response.status})`, status: response.status };
  }
  return data;
}

const api = {
  health:        ()      => apiFetch("/health"),
  documents:     ()      => apiFetch("/documents"),
  models:        ()      => apiFetch("/models"),
  reset:         ()      => apiFetch("/reset", { method: "DELETE" }),
  switchModel:   model   => apiFetch("/model", { method: "POST", body: JSON.stringify({ model }) }),
  getSessions:   ()      => apiFetch("/sessions"),
  loadSession:   id      => apiFetch(`/sessions/${id}`),
  deleteSession: id      => apiFetch(`/sessions/${id}`, { method: "DELETE" }),
  upload: file => {
    const fd = new FormData();
    fd.append("file", file);
    return apiFetch("/upload", { method: "POST", body: fd });
  },
};


/* ═══════════════════════════════════════════════════════════
   TOAST
═══════════════════════════════════════════════════════════ */
let _toastTimer;
function showToast(msg, type = "info") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className   = `toast show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { t.className = "toast"; }, 3500);
}


/* ═══════════════════════════════════════════════════════════
   SESSIONS
═══════════════════════════════════════════════════════════ */
async function refreshSessions() {
  try {
    const { sessions } = await api.getSessions();
    renderSessions(sessions || []);
  } catch { renderSessions([]); }
}

function renderSessions(sessions) {
  const list = document.getElementById("sessionList");
  if (!sessions.length) {
    list.innerHTML = '<div class="session-empty">No past sessions yet</div>';
    return;
  }
  list.innerHTML = sessions.map(s => `
    <div class="session-item ${s.id === activeSessionId ? "active" : ""}" data-id="${s.id}" onclick="loadSession(${s.id})">
      <div class="session-title">${escapeHtml(s.title)}</div>
      <div class="session-meta">${formatDate(s.updated_at)}</div>
      <button class="session-delete" onclick="deleteSession(event,${s.id})" title="Delete">✕</button>
    </div>`).join("");
}

async function loadSession(sessionId) {
  try {
    const data = await api.loadSession(sessionId);
    activeSessionId = sessionId;
    const msgBox = document.getElementById("messages");
    document.getElementById("welcome")?.remove();
    msgBox.innerHTML = "";
    data.messages.forEach(m => appendBubble(m.role === "user" ? "user" : "ai", m.content, m.sources || [], m.model || ""));
    document.querySelectorAll(".session-item").forEach(el =>
      el.classList.toggle("active", parseInt(el.dataset.id) === sessionId));
    showToast(`Loaded: ${data.session_title}`, "info");
  } catch (err) { showToast(err.message || "Failed to load session", "error"); }
}

async function deleteSession(event, sessionId) {
  event.stopPropagation();
  if (!confirm("Delete this chat session?")) return;
  try {
    await api.deleteSession(sessionId);
    if (sessionId === activeSessionId) {
      activeSessionId = null;
      document.getElementById("messages").innerHTML = `
        <div class="welcome" id="welcome">
          <div class="welcome-icon">🎓</div>
          <h2>Chat with your study material</h2>
          <p>Select a past session or ask a new question.</p>
        </div>`;
    }
    await refreshSessions();
    showToast("Session deleted", "success");
  } catch (err) { showToast(err.message || "Delete failed", "error"); }
}

function newChat() {
  activeSessionId = null;
  document.getElementById("messages").innerHTML = `
    <div class="welcome" id="welcome">
      <div class="welcome-icon">🎓</div>
      <h2>New conversation</h2>
      <p>Ask a question to start a new session.</p>
    </div>`;
  document.querySelectorAll(".session-item").forEach(el => el.classList.remove("active"));
  document.getElementById("questionInput").focus();
}


/* ═══════════════════════════════════════════════════════════
   DOCS
═══════════════════════════════════════════════════════════ */
function renderDocList(docs) {
  const list = document.getElementById("docList");
  list.innerHTML = docs.length
    ? docs.map(n => `<div class="doc-item"><span class="doc-icon">📄</span><span class="doc-name">${escapeHtml(n)}</span></div>`).join("")
    : '<div class="doc-empty">No documents yet</div>';
}

async function refreshDocList() {
  try { const { documents } = await api.documents(); renderDocList(documents || []); }
  catch { renderDocList([]); }
}


/* ═══════════════════════════════════════════════════════════
   UPLOAD
═══════════════════════════════════════════════════════════ */
function initUpload() {
  const zone         = document.getElementById("uploadZone");
  const fileInput    = document.getElementById("fileInput");
  const progressWrap = document.getElementById("uploadProgress");
  const progressBar  = document.getElementById("progressBar");
  const progressLbl  = document.getElementById("progressLabel");

  zone.addEventListener("click",     () => fileInput.click());
  zone.addEventListener("dragover",  e  => { e.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", ()  => zone.classList.remove("drag"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("drag");
    const f = e.dataTransfer.files[0];
    f?.name.toLowerCase().endsWith(".pdf") ? handleUpload(f) : showToast("Please drop a PDF file", "error");
  });
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) handleUpload(fileInput.files[0]); });

  async function handleUpload(file) {
    progressWrap.style.display = "flex";
    progressBar.style.width    = "0%";
    progressLbl.textContent    = `Uploading ${file.name}…`;
    let pct = 0;
    const timer = setInterval(() => { pct = Math.min(pct + Math.random() * 9, 85); progressBar.style.width = pct + "%"; }, 200);
    try {
      const data = await api.upload(file);
      clearInterval(timer);
      progressBar.style.width = "100%";
      progressLbl.textContent = data.message;
      showToast(`✓ ${data.details.chunks} chunks from ${data.details.pages} pages`, "success");
      await refreshDocList();
    } catch (err) {
      clearInterval(timer);
      showToast(err.message || "Upload failed", "error");
    } finally {
      setTimeout(() => { progressWrap.style.display = "none"; }, 3000);
      fileInput.value = "";
    }
  }
}


/* ═══════════════════════════════════════════════════════════
   CHAT — streaming version
═══════════════════════════════════════════════════════════ */
function initChat() {
  const input   = document.getElementById("questionInput");
  const sendBtn = document.getElementById("sendBtn");

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 150) + "px";
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  });
  sendBtn.addEventListener("click", handleSend);
}

async function handleSend() {
  const input   = document.getElementById("questionInput");
  const sendBtn = document.getElementById("sendBtn");
  const question = input.value.trim();
  if (!question || sendBtn.disabled) return;

  document.getElementById("welcome")?.remove();
  input.value        = "";
  input.style.height = "auto";
  sendBtn.disabled   = true;

  appendBubble("user", question);

  // Create an empty AI bubble — we'll fill it token by token
  const aiBubble = createStreamingBubble();

  try {
    await streamChat(question, activeSessionId, aiBubble);
  } catch (err) {
    aiBubble.querySelector(".bubble-text").textContent = `⚠️ ${err.message}`;
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

async function streamChat(question, sessionId, aiBubble) {
  /**
   * Uses fetch() with a ReadableStream to consume SSE line by line.
   * Each SSE message is: "data: {...}\n\n"
   * We parse the JSON and append tokens to the bubble in real time.
   */
  const response = await fetch(`${API_BASE}/chat`, {
    method:  "POST",
    headers: Auth.headers(),
    body:    JSON.stringify({ question, session_id: sessionId || null }),
  });

  if (response.status === 401) { Auth.logout(); return; }
  if (response.status === 429) {
    throw { message: "⏱ Too many requests. Please wait a moment and try again." };
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw { message: err.detail || `Error ${response.status}` };
  }

  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buffer  = "";
  const textEl  = aiBubble.querySelector(".bubble-text");

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by double newlines
    const parts = buffer.split("\n\n");
    buffer = parts.pop();   // keep incomplete last part

    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      let payload;
      try { payload = JSON.parse(part.slice(6)); } catch { continue; }

      if (payload.session_id) {
        // First message — update active session
        activeSessionId = payload.session_id;
      } else if (payload.token) {
        // Append token to bubble
        textEl.textContent += payload.token;
        const msgBox = document.getElementById("messages");
        msgBox.scrollTop = msgBox.scrollHeight;
      } else if (payload.done) {
        // Stream complete — add sources, confidence, model badge
        finalizeBubble(aiBubble, payload.sources || [], payload.model || "", payload.confidence);
        // Render follow-up suggestions if available
        if (payload.followups?.length && typeof renderFollowups === "function") {
          const msgBox = document.getElementById("messages");
          renderFollowups(payload.followups, msgBox);
        }
        await refreshSessions();   // update sidebar title
      } else if (payload.error) {
        textEl.textContent = `⚠️ ${payload.error}`;
      }
    }
  }
}

function createStreamingBubble() {
  /**
   * Creates an AI bubble with an empty text span.
   * The span is filled token by token during streaming.
   */
  const msgBox = document.getElementById("messages");

  const wrap   = document.createElement("div");
  wrap.className = "bubble-wrap";

  const avatar = document.createElement("div");
  avatar.className  = "avatar ai";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble ai";

  // Typing dots shown while waiting for first token
  bubble.innerHTML = `
    <span class="bubble-text"></span>
    <div class="typing" id="streamTyping">
      <div class="dot"></div><div class="dot"></div><div class="dot"></div>
    </div>`;

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  msgBox.appendChild(wrap);
  msgBox.scrollTop = msgBox.scrollHeight;
  return wrap;
}

function finalizeBubble(wrap, sources, model, confidence) {
  const bubble = wrap.querySelector(".bubble");
  bubble.querySelector("#streamTyping")?.remove();

  // Source citations
  if (sources.length) {
    const srcs = document.createElement("div");
    srcs.className = "sources";
    sources.forEach(s => {
      const chip = document.createElement("span");
      chip.className  = "source-chip";
      chip.textContent = `${s.file} · p.${s.page !== undefined ? s.page + 1 : "?"}`;
      srcs.appendChild(chip);
    });
    bubble.appendChild(srcs);
  }

  // Confidence badge
  if (confidence) {
    const badge = document.createElement("div");
    badge.className = `confidence-badge confidence-${confidence.level}`;
    badge.title     = confidence.message;
    badge.textContent = confidence.label;
    bubble.appendChild(badge);
  }

  // Model badge + AI disclaimer
  const meta = document.createElement("div");
  meta.className = "bubble-meta";
  meta.innerHTML = model
    ? `⚡ ${model} &nbsp;·&nbsp; <span style="color:var(--yellow)">⚠ AI-generated — verify with source material</span>`
    : `<span style="color:var(--yellow)">⚠ AI-generated — verify with source material</span>`;
  bubble.appendChild(meta);
}

function appendBubble(role, text, sources = [], model = "") {
  /** Used for loading past sessions — non-streaming. */
  const msgBox = document.getElementById("messages");
  const isUser = role === "user";
  const wrap   = document.createElement("div");
  wrap.className = `bubble-wrap${isUser ? " user" : ""}`;
  const avatar = document.createElement("div");
  avatar.className  = `avatar ${isUser ? "usr" : "ai"}`;
  avatar.textContent = isUser ? "👤" : "🤖";
  const bubble = document.createElement("div");
  bubble.className = `bubble ${isUser ? "usr" : "ai"}`;

  const textEl = document.createElement("span");
  textEl.className  = "bubble-text";
  textEl.textContent = text;
  bubble.appendChild(textEl);

  if (sources.length) {
    const srcs = document.createElement("div");
    srcs.className = "sources";
    sources.forEach(s => {
      const chip = document.createElement("span");
      chip.className  = "source-chip";
      chip.textContent = `${s.file} · p.${s.page !== undefined ? s.page + 1 : "?"}`;
      srcs.appendChild(chip);
    });
    bubble.appendChild(srcs);
  }
  if (model && !isUser) {
    const meta = document.createElement("div");
    meta.className  = "bubble-meta";
    meta.textContent = `⚡ ${model}`;
    bubble.appendChild(meta);
  }
  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  msgBox.appendChild(wrap);
  msgBox.scrollTop = msgBox.scrollHeight;
  return wrap;
}


/* ═══════════════════════════════════════════════════════════
   RESET
═══════════════════════════════════════════════════════════ */
function initReset() {
  document.getElementById("btnReset").addEventListener("click", async () => {
    if (!confirm("Delete YOUR documents? Other users are unaffected. Chat history is kept.")) return;
    try {
      await api.reset();
      renderDocList([]);
      showToast("Your documents cleared ✓", "success");
    } catch (err) { showToast(err.message || "Reset failed", "error"); }
  });
}


/* ═══════════════════════════════════════════════════════════
   MODEL SELECTOR
═══════════════════════════════════════════════════════════ */
function initModelSelector() {
  const select = document.getElementById("modelSelect");
  select.disabled = false;
  select.addEventListener("change", async () => {
    const chosen = select.value;
    select.disabled = true;
    try {
      await api.switchModel(chosen);
      document.getElementById("modelBadge").textContent = `⚡ ${chosen}`;
      showToast(`✓ Switched to ${chosen}`, "success");
    } catch (err) {
      showToast(err.message || "Model switch failed", "error");
      await syncModelDropdown();
    } finally { select.disabled = false; }
  });
}

async function syncModelDropdown() {
  try {
    const { active, available } = await api.models();
    const select = document.getElementById("modelSelect");
    const badge  = document.getElementById("modelBadge");
    select.innerHTML = available.map(m =>
      `<option value="${m}" ${m === active ? "selected" : ""}>${m}</option>`).join("");
    badge.textContent = `⚡ ${active}`;
    badge.classList.add("visible");
  } catch { /* non-fatal */ }
}


/* ═══════════════════════════════════════════════════════════
   HEALTH + BOOT
═══════════════════════════════════════════════════════════ */
async function checkHealth() {
  const dot   = document.getElementById("statusDot");
  const label = document.getElementById("statusLabel");
  try {
    await api.health();
    dot.className     = "status-dot online";
    label.textContent = "backend online";
    document.getElementById("sendBtn").disabled = false;
    await syncModelDropdown();
    await refreshDocList();
    await refreshSessions();
  } catch {
    dot.className     = "status-dot offline";
    label.textContent = "backend offline — run uvicorn";
    setTimeout(checkHealth, 4000);
  }
}

function escapeHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month:"short", day:"numeric" })
       + " " + d.toLocaleTimeString(undefined, { hour:"2-digit", minute:"2-digit" });
}

document.addEventListener("DOMContentLoaded", () => {
  Auth.requireAuth();
  const user = Auth.getUser();

  // Set user name in topbar
  const nameEl = document.getElementById("userName");
  if (nameEl) nameEl.textContent = user.full_name || user.email;

  // Show admin button ONLY if the logged-in user is admin
  const adminBtn = document.getElementById("btnAdminPanel");
  if (adminBtn && Auth.isAdmin()) {
    adminBtn.style.display = "inline-flex";
  }

  document.getElementById("btnLogout")?.addEventListener("click", () => { if (confirm("Log out?")) Auth.logout(); });
  document.getElementById("btnNewChat")?.addEventListener("click", newChat);
  document.getElementById("btnDeleteAccount")?.addEventListener("click", deleteAccount);
  initUpload();
  initChat();
  initReset();
  initModelSelector();
  checkHealth();
});

async function deleteAccount() {
  if (!confirm(
    "⚠️ This will permanently delete your account, all chat history, and all uploaded documents.\n\nThis cannot be undone. Are you sure?"
  )) return;

  try {
    await apiFetch("/auth/account", { method: "DELETE" });
    showToast("Account deleted. Redirecting…", "success");
    setTimeout(() => { localStorage.clear(); window.location.href = "/"; }, 2000);
  } catch (err) {
    showToast(err.message || "Delete failed", "error");
  }
}
