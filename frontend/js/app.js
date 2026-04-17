// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE = 'https://lmu-setup-engineer.onrender.com';
const MAX_TURNS = 5;

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  currentStep: 1,
  file: null,
  carClass: null,
  trackName: '',
  lapIndex: null,
  allLaps: [],
  issueCategory: null,
  description: '',
  // multi-turn session
  sessionId: null,
  history: null,
  turnNumber: 0,
  // follow-up file
  followupFile: null,
  followupLapIndex: null,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const dropZone           = document.getElementById('dropZone');
const fileInput          = document.getElementById('fileInput');
const fileChosen         = document.getElementById('fileChosen');
const fileName           = document.getElementById('fileName');
const fileClear          = document.getElementById('fileClear');
const trackName          = document.getElementById('trackName');
const lapSelectorWrap    = document.getElementById('lapSelectorWrap');
const lapSelect          = document.getElementById('lapSelect');
const description        = document.getElementById('description');
const charCount          = document.getElementById('charCount');
const errorBannerStep1   = document.getElementById('errorBannerStep1');
const errorBannerStep2   = document.getElementById('errorBannerStep2');
const btnStep1Next       = document.getElementById('btnStep1Next');
const btnStep2Back       = document.getElementById('btnStep2Back');
const btnAnalyse         = document.getElementById('btnAnalyse');
const tipsPanel          = document.getElementById('tipsPanel');
const tipsPanelTitle     = document.getElementById('tipsPanelTitle');
const tipsPanelBody      = document.getElementById('tipsPanelBody');
// results
const resultsSkeleton    = document.getElementById('resultsSkeleton');
const resultsContent     = document.getElementById('resultsContent');
const sessionStrip       = document.getElementById('sessionStrip');
const adviceList         = document.getElementById('adviceList');
const turnInfo           = document.getElementById('turnInfo');
const btnStartFresh      = document.getElementById('btnStartFresh');
const btnContinue        = document.getElementById('btnContinue');
// follow-up panel
const followupPanel      = document.getElementById('followupPanel');
const followupDropZone   = document.getElementById('followupDropZone');
const followupFileInput  = document.getElementById('followupFileInput');
const followupFileChosen = document.getElementById('followupFileChosen');
const followupFileName   = document.getElementById('followupFileName');
const followupFileClear  = document.getElementById('followupFileClear');
const followupLapWrap    = document.getElementById('followupLapWrap');
const followupLapSelect  = document.getElementById('followupLapSelect');
const changesDescription = document.getElementById('changesDescription');
const errorBannerFollowup= document.getElementById('errorBannerFollowup');
const followupTurnBadge  = document.getElementById('followupTurnBadge');
const btnCancelFollowup  = document.getElementById('btnCancelFollowup');
const btnFollowup        = document.getElementById('btnFollowup');

// ── Sidebar navigation ─────────────────────────────────────────────────────
document.querySelectorAll('.sidebar-nav-item').forEach(item => {
  item.addEventListener('click', () => {
    const page = item.dataset.page;
    document.querySelectorAll('.sidebar-nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById(`page-${page}`).classList.add('active');
  });
});

// ── Stepper ────────────────────────────────────────────────────────────────
function updateStepper(step) {
  document.querySelectorAll('.stepper-step').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.remove('active', 'done');
    if (s === step) el.classList.add('active');
    if (s < step)   el.classList.add('done');
  });
  const line1 = document.getElementById('stepLine1');
  const line2 = document.getElementById('stepLine2');
  if (line1) line1.classList.toggle('done', step > 1);
  if (line2) line2.classList.toggle('done', step > 2);
}

function goToStep(step) {
  document.querySelectorAll('.wizard-step').forEach(el => el.classList.remove('active'));
  document.getElementById(`step${step}`).classList.add('active');
  state.currentStep = step;
  updateStepper(step);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── File handling (step 1) ─────────────────────────────────────────────────
function setFile(file) {
  if (!file || !file.name.toLowerCase().endsWith('.ld')) {
    showError(errorBannerStep1, 'Only .ld files are supported.');
    return;
  }
  state.file = file;
  fileName.textContent = file.name;
  fileChosen.classList.add('visible');
  hideError(errorBannerStep1);
  updateStep1State();
}

function clearFile() {
  state.file = null;
  state.allLaps = [];
  state.lapIndex = null;
  fileInput.value = '';
  fileChosen.classList.remove('visible');
  lapSelectorWrap.style.display = 'none';
  lapSelect.innerHTML = '';
  updateStep1State();
}

fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });
fileClear.addEventListener('click', (e) => { e.stopPropagation(); clearFile(); });

