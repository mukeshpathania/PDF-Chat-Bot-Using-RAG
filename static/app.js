/* ── DocMind app.js ───────────────────────────────────
   Handles PDF upload + RAG chat
─────────────────────────────────────────────────────── */

const API = '';

// ── DOM refs ──────────────────────────────────────────
const dropZone      = document.getElementById('dropZone');
const fileInput     = document.getElementById('fileInput');
const stateIdle     = document.getElementById('stateIdle');
const stateLoading  = document.getElementById('stateLoading');
const stateSuccess  = document.getElementById('stateSuccess');
const stateError    = document.getElementById('stateError');
const successMsg    = document.getElementById('successMsg');
const errorMsg      = document.getElementById('errorMsg');

const messages      = document.getElementById('messages');
let   emptyState    = document.getElementById('emptyState');
const chatSub       = document.getElementById('chatSub');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const clearBtn      = document.getElementById('clearBtn');
const chipsContainer= document.getElementById('chipsContainer');

let docLoaded = false;
let currentFilename = ''; // Server-normalized filename — always matches ChromaDB index
let chatHistory = [];    // Conversation memory: [{role, content}, ...]

/* ══════════════════════════════════════════════════════
   UPLOAD
══════════════════════════════════════════════════════ */

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file && file.type === 'application/pdf') uploadFile(file);
  else setStatus('error', 'Please drop a valid PDF file.');
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
  setStatus('loading');
  const form = new FormData();
  form.append('file', file);

  try {
    const res = await fetch(`${API}/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();

    // Use the server-returned filename — it's been normalized (e.g. extra spaces
    // collapsed) so it will always match what's stored in ChromaDB.
    currentFilename = data.filename || file.name;

    setStatus('success', `"${currentFilename}" — ${data.chunks} chunks`);
    docLoaded = true;
    enableChat();
    chatSub.textContent = currentFilename;

    // Clear previous chat so old answers from another doc don't linger
    chatHistory = [];
    clearChat(currentFilename);

  } catch (err) {
    setStatus('error', err.message || 'Upload failed');
  }
}

function setStatus(state, msg = '') {
  [stateIdle, stateLoading, stateSuccess, stateError].forEach(el => el.classList.add('hidden'));
  if (state === 'idle')    stateIdle.classList.remove('hidden');
  if (state === 'loading') stateLoading.classList.remove('hidden');
  if (state === 'success') { stateSuccess.classList.remove('hidden'); successMsg.textContent = msg; }
  if (state === 'error')   { stateError.classList.remove('hidden');   errorMsg.textContent   = msg; }
}

/* ══════════════════════════════════════════════════════
   CHAT ENABLE
══════════════════════════════════════════════════════ */

function enableChat() {
  questionInput.disabled = false;
  sendBtn.disabled = true; // still disabled until user types
  questionInput.focus();
}

/* ══════════════════════════════════════════════════════
   TEXTAREA BEHAVIOUR
══════════════════════════════════════════════════════ */

questionInput.addEventListener('input', () => {
  // auto-resize
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 140) + 'px';
  sendBtn.disabled = !questionInput.value.trim() || !docLoaded;
});

questionInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) askQuestion();
  }
});

sendBtn.addEventListener('click', askQuestion);

/* ══════════════════════════════════════════════════════
   CHIPS
══════════════════════════════════════════════════════ */

function bindChips(container) {
  container.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (!docLoaded) return;
      questionInput.value = chip.dataset.q;
      questionInput.dispatchEvent(new Event('input'));
      askQuestion();
    });
  });
}

if (chipsContainer) bindChips(chipsContainer);

/* ══════════════════════════════════════════════════════
   ASK QUESTION
══════════════════════════════════════════════════════ */

async function askQuestion() {
  const q = questionInput.value.trim();
  if (!q || !docLoaded) return;

  // clear input
  questionInput.value = '';
  questionInput.style.height = 'auto';
  sendBtn.disabled = true;

  // remove empty state
  emptyState && emptyState.remove();

  appendMsg('user', q);
  const typingId = appendTyping();

  try {
    // Use the authoritative server-normalized filename, not the DOM text
    const res = await fetch(`${API}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: q,
        filename: currentFilename,
        chat_history: chatHistory,
        ...getModelSettings(),
      }),
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);
    appendMsg('ai', data.answer);

    // Save this Q&A turn to memory for follow-up context
    chatHistory.push({ role: 'user',      content: q });
    chatHistory.push({ role: 'assistant', content: data.answer });

  } catch (err) {
    removeTyping(typingId);
    appendMsg('ai', `⚠️ ${err.message || 'Something went wrong'}`, true);
  }
}

/* ══════════════════════════════════════════════════════
   MESSAGE HELPERS
══════════════════════════════════════════════════════ */

function appendMsg(role, text, isError = false) {
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.innerHTML = role === 'user'
    ? `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="6" r="3" fill="white"/>
        <path d="M2 13.5c0-2.76 2.686-5 6-5s6 2.24 6 5" stroke="white" stroke-width="1.4" stroke-linecap="round"/>
       </svg>`
    : `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M3 4h10M3 8h7M3 12h8" stroke="#888" stroke-width="1.5" stroke-linecap="round"/>
       </svg>`;

  const bubble = document.createElement('div');
  bubble.className = `msg-bubble${isError ? ' error' : ''}`;
  bubble.innerHTML = esc(text).replace(/\n/g, '<br>');

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollBottom();
}

