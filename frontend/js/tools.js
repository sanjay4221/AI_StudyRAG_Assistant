/**
 * js/tools.js
 * -----------
 * Study tools UI: Quiz Generator, Document Summariser, Chat Export.
 * Loaded after auth.js and app.js in index.html.
 */

/* ═══════════════════════════════════════════════════════════
   QUIZ GENERATOR
═══════════════════════════════════════════════════════════ */

function initQuiz() {
  document.getElementById("btnQuiz")?.addEventListener("click", openQuizModal);
  document.getElementById("btnGenerateQuiz")?.addEventListener("click", generateQuiz);
  document.getElementById("btnCloseQuiz")?.addEventListener("click", closeQuizModal);
  document.getElementById("quizOverlay")?.addEventListener("click", e => {
    if (e.target === document.getElementById("quizOverlay")) closeQuizModal();
  });
}

function openQuizModal() {
  document.getElementById("quizOverlay").classList.add("open");
  document.getElementById("quizContent").innerHTML = "";
  document.getElementById("quizSettings").style.display = "block";
}

function closeQuizModal() {
  document.getElementById("quizOverlay").classList.remove("open");
}

async function generateQuiz() {
  const numQ   = parseInt(document.getElementById("quizNumQ").value) || 10;
  const diff   = document.getElementById("quizDiff").value || "medium";
  const btn    = document.getElementById("btnGenerateQuiz");
  const content = document.getElementById("quizContent");

  btn.disabled    = true;
  btn.textContent = "Generating…";
  content.innerHTML = `<div class="tool-loading">⚡ Generating ${numQ} questions…<br><small>This takes about 10-15 seconds</small></div>`;
  document.getElementById("quizSettings").style.display = "none";

  try {
    const r    = await fetch("/tools/quiz", {
      method:  "POST",
      headers: Auth.headers(),
      body:    JSON.stringify({ num_questions: numQ, difficulty: diff }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Quiz generation failed");
    renderQuiz(data);
  } catch (err) {
    content.innerHTML = `<div class="tool-error">⚠️ ${err.message}</div>`;
    document.getElementById("quizSettings").style.display = "block";
  } finally {
    btn.disabled    = false;
    btn.textContent = "Generate Quiz";
  }
}

function renderQuiz(data) {
  const content = document.getElementById("quizContent");
  let score = 0;
  let html = `
    <div class="quiz-header">
      <div class="quiz-title">${escapeHtml(data.title || "Quiz")}</div>
      <div class="quiz-meta">${data.questions?.length || 0} questions · ${data.difficulty || "medium"} difficulty</div>
    </div>`;

  (data.questions || []).forEach((q, i) => {
    html += `
      <div class="quiz-question" id="qq-${i}">
        <div class="quiz-q-text">${i + 1}. ${escapeHtml(q.question)}</div>
        <div class="quiz-options">
          ${(q.options || []).map(opt => `
            <button class="quiz-option" onclick="selectAnswer(${i}, '${opt[0]}', '${q.answer}')">
              ${escapeHtml(opt)}
            </button>`).join("")}
        </div>
        <div class="quiz-explanation" id="exp-${i}" style="display:none">
          ✓ ${escapeHtml(q.explanation || "")}
        </div>
      </div>`;
  });

  html += `<div class="quiz-actions">
    <button class="btn-tool secondary" onclick="resetQuiz()">↺ Retake</button>
    <button class="btn-tool" onclick="exportQuiz(${JSON.stringify(data).replace(/"/g, '&quot;')})">⬇ Export Quiz</button>
  </div>`;

  content.innerHTML = html;
}

function selectAnswer(qIdx, selected, correct) {
  const options = document.querySelectorAll(`#qq-${qIdx} .quiz-option`);
  options.forEach(btn => {
    btn.disabled = true;
    const letter = btn.textContent.trim()[0];
    if (letter === correct) btn.classList.add("correct");
    else if (letter === selected && selected !== correct) btn.classList.add("wrong");
  });
  document.getElementById(`exp-${qIdx}`).style.display = "block";
}

function resetQuiz() {
  document.getElementById("quizContent").innerHTML = "";
  document.getElementById("quizSettings").style.display = "block";
}

function exportQuiz(data) {
  const lines = [`${data.title}\n${"=".repeat(data.title.length)}\n`];
  (data.questions || []).forEach((q, i) => {
    lines.push(`${i + 1}. ${q.question}`);
    (q.options || []).forEach(o => lines.push(`   ${o}`));
    lines.push(`   Answer: ${q.answer}`);
    lines.push(`   ${q.explanation}\n`);
  });
  downloadText(lines.join("\n"), `${data.title || "quiz"}.txt`);
}


/* ═══════════════════════════════════════════════════════════
   DOCUMENT SUMMARISER
═══════════════════════════════════════════════════════════ */

function initSummarise() {
  document.getElementById("btnSummarise")?.addEventListener("click", generateSummary);
  document.getElementById("btnCloseSummary")?.addEventListener("click", closeSummaryModal);
  document.getElementById("summaryOverlay")?.addEventListener("click", e => {
    if (e.target === document.getElementById("summaryOverlay")) closeSummaryModal();
  });
}

function closeSummaryModal() {
  document.getElementById("summaryOverlay").classList.remove("open");
}

async function generateSummary() {
  const overlay = document.getElementById("summaryOverlay");
  const content = document.getElementById("summaryContent");
  overlay.classList.add("open");
  content.innerHTML = `<div class="tool-loading">📖 Analysing your documents…<br><small>This takes about 15-20 seconds</small></div>`;

  try {
    const r    = await fetch("/tools/summarise", {
      method:  "POST",
      headers: Auth.headers(),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Summarise failed");
    renderSummary(data);
  } catch (err) {
    content.innerHTML = `<div class="tool-error">⚠️ ${err.message}</div>`;
  }
}

function renderSummary(data) {
  const content = document.getElementById("summaryContent");
  content.innerHTML = `
    <div class="summary-title">${escapeHtml(data.title || "Document Summary")}</div>

    <div class="summary-section">
      <div class="summary-label">📋 Overview</div>
      <p>${escapeHtml(data.overview || "")}</p>
    </div>

    <div class="summary-section">
      <div class="summary-label">🔑 Key Concepts</div>
      <div class="tag-list">
        ${(data.key_concepts || []).map(c => `<span class="tag">${escapeHtml(c)}</span>`).join("")}
      </div>
    </div>

    <div class="summary-section">
      <div class="summary-label">📖 Key Definitions</div>
      ${(data.definitions || []).map(d => `
        <div class="definition-row">
          <strong>${escapeHtml(d.term)}</strong> — ${escapeHtml(d.definition)}
        </div>`).join("")}
    </div>

    <div class="summary-section">
      <div class="summary-label">🎯 Likely Exam Topics</div>
      <ul class="summary-list">
        ${(data.exam_topics || []).map(t => `<li>${escapeHtml(t)}</li>`).join("")}
      </ul>
    </div>

    <div class="summary-section">
      <div class="summary-label">💡 Study Tips</div>
      <ul class="summary-list tips">
        ${(data.study_tips || []).map(t => `<li>${escapeHtml(t)}</li>`).join("")}
      </ul>
    </div>

    <div class="summary-actions">
      <button class="btn-tool" onclick="exportSummary(${JSON.stringify(data).replace(/"/g, '&quot;')})">⬇ Export Summary</button>
      <button class="btn-tool secondary" onclick="closeSummaryModal()">Close</button>
    </div>`;
}

function exportSummary(data) {
  const lines = [
    data.title, "=".repeat(data.title?.length || 20), "",
    "OVERVIEW", data.overview, "",
    "KEY CONCEPTS", (data.key_concepts || []).join(", "), "",
    "KEY DEFINITIONS",
    ...(data.definitions || []).map(d => `${d.term}: ${d.definition}`), "",
    "LIKELY EXAM TOPICS",
    ...(data.exam_topics || []).map((t, i) => `${i + 1}. ${t}`), "",
    "STUDY TIPS",
    ...(data.study_tips || []).map((t, i) => `${i + 1}. ${t}`),
  ];
  downloadText(lines.join("\n"), `${data.title || "summary"}.txt`);
}


/* ═══════════════════════════════════════════════════════════
   FOLLOW-UP SUGGESTIONS (called from app.js after each answer)
═══════════════════════════════════════════════════════════ */

function renderFollowups(followups, msgBox) {
  if (!followups || !followups.length) return;

  const container = document.createElement("div");
  container.className = "followup-container";

  const label = document.createElement("div");
  label.className   = "followup-label";
  label.textContent = "💡 You might also ask:";
  container.appendChild(label);

  const pills = document.createElement("div");
  pills.className = "followup-pills";

  followups.forEach(q => {
    const pill = document.createElement("button");
    pill.className   = "followup-pill";
    pill.textContent = q;
    pill.onclick     = () => {
      document.getElementById("questionInput").value = q;
      document.getElementById("questionInput").focus();
      // Auto-remove suggestions once clicked
      container.remove();
    };
    pills.appendChild(pill);
  });

  container.appendChild(pills);
  msgBox.appendChild(container);
  msgBox.scrollTop = msgBox.scrollHeight;
}


/* ═══════════════════════════════════════════════════════════
   CHAT EXPORT (Feature 5 — frontend only, no backend needed)
═══════════════════════════════════════════════════════════ */

function exportChat() {
  const msgBox  = document.getElementById("messages");
  const bubbles = msgBox.querySelectorAll(".bubble-wrap");

  if (!bubbles.length) {
    showToast("No messages to export", "error");
    return;
  }

  const lines = [
    "StudyRAG — Chat Export",
    `Exported: ${new Date().toLocaleString()}`,
    "=".repeat(40), "",
  ];

  bubbles.forEach(wrap => {
    const isUser  = wrap.classList.contains("user");
    const textEl  = wrap.querySelector(".bubble-text");
    const content = textEl?.textContent?.trim() || "";
    if (!content) return;

    lines.push(isUser ? "STUDENT:" : "STUDYRAG:");
    lines.push(content);

    // Include sources if present
    const chips = wrap.querySelectorAll(".source-chip");
    if (chips.length) {
      lines.push(`Sources: ${[...chips].map(c => c.textContent).join(", ")}`);
    }
    lines.push("");
  });

  downloadText(lines.join("\n"), `studyrag-chat-${Date.now()}.txt`);
  showToast("Chat exported ✓", "success");
}


/* ═══════════════════════════════════════════════════════════
   HELPERS
═══════════════════════════════════════════════════════════ */

function downloadText(text, filename) {
  const blob = new Blob([text], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initQuiz();
  initSummarise();
  document.getElementById("btnExportChat")?.addEventListener("click", exportChat);
});