dropZone.addEventListener('dragover',  (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', ()  => { dropZone.classList.remove('dragover'); });
dropZone.addEventListener('drop',      (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});

// ── Car class selection ────────────────────────────────────────────────────
document.querySelectorAll('.class-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.class-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    state.carClass = card.dataset.class;
    updateStep1State();
  });
});

// ── Lap selector (step 1) ──────────────────────────────────────────────────
function populateLapSelector(laps, selectedIndex, selectEl, wrapEl) {
  selectEl.innerHTML = '';
  laps.forEach(lap => {
    const opt = document.createElement('option');
    opt.value = lap.index;
    opt.textContent = `Lap ${lap.lap_number}  —  ${lap.lap_time_str}`;
    if (lap.index === selectedIndex) opt.selected = true;
    selectEl.appendChild(opt);
  });
  wrapEl.style.display = 'block';
}

lapSelect.addEventListener('change', () => { state.lapIndex = parseInt(lapSelect.value); });

// ── Step 1 validation ──────────────────────────────────────────────────────
function updateStep1State() {
  btnStep1Next.disabled = !(state.file !== null && state.carClass !== null);
}

// ── Category + tips (step 2) ───────────────────────────────────────────────
const CATEGORY_TIPS = {
  Understeer: {
    title: 'Tips for Understeer',
    body: `<p>The AI needs to know <strong>when</strong> and <strong>where</strong> the understeer occurs.</p>
<ul class="tips-list">
  <li><strong>Entry push:</strong> mention how hard you're turning in and trail-braking behaviour</li>
  <li><strong>Mid-corner push:</strong> mention the speed and whether it's a high or low-speed corner</li>
  <li><strong>Exit push:</strong> mention throttle application timing</li>
  <li>Name specific corners — high-speed and hairpins need different fixes</li>
</ul>`
  },
  Oversteer: {
    title: 'Tips for Oversteer & Snap',
    body: `<p>Snap oversteer needs as much context as possible to diagnose correctly.</p>
<ul class="tips-list">
  <li><strong>Entry snap:</strong> under braking while turning? Mention trail-braking</li>
  <li><strong>Exit snap:</strong> at initial throttle pickup, or further into the power?</li>
  <li>Does it happen on kerbs specifically? Kerb-induced snap has different causes</li>
  <li>Does the car give warning, or is it sudden and unpredictable?</li>
</ul>`
  },
  Traction: {
    title: 'Tips for Traction & Exits',
    body: `<p>TC settings are adjusted before the mechanical setup. Mention them.</p>
<ul class="tips-list">
  <li>What are your current TC, TC Slip, and TC Cut settings?</li>
  <li>Is it wheelspin, or does the car also move laterally?</li>
  <li>What corner type? Slow hairpins vs. medium-speed exits need different solutions</li>
  <li>Mention the speed at which wheelspin starts</li>
</ul>`
  },
  Braking: {
    title: 'Tips for Braking & Rotation',
    body: `<p>Braking diagnosis differs between GT3 (ABS) and prototypes (no ABS).</p>
<ul class="tips-list">
  <li><strong>Non-GT3 lockup:</strong> which end or wheel is locking?</li>
  <li><strong>GT3:</strong> mention your ABS setting — ABS 9 (Understeer) is the competitive default</li>
  <li>Straight-line braking, or while turning in (trail-braking)?</li>
  <li>Mention specific braking zones if you know them</li>
</ul>`
  },
  Bumps: {
    title: 'Tips for Bumps & Kerbs',
    body: `<p>Bump/kerb issues are addressed with fast dampers, not slow dampers.</p>
<ul class="tips-list">
  <li>Which kerbs — sausage, flat, or rumble strips?</li>
  <li>Does the car bounce, snap, or just lose grip over the bump?</li>
  <li>Is one axle worse than the other?</li>
  <li>Is the issue the initial hit, or the aftermath/recovery?</li>
</ul>`
  },
};

document.querySelectorAll('.category-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.category-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    state.issueCategory = card.dataset.category;
    const tips = CATEGORY_TIPS[state.issueCategory];
    if (tips) {
      tipsPanelTitle.textContent = tips.title;
      tipsPanelBody.innerHTML = tips.body;
      tipsPanel.classList.add('visible');
    }
    updateStep2State();
  });
});