function appendTyping() {
  const id = `t-${Date.now()}`;
  const row = document.createElement('div');
  row.className = 'msg-row ai';
  row.id = id;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M3 4h10M3 8h7M3 12h8" stroke="#888" stroke-width="1.5" stroke-linecap="round"/>
   </svg>`;

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollBottom();
  return id;
}

function removeTyping(id) { document.getElementById(id)?.remove(); }

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function scrollBottom() {
  messages.scrollTop = messages.scrollHeight;
}

/* ══════════════════════════════════════════════════════
   CLEAR HELPERS
══════════════════════════════════════════════════════ */

/**
 * Wipes the chat panel and rebuilds the empty-state placeholder.
 * Pass a filename to show a doc-specific message, or omit for the
 * generic "Upload a PDF" prompt.
 */
function clearChat(filename = '') {
  messages.innerHTML = '';

  const bodyText = filename
    ? `Ask questions about <strong>${esc(filename)}</strong>. Answers come only from the document.`
    : 'Upload a PDF and start asking questions.';

  const empty = document.createElement('div');
  empty.id = 'emptyState';
  empty.className = 'empty-state';
  empty.innerHTML = `
    <div class="empty-glow"></div>
    <div class="empty-icon">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <path d="M8 8h12M8 13h8M8 18h10" stroke="#888" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
    </div>
    <h2>Chat with your document</h2>
    <p>${bodyText}</p>
    <div class="chips" id="chipsContainerCleared">
      <button class="chip" data-q="Summarize this document in a few sentences">📄 Summarize</button>
      <button class="chip" data-q="What are the key points discussed?">🔑 Key points</button>
      <button class="chip" data-q="What skills or technologies are mentioned?">⚙️ Skills</button>
      <button class="chip" data-q="What is the main topic of this document?">🎯 Main topic</button>
    </div>`;
  messages.appendChild(empty);
  emptyState = empty;
  bindChips(document.getElementById('chipsContainerCleared'));
}

clearBtn.addEventListener('click', () => {
  const currentFile = docLoaded ? chatSub.textContent : '';
  chatHistory = [];
  clearChat(currentFile);
});


/* ══════════════════════════════════════════════════════
   MODEL SETTINGS PANEL
══════════════════════════════════════════════════════ */

const settingsToggle = document.getElementById('settingsToggle');
const settingsBody   = document.getElementById('settingsBody');
const settingModel   = document.getElementById('settingModel');
const settingTemp    = document.getElementById('settingTemp');
const settingTokens  = document.getElementById('settingTokens');
const settingK       = document.getElementById('settingK');
const settingTopN    = document.getElementById('settingTopN');
const settingsReset  = document.getElementById('settingsReset');
const activeModelLabel = document.getElementById('activeModelLabel');

// Friendly display names for the model tag
const MODEL_LABELS = {
  'llama-3.3-70b-versatile': 'LLaMA 3.3 70B · Groq',
  'llama-3.1-8b-instant':    'LLaMA 3.1 8B · Groq',
  'gemma2-9b-it':            'Gemma 2 9B · Groq',
  'mixtral-8x7b-32768':      'Mixtral 8x7B · Groq',
};

// Defaults
const DEFAULTS = { model: 'llama-3.3-70b-versatile', temp: 0.7, tokens: 512, k: 8, topN: 3 };

// Toggle open/close
settingsToggle.addEventListener('click', () => {
  const isOpen = settingsBody.classList.toggle('open');
  settingsToggle.classList.toggle('open', isOpen);
  settingsToggle.setAttribute('aria-expanded', isOpen);
});

// Live slider labels
settingTemp.addEventListener('input', () => {
  document.getElementById('tempVal').textContent = parseFloat(settingTemp.value).toFixed(2);
});
settingTokens.addEventListener('input', () => {
  document.getElementById('tokensVal').textContent = settingTokens.value;
});
settingK.addEventListener('input', () => {
  document.getElementById('kVal').textContent = settingK.value;
});
settingTopN.addEventListener('input', () => {
  document.getElementById('topNVal').textContent = settingTopN.value;
});

// Update model tag when model changes
settingModel.addEventListener('change', () => {
  activeModelLabel.textContent = MODEL_LABELS[settingModel.value] || settingModel.value;
});

// Reset to defaults
settingsReset.addEventListener('click', () => {
  settingModel.value  = DEFAULTS.model;
  settingTemp.value   = DEFAULTS.temp;
  settingTokens.value = DEFAULTS.tokens;
  settingK.value      = DEFAULTS.k;
  settingTopN.value   = DEFAULTS.topN;
  document.getElementById('tempVal').textContent   = DEFAULTS.temp.toFixed(2);
  document.getElementById('tokensVal').textContent = DEFAULTS.tokens;
  document.getElementById('kVal').textContent      = DEFAULTS.k;
  document.getElementById('topNVal').textContent   = DEFAULTS.topN;
  activeModelLabel.textContent = MODEL_LABELS[DEFAULTS.model];
});

/** Returns the current settings object to attach to every /query request */
function getModelSettings() {
  return {
    llm_model:    settingModel.value,
    temperature:  parseFloat(settingTemp.value),
    max_tokens:   parseInt(settingTokens.value, 10),
    retrieval_k:  parseInt(settingK.value, 10),
    rerank_top_n: parseInt(settingTopN.value, 10),
  };
}
