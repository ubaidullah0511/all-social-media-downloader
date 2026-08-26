const BACKEND_URL = 'http://127.0.0.1:5000';
const DEV_MODE = true;
const YOUTUBE_RE = /^https?:\/\/(?:www\.)?youtube\.com\/watch\?[^#]*\bv=([\w-]+)|^https?:\/\/youtu\.be\/([\w-]+)/;

function log(...args) {
  if (DEV_MODE) console.log('[YT-DL/popup]', ...args);
}

function extractVideoId(url) {
  const m = url && url.match(YOUTUBE_RE);
  return m ? (m[1] || m[2]) : null;
}

// ---- DOM ----
const el = {
  notYoutube: document.getElementById('not-youtube'),
  backendOffline: document.getElementById('backend-offline'),
  retryBackendBtn: document.getElementById('retry-backend-btn'),
  main: document.getElementById('main-content'),
  videoTitle: document.getElementById('video-title'),
  videoUrl: document.getElementById('video-url'),
  checkBtn: document.getElementById('check-btn'),
  results: document.getElementById('results'),
  typeSelector: document.getElementById('type-selector'),
  qualityField: document.getElementById('quality-field'),
  qualityOptions: document.getElementById('quality-options'),
  modeField: document.getElementById('mode-field'),
  downloadBtn: document.getElementById('download-btn'),
  spinner: document.getElementById('spinner'),
  statusText: document.getElementById('status-text'),
  errorBox: document.getElementById('error-box'),
};

// ---- UI helpers ----
function setStatus(text, { spinning = false } = {}) {
  el.statusText.textContent = text;
  el.spinner.classList.toggle('hidden', !spinning);
}

function showError(message) {
  el.errorBox.textContent = message;
  el.errorBox.classList.remove('hidden');
}

function clearError() {
  el.errorBox.classList.add('hidden');
  el.errorBox.textContent = '';
}

// ---- Friendly error mapping (only used for /youtube/qualities, where we
// get the real backend JSON body — the /download path's errors come
// pre-summarized from background.js since Chrome's downloads API doesn't
// expose response bodies to the extension). ----
function friendlyCheckError(rawMessage) {
  const msg = (rawMessage || '').toLowerCase();
  if (msg.includes('429') || msg.includes('too many requests')) {
    return 'YouTube is rate-limiting requests right now (HTTP 429). Wait a bit and try again.';
  }
  if (msg.includes('sign in to confirm') || msg.includes('not a bot')) {
    return "YouTube is asking for sign-in verification. The backend's cookies may be missing or expired.";
  }
  if (msg.includes('cookie')) {
    return 'A YouTube cookie/authentication problem occurred on the backend. Check cookies.txt is valid.';
  }
  if (msg.includes('ejs') || msg.includes('deno') || msg.includes('challenge')) {
    return "YouTube's JS challenge could not be solved by the backend (EJS/Deno). Check the Flask console.";
  }
  if (msg.includes('unsupported url') || msg.includes('is not a valid url')) {
    return 'That does not look like a valid YouTube video URL.';
  }
  if (msg.includes('unable to download webpage') || msg.includes('video unavailable')) {
    return 'Could not fetch this video (it may be private, deleted, or region-locked).';
  }
  if (msg.includes('no video formats') || msg.includes('no formats')) {
    return 'No downloadable formats were found for this video.';
  }
  if (msg.includes('timed out') || msg.includes('timeout')) {
    return 'The request to YouTube timed out. Check your connection and try again.';
  }
  return rawMessage || 'Could not check this video.';
}

async function checkBackendReachable() {
  try {
    await fetch(`${BACKEND_URL}/`, { method: 'GET', signal: AbortSignal.timeout(3000) });
    return true;
  } catch (e) {
    log('backend unreachable:', e.message);
    return false;
  }
}

// ---- App state (reset whenever the video changes) ----
let state = {
  tabId: null,
  videoUrl: null,
  videoId: null,
  isChecking: false,
  qualities: [], // [{height, label}], height=null means "Best available"
  selectedQuality: null, // null = best available
  selectedMode: 'original',
  selectedType: 'video',
};

function resetForNewVideo(videoUrl, videoId) {
  state = {
    ...state,
    videoUrl,
    videoId,
    isChecking: false,
    qualities: [],
    selectedQuality: null,
    selectedMode: 'original',
    selectedType: 'video',
  };
  el.notYoutube.classList.add('hidden');
  el.main.classList.remove('hidden');
  el.videoUrl.textContent = videoUrl;
  el.videoTitle.textContent = '—';
  el.results.classList.add('hidden');
  el.downloadBtn.disabled = true;
  el.checkBtn.disabled = false;
  clearError();
  setStatus('Ready');
  log('reset for new video', videoId);
}

function renderQualityChips() {
  el.qualityOptions.innerHTML = '';
  const options = [{ height: null, label: 'Best Available' }, ...state.qualities];
  for (const q of options) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip' + (state.selectedQuality === q.height ? ' active' : '');
    chip.textContent = q.label;
    chip.addEventListener('click', () => {
      state.selectedQuality = q.height;
      log('quality selected', q.height);
      renderQualityChips();
    });
    el.qualityOptions.appendChild(chip);
  }
}

function applyTypeVisibility() {
  const isAudio = state.selectedType === 'audio';
  el.qualityField.classList.toggle('hidden', isAudio);
  el.modeField.classList.toggle('hidden', isAudio);
}