description.addEventListener('input', () => {
  const len = description.value.length;
  charCount.textContent = `${len} / 1000`;
  charCount.classList.toggle('warn', len > 900);
  state.description = description.value;
  updateStep2State();
});

function updateStep2State() {
  btnAnalyse.disabled = !(state.issueCategory !== null && description.value.trim().length > 0);
}

// ── Navigation ─────────────────────────────────────────────────────────────
btnStep1Next.addEventListener('click', () => goToStep(2));
btnStep2Back.addEventListener('click', () => goToStep(1));
btnStartFresh.addEventListener('click', resetAll);

// ── Error helpers ──────────────────────────────────────────────────────────
function showError(el, msg) { el.textContent = msg; el.classList.add('visible'); }
function hideError(el)      { el.classList.remove('visible'); }

// ── Submit — first analysis ────────────────────────────────────────────────
btnAnalyse.addEventListener('click', () => {
  hideError(errorBannerStep2);
  // Move to step 3 immediately and show skeleton
  goToStep(3);
  resultsSkeleton.style.display = 'block';
  resultsContent.style.display = 'none';
  setAnalyseLoading(true);
  runAnalysis();
});

async function runAnalysis() {
  const formData = new FormData();
  formData.append('file', state.file);
  formData.append('description', description.value.trim());
  if (state.carClass)       formData.append('car_class', state.carClass);
  if (state.issueCategory)  formData.append('issue_category', state.issueCategory);
  const track = trackName.value.trim();
  if (track) formData.append('track_name', track);
  if (lapSelectorWrap.style.display !== 'none') {
    formData.append('lap_index', lapSelect.value);
  }

  try {
    const data = await callApi(formData);
    state.allLaps    = data.all_laps;
    state.sessionId  = data.session_id;
    state.history    = data.history;
    state.turnNumber = data.turn_number || 1;

    populateLapSelector(state.allLaps, data.lap.index, lapSelect, lapSelectorWrap);
    persistSession();
    renderResults(data, false);

  } catch (err) {
    // Error: go back to step 2 to show the error
    goToStep(2);
    showError(errorBannerStep2, err.message || 'Could not reach the server. Check your connection and try again.');
    console.error(err);
  } finally {
    setAnalyseLoading(false);
  }
}

function setAnalyseLoading(on) {
  btnAnalyse.classList.toggle('loading', on);
  btnAnalyse.disabled = on;
}

// ── Render results ─────────────────────────────────────────────────────────
function renderResults(data, isFollowup) {
  if (!isFollowup) {
    // First run: populate session strip + clear advice list
    renderSessionStrip(data.session, data.lap);
    adviceList.innerHTML = '';
  }

  // Append a new advice card
  appendAdviceCard(data.advice, data.lap, isFollowup ? state.turnNumber : 1);

  // Turn info badge
  updateTurnInfo();

  // Show/hide "Continue" depending on cap
  btnContinue.style.display = state.turnNumber >= MAX_TURNS ? 'none' : '';
  if (state.turnNumber >= MAX_TURNS) {
    // Show cap message if not already present
    if (!document.getElementById('turnCapMsg')) {
      const msg = document.createElement('div');
      msg.id = 'turnCapMsg';
      msg.className = 'turn-cap-msg';
      msg.textContent = `Maximum ${MAX_TURNS} analysis turns reached. Start a fresh session to continue.`;
      document.querySelector('.results-actions').after(msg);
    }
  }

  // Show results, hide skeleton
  resultsSkeleton.style.display = 'none';
  resultsContent.style.display = 'block';
}

