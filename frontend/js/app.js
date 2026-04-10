// ── Config ────────────────────────────────────────────────────────────────────
// Change this to your Render backend URL when deploying.
// Leave empty to use the same origin (only works if frontend and backend are served together).
const API_BASE = 'https://lmu-setup-engineer.onrender.com';

// ── State ─────────────────────────────────────────────────────────────────────
let selectedFile = null;
let allLaps = [];          // populated after first successful analysis
let lastLapIndex = null;   // the lap index used in the last analysis

// ── DOM refs ──────────────────────────────────────────────────────────────────
const dropZone    = document.getElementById('dropZone');
const fileInput   = document.getElementById('fileInput');
const fileChosen  = document.getElementById('fileChosen');
const fileName    = document.getElementById('fileName');
const fileClear   = document.getElementById('fileClear');
const lapSelector = document.getElementById('lapSelector');
const lapSelect   = document.getElementById('lapSelect');
const description = document.getElementById('description');
const charCount   = document.getElementById('charCount');
const errorBanner = document.getElementById('errorBanner');
const submitBtn   = document.getElementById('submitBtn');
const results     = document.getElementById('results');
const sessionStrip = document.getElementById('sessionStrip');
const lapBadge    = document.getElementById('lapBadge');
const adviceBody  = document.getElementById('adviceBody');

// ── File handling ─────────────────────────────────────────────────────────────
function setFile(file) {
  if (!file || !file.name.toLowerCase().endsWith('.ld')) {
    showError('Only .ld files are supported.');
    return;
  }
  selectedFile = file;
  fileName.textContent = file.name;
  fileChosen.classList.add('visible');
  hideError();
  updateSubmitState();
}

function clearFile() {
  selectedFile = null;
  fileInput.value = '';
  fileChosen.classList.remove('visible');
  lapSelector.classList.remove('visible');
  lapSelect.innerHTML = '';
  allLaps = [];
  lastLapIndex = null;
  updateSubmitState();
}

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
});

fileClear.addEventListener('click', (e) => {
  e.stopPropagation();
  clearFile();
});

// Drag and drop
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});

// ── Character counter ─────────────────────────────────────────────────────────
description.addEventListener('input', () => {
  const len = description.value.length;
  charCount.textContent = `${len} / 1000`;
  charCount.classList.toggle('warn', len > 900);
  updateSubmitState();
});

// ── Submit state ──────────────────────────────────────────────────────────────
function updateSubmitState() {
  const ready = selectedFile !== null && description.value.trim().length > 0;
  submitBtn.disabled = !ready;
}

// ── Error banner ──────────────────────────────────────────────────────────────
function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.classList.add('visible');
}

function hideError() {
  errorBanner.classList.remove('visible');
}

// ── Lap selector ──────────────────────────────────────────────────────────────
function populateLapSelector(laps, selectedIndex) {
  lapSelect.innerHTML = '';
  laps.forEach((lap) => {
    const opt = document.createElement('option');
    opt.value = lap.index;
    opt.textContent = `Lap ${lap.lap_number}  —  ${lap.lap_time_str}`;
    if (lap.index === selectedIndex) opt.selected = true;
    lapSelect.appendChild(opt);
  });
  lapSelector.classList.add('visible');
}

// ── Markdown → HTML ───────────────────────────────────────────────────────────
// Simple converter for the subset Gemini typically outputs.
function markdownToHtml(text) {
  const lines = text.split('\n');
  const out = [];
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Inline formatting first (applied to every line)
    line = line
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+?)\*/g,  '<em>$1</em>');

    // Headings
    if (/^###\s/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3>${line.replace(/^###\s/, '')}</h3>`);
      continue;
    }
    if (/^##\s/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2>${line.replace(/^##\s/, '')}</h2>`);
      continue;
    }

    // Bullet list items (- or *)
    if (/^[-*]\s/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${line.replace(/^[-*]\s/, '')}</li>`);
      continue;
    }

    // Numbered list items
    if (/^\d+\.\s/.test(line)) {
      if (!inList) { out.push('<ol>'); inList = true; }
      out.push(`<li>${line.replace(/^\d+\.\s/, '')}</li>`);
      continue;
    }

    // End list on blank line or non-list line
    if (inList) { out.push('</ul>'); inList = false; }

    // Blank lines become paragraph breaks (skip double-blanks)
    if (line.trim() === '') {
      continue;
    }

    out.push(`<p>${line}</p>`);
  }

  if (inList) out.push('</ul>');
  return out.join('\n');
}

// ── Session strip ─────────────────────────────────────────────────────────────
function renderSessionStrip(session, lap) {
  sessionStrip.innerHTML = [
    { label: 'Driver',   value: session.driver },
    { label: 'Car',      value: session.vehicle },
    { label: 'Track',    value: session.venue },
    { label: 'Lap',      value: `Lap ${lap.lap_number}`, accent: true },
    { label: 'Lap time', value: lap.lap_time_str, accent: true },
  ].map(({ label, value, accent }) => `
    <div class="session-cell">
      <div class="session-cell-label">${label}</div>
      <div class="session-cell-value${accent ? ' accent' : ''}">${value || '—'}</div>
    </div>
  `).join('');
}

// ── Submit ────────────────────────────────────────────────────────────────────
submitBtn.addEventListener('click', runAnalysis);

async function runAnalysis() {
  hideError();
  setLoading(true);

  const formData = new FormData();
  formData.append('file', selectedFile);
  formData.append('description', description.value.trim());

  // If the user has selected a specific lap, send it
  if (lapSelector.classList.contains('visible')) {
    formData.append('lap_index', lapSelect.value);
  }

  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      showError(data.error || 'Something went wrong. Please try again.');
      return;
    }

    // Populate lap selector if this is the first analysis (or laps changed)
    allLaps = data.all_laps;
    populateLapSelector(allLaps, data.lap.index);

    // Render results
    renderSessionStrip(data.session, data.lap);
    lapBadge.textContent = `Lap ${data.lap.lap_number} · ${data.lap.lap_time_str}`;
    adviceBody.innerHTML = markdownToHtml(data.advice);
    results.classList.add('visible');

    // Scroll to results
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch (err) {
    showError('Could not reach the server. Check your connection and try again.');
    console.error(err);
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  submitBtn.classList.toggle('loading', on);
  submitBtn.disabled = on;
}