// ---- Check Video ----
async function onCheckVideoClick() {
  if (state.isChecking) return;
  state.isChecking = true;
  el.checkBtn.disabled = true;
  clearError();
  setStatus('Checking video...', { spinning: true });
  log('quality check started', state.videoUrl);

  const reachable = await checkBackendReachable();
  if (!reachable) {
    el.backendOffline.classList.remove('hidden');
    setStatus('Failed', { spinning: false });
    state.isChecking = false;
    el.checkBtn.disabled = false;
    return;
  }
  el.backendOffline.classList.add('hidden');

  try {
    const res = await fetch(`${BACKEND_URL}/youtube/qualities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: state.videoUrl }),
    });
    const data = await res.json();
    log('quality response received', { ok: res.ok, success: data.success });

    if (!res.ok || !data.success) {
      showError(friendlyCheckError(data.message));
      setStatus('Failed');
      return;
    }

    state.qualities = data.qualities || [];
    el.videoTitle.textContent = data.title || state.videoUrl;
    renderQualityChips();
    applyTypeVisibility();
    el.results.classList.remove('hidden');
    el.downloadBtn.disabled = false;
    setStatus('Qualities loaded');
    setTimeout(() => setStatus('Waiting for selection'), 700);
  } catch (e) {
    log('quality check error', e.message);
    showError('Could not reach the backend to check this video.');
    setStatus('Failed');
  } finally {
    state.isChecking = false;
    el.checkBtn.disabled = false;
  }
}

// ---- Download ----
function buildPayload() {
  const payload = {
    url: state.videoUrl,
    platform: 'youtube',
    content_type: state.selectedType,
  };
  if (state.selectedType === 'video') {
    if (state.selectedQuality) payload.quality = state.selectedQuality;
    payload.quality_mode = state.selectedMode;
  }
  return payload;
}

async function onDownloadClick() {
  el.downloadBtn.disabled = true; // synchronous guard against double-click
  clearError();
  setStatus('Starting download...', { spinning: true });
  const payload = buildPayload();
  log('download request started', payload);

  const response = await chrome.runtime.sendMessage({
    type: 'START_DOWNLOAD',
    // Keyed by video ID, not the raw URL string — incidental differences
    // like a `&t=42s` timestamp shouldn't be treated as a different video.
    videoUrl: state.videoId,
    payload,
  });
  log('backend response status', response);

  if (!response.ok) {
    showError(response.message || 'Could not start the download.');
    setStatus('Failed');
    el.downloadBtn.disabled = false;
  }
  // On success we wait for DOWNLOAD_STATE_UPDATE messages from background.js
  // to drive the status text through processing -> downloading -> completed.
}

function applyDownloadState(s) {
  if (!s) return;
  switch (s.status) {
    case 'processing':
      setStatus('Processing...', { spinning: true });
      el.downloadBtn.disabled = true;
      break;
    case 'downloading':
      setStatus(s.filename ? `Downloading... (${s.filename})` : 'Downloading...', { spinning: true });
      el.downloadBtn.disabled = true;
      break;
    case 'completed':
      setStatus(s.filename ? `Completed — ${s.filename}` : 'Completed', { spinning: false });
      log('download completed', s.filename);
      el.downloadBtn.disabled = false;
      break;
    case 'failed':
      setStatus('Failed', { spinning: false });
      if (s.error) showError(s.error);
      log('download failed', s.error);
      el.downloadBtn.disabled = false;
      break;
    default:
      break;
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === 'DOWNLOAD_STATE_UPDATE' && message.videoUrl === state.videoId) {
    applyDownloadState(message.state);
  }
});

// ---- Type / quality / mode wiring ----
el.typeSelector.addEventListener('click', (e) => {
  const btn = e.target.closest('.seg');
  if (!btn) return;
  state.selectedType = btn.dataset.value;
  [...el.typeSelector.children].forEach((c) => c.classList.toggle('active', c === btn));
  applyTypeVisibility();
});

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener('change', (e) => {
    state.selectedMode = e.target.value;
    log('mode selected', state.selectedMode);
  });
});

el.checkBtn.addEventListener('click', onCheckVideoClick);
el.downloadBtn.addEventListener('click', onDownloadClick);
el.retryBackendBtn.addEventListener('click', async () => {
  if (await checkBackendReachable()) {
    el.backendOffline.classList.add('hidden');
  }
});

// ---- SPA navigation: same tab, URL changes without a full reload ----
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (tabId !== state.tabId || !changeInfo.url) return;
  const newVideoId = extractVideoId(changeInfo.url);
  if (newVideoId && newVideoId !== state.videoId) {
    log('SPA navigation detected, resetting', newVideoId);
    resetForNewVideo(changeInfo.url, newVideoId);
  } else if (!newVideoId) {
    // Navigated away from a video entirely.
    el.main.classList.add('hidden');
    el.notYoutube.classList.remove('hidden');
  }
});

// ---- Init ----
async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const videoId = tab?.url ? extractVideoId(tab.url) : null;
  log('current tab url', tab?.url);

  if (!tab?.url || !videoId) {
    el.notYoutube.classList.remove('hidden');
    el.main.classList.add('hidden');
    return;
  }

  el.notYoutube.classList.add('hidden');
  el.main.classList.remove('hidden');
  state.tabId = tab.id;
  resetForNewVideo(tab.url, videoId);

  const reachable = await checkBackendReachable();
  el.backendOffline.classList.toggle('hidden', reachable);

  // Restore any in-progress/completed/failed download state for this exact
  // video so reopening the popup mid-download shows the real status instead
  // of resetting to "Ready".
  const existing = await chrome.runtime.sendMessage({ type: 'GET_STATE', videoUrl: state.videoId });
  if (existing && existing.status !== 'idle') {
    applyDownloadState(existing);
  }
}

init();