function appendAdviceCard(adviceText, lap, turnNum) {
  const card = document.createElement('div');
  card.className = 'advice-card';
  if (adviceList.children.length > 0) card.style.marginTop = '14px';

  card.innerHTML = `
    <div class="advice-header">
      <div class="advice-header-title">
        ${turnNum > 1 ? `Follow-up Analysis — Turn ${turnNum}` : 'AI Setup Recommendations'}
      </div>
      <div class="advice-lap-badge">Lap ${lap.lap_number} · ${lap.lap_time_str}</div>
    </div>
    <div class="advice-body">${markdownToHtml(adviceText)}</div>
  `;
  adviceList.appendChild(card);
  // Smooth scroll to new card
  setTimeout(() => card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
}

function updateTurnInfo() {
  if (state.turnNumber <= 1) {
    turnInfo.innerHTML = '';
    return;
  }
  turnInfo.innerHTML = `
    <span class="turn-badge">
      <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z"/></svg>
      Turn ${state.turnNumber} of ${MAX_TURNS}
    </span>
  `;
}

// ── Session strip ──────────────────────────────────────────────────────────
function renderSessionStrip(session, lap) {
  const track = session.venue && session.venue !== 'Unknown' ? session.venue : '—';
  sessionStrip.innerHTML = [
    { label: 'Driver',   value: session.driver },
    { label: 'Car',      value: session.vehicle },
    { label: 'Class',    value: state.carClass || '—' },
    { label: 'Track',    value: track },
    { label: 'Lap',      value: `Lap ${lap.lap_number}`, accent: true },
    { label: 'Lap time', value: lap.lap_time_str, accent: true },
  ].map(({ label, value, accent }) => `
    <div class="session-cell">
      <div class="session-cell-label">${label}</div>
      <div class="session-cell-value${accent ? ' accent' : ''}">${value || '—'}</div>
    </div>
  `).join('');
}

// ── Follow-up panel ────────────────────────────────────────────────────────
btnContinue.addEventListener('click', openFollowup);
btnCancelFollowup.addEventListener('click', closeFollowup);

function openFollowup() {
  followupPanel.classList.add('open');
  const remaining = MAX_TURNS - state.turnNumber;
  followupTurnBadge.textContent = `${remaining} turn${remaining !== 1 ? 's' : ''} remaining`;
  followupPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeFollowup() {
  followupPanel.classList.remove('open');
  clearFollowupFile();
  changesDescription.value = '';
  hideError(errorBannerFollowup);
  updateFollowupState();
}

// Follow-up file handling
function setFollowupFile(file) {
  if (!file || !file.name.toLowerCase().endsWith('.ld')) {
    showError(errorBannerFollowup, 'Only .ld files are supported.');
    return;
  }
  state.followupFile = file;
  followupFileName.textContent = file.name;
  followupFileChosen.classList.add('visible');
  hideError(errorBannerFollowup);
  updateFollowupState();
}

function clearFollowupFile() {
  state.followupFile = null;
  state.followupLapIndex = null;
  followupFileInput.value = '';
  followupFileChosen.classList.remove('visible');
  followupLapWrap.style.display = 'none';
  followupLapSelect.innerHTML = '';
  updateFollowupState();
}

followupFileInput.addEventListener('change', () => {
  if (followupFileInput.files[0]) setFollowupFile(followupFileInput.files[0]);
});
followupFileClear.addEventListener('click', (e) => { e.stopPropagation(); clearFollowupFile(); });

followupDropZone.addEventListener('dragover',  (e) => { e.preventDefault(); followupDropZone.classList.add('dragover'); });
followupDropZone.addEventListener('dragleave', ()  => { followupDropZone.classList.remove('dragover'); });
followupDropZone.addEventListener('drop',      (e) => {
  e.preventDefault();
  followupDropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) setFollowupFile(e.dataTransfer.files[0]);
});

followupLapSelect.addEventListener('change', () => {
  state.followupLapIndex = parseInt(followupLapSelect.value);
});

changesDescription.addEventListener('input', updateFollowupState);

function updateFollowupState() {
  btnFollowup.disabled = !(state.followupFile && changesDescription.value.trim().length > 0);
}

// ── Submit — follow-up ─────────────────────────────────────────────────────
btnFollowup.addEventListener('click', runFollowup);

async function runFollowup() {
  hideError(errorBannerFollowup);
  setFollowupLoading(true);

  // Show skeleton again while waiting
  resultsSkeleton.style.display = 'block';
  resultsContent.style.display = 'none';
  closeFollowupPanelSilently();

  const formData = new FormData();
  formData.append('file', state.followupFile);
  formData.append('description', description.value.trim()); // same original description context
  formData.append('changes_description', changesDescription.value.trim());
  formData.append('session_id', state.sessionId || '');
  if (state.history) formData.append('history', JSON.stringify(state.history));
  if (state.carClass)       formData.append('car_class', state.carClass);
  if (state.issueCategory)  formData.append('issue_category', state.issueCategory);
  const track = trackName.value.trim();
  if (track) formData.append('track_name', track);
  if (followupLapWrap.style.display !== 'none') {
    formData.append('lap_index', followupLapSelect.value);
  }

  try {
    const data = await callApi(formData);
    state.sessionId  = data.session_id;
    state.history    = data.history;
    state.turnNumber = data.turn_number || state.turnNumber + 1;

    // Update lap selector with new file's laps
    populateLapSelector(data.all_laps, data.lap.index, followupLapSelect, followupLapWrap);
    persistSession();
    renderResults(data, true);

    // Clear the follow-up inputs for the next potential turn
    state.followupFile = null;
    state.followupLapIndex = null;
    followupFileInput.value = '';
    followupFileChosen.classList.remove('visible');
    changesDescription.value = '';
    followupLapWrap.style.display = 'none';

  } catch (err) {
    // Restore content view and show error in follow-up panel
    resultsSkeleton.style.display = 'none';
    resultsContent.style.display = 'block';
    followupPanel.classList.add('open');
    showError(errorBannerFollowup, err.message || 'Could not reach the server. Try again.');
    console.error(err);
  } finally {
    setFollowupLoading(false);
  }
}

function closeFollowupPanelSilently() {
  followupPanel.classList.remove('open');
}

function setFollowupLoading(on) {
  btnFollowup.classList.toggle('loading', on);
  btnFollowup.disabled = on;
}

// ── Shared API call ────────────────────────────────────────────────────────
async function callApi(formData) {
  const res = await fetch(`${API_BASE}/analyze`, { method: 'POST', body: formData });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}

// ── localStorage persistence ───────────────────────────────────────────────
const LS_KEY = 'lmu_session';

function persistSession() {
  if (!state.sessionId) return;
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      sessionId:     state.sessionId,
      history:       state.history,
      turnNumber:    state.turnNumber,
      carClass:      state.carClass,
      issueCategory: state.issueCategory,
    }));
  } catch (e) { /* storage full or unavailable — silent */ }
}

function clearPersistedSession() {
  try { localStorage.removeItem(LS_KEY); } catch (e) { /* silent */ }
}

// ── Reset ──────────────────────────────────────────────────────────────────
function resetAll() {
  clearFile();
  clearFollowupFile();
  clearPersistedSession();
  document.querySelectorAll('.class-card').forEach(c => c.classList.remove('selected'));
  document.querySelectorAll('.category-card').forEach(c => c.classList.remove('selected'));
  trackName.value = '';
  description.value = '';
  charCount.textContent = '0 / 1000';
  charCount.classList.remove('warn');
  tipsPanel.classList.remove('visible');
  hideError(errorBannerStep1);
  hideError(errorBannerStep2);
  // Reset state
  Object.assign(state, {
    carClass: null, issueCategory: null, description: '',
    lapIndex: null, sessionId: null, history: null, turnNumber: 0,
    followupFile: null, followupLapIndex: null,
  });
  updateStep1State();
  updateStep2State();
  updateFollowupState();
  // Reset results area
  adviceList.innerHTML = '';
  turnInfo.innerHTML = '';
  followupPanel.classList.remove('open');
  resultsSkeleton.style.display = 'block';
  resultsContent.style.display = 'none';
  const capMsg = document.getElementById('turnCapMsg');
  if (capMsg) capMsg.remove();
  goToStep(1);
}

// ── Markdown → HTML ────────────────────────────────────────────────────────
function markdownToHtml(text) {
  const lines = text.split('\n');
  const out = [];
  let inList = false;
  let listType = 'ul';

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    line = line
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+?)\*/g,  '<em>$1</em>');

    if (/^###\s/.test(line)) {
      if (inList) { out.push(`</${listType}>`); inList = false; }
      out.push(`<h3>${line.replace(/^###\s/, '')}</h3>`);
      continue;
    }
    if (/^##\s/.test(line)) {
      if (inList) { out.push(`</${listType}>`); inList = false; }
      out.push(`<h2>${line.replace(/^##\s/, '')}</h2>`);
      continue;
    }
    if (/^[-*]\s/.test(line)) {
      if (!inList || listType !== 'ul') {
        if (inList) out.push(`</${listType}>`);
        out.push('<ul>'); inList = true; listType = 'ul';
      }
      out.push(`<li>${line.replace(/^[-*]\s/, '')}</li>`);
      continue;
    }
    if (/^\d+\.\s/.test(line)) {
      if (!inList || listType !== 'ol') {
        if (inList) out.push(`</${listType}>`);
        out.push('<ol>'); inList = true; listType = 'ol';
      }
      out.push(`<li>${line.replace(/^\d+\.\s/, '')}</li>`);
      continue;
    }
    if (inList) { out.push(`</${listType}>`); inList = false; }
    if (line.trim() === '') continue;
    out.push(`<p>${line}</p>`);
  }

  if (inList) out.push(`</${listType}>`);
  return out.join('\n');
}
