// Service worker: owns the actual download lifecycle so it survives the
// popup closing. The popup is only a thin UI — all state that must persist
// (which video is downloading, at what quality/mode, filename, errors) lives
// here in chrome.storage.session, keyed by the YouTube video URL.

const BACKEND_URL = 'http://127.0.0.1:5000';
const DEV_MODE = true;
const STORAGE_KEY = 'downloads';

function log(...args) {
  if (DEV_MODE) console.log('[YT-DL/bg]', ...args);
}

function basename(path) {
  if (!path) return '';
  return path.split(/[\\/]/).pop();
}

async function getAllState() {
  const data = await chrome.storage.session.get(STORAGE_KEY);
  return data[STORAGE_KEY] || {};
}

async function getState(videoUrl) {
  const all = await getAllState();
  return all[videoUrl] || null;
}

async function setState(videoUrl, entry) {
  const all = await getAllState();
  all[videoUrl] = entry;
  await chrome.storage.session.set({ [STORAGE_KEY]: all });
  return entry;
}

async function findTrackedByDownloadId(downloadId) {
  const all = await getAllState();
  for (const [videoUrl, entry] of Object.entries(all)) {
    if (entry && entry.downloadId === downloadId) return [videoUrl, entry];
  }
  return null;
}

function broadcast(videoUrl, state) {
  // No listener (popup closed) throws/rejects — that's expected, swallow it.
  chrome.runtime.sendMessage({ type: 'DOWNLOAD_STATE_UPDATE', videoUrl, state }).catch(() => {});
}

async function startDownload(videoUrl, payload) {
  const existing = await getState(videoUrl);
  if (existing && ['processing', 'downloading'].includes(existing.status)) {
    log('duplicate download blocked for', videoUrl);
    return { ok: false, message: 'A download for this video is already in progress.' };
  }

  const entry = {
    // 'processing': the POST /download call is running yt-dlp/FFmpeg on the
    // backend right now and won't resolve until that's fully done.
    status: 'processing',
    quality: payload.quality ?? null,
    mode: payload.quality_mode || 'original',
    contentType: payload.content_type || 'video',
    downloadId: null,
    filename: null,
    error: null,
    startedAt: Date.now(),
  };
  await setState(videoUrl, entry);
  broadcast(videoUrl, entry);
  log('POST /download started', { videoUrl, payload });

  let data;
  try {
    const response = await fetch(`${BACKEND_URL}/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    data = await response.json();
  } catch (e) {
    const failed = await setState(videoUrl, { ...entry, status: 'failed', error: 'Could not reach the backend.' });
    broadcast(videoUrl, failed);
    log('backend unreachable', e.message);
    return { ok: false, message: 'Could not reach the backend.' };
  }

  log('backend response', data);
  if (!data.success) {
    // The backend's own JSON error text, verbatim — no more mime-sniffing
    // needed to guess what went wrong, since /download no longer streams
    // the file (or a same-shaped error) through chrome.downloads itself.
    const failed = await setState(videoUrl, { ...entry, status: 'failed', error: data.message });
    broadcast(videoUrl, failed);
    log('backend rejected download', data.message);
    return { ok: false, message: data.message };
  }

  // The backend already finished all yt-dlp/FFmpeg work; data.download_url
  // is a plain GET, range-capable resource. Chrome's own network stack
  // fetches it directly — the extension's JS is never in the data path.
  try {
    const downloadId = await new Promise((resolve, reject) => {
      chrome.downloads.download({ url: data.download_url, saveAs: false }, (id) => {
        if (chrome.runtime.lastError || id === undefined) {
          reject(new Error(chrome.runtime.lastError?.message || 'Chrome refused to start the download'));
        } else {
          resolve(id);
        }
      });
    });
    const updated = await setState(videoUrl, {
      ...entry,
      status: 'downloading',
      downloadId,
      filename: data.filename,
    });
    broadcast(videoUrl, updated);
    log('download registered with Chrome', { videoUrl, downloadId, url: data.download_url });
    return { ok: true, downloadId };
  } catch (e) {
    const failed = await setState(videoUrl, { ...entry, status: 'failed', error: e.message });
    broadcast(videoUrl, failed);
    log('failed to start chrome download', e.message);
    return { ok: false, message: e.message };
  }
}

// The backend's /file/<id> route can still (rarely) answer with a small
// JSON error instead of the file — e.g. a race where the registered download
// expired between POST /download and this GET. Chrome would otherwise
// silently save that JSON as a wrongly-named file; detect and clean it up.
chrome.downloads.onChanged.addListener(async (delta) => {
  const tracked = await findTrackedByDownloadId(delta.id);
  if (!tracked) return;
  const [videoUrl, entry] = tracked;

  if (delta.filename && delta.filename.current && entry.status !== 'completed' && entry.status !== 'failed') {
    const updated = await setState(videoUrl, {
      ...entry,
      filename: basename(delta.filename.current),
    });
    broadcast(videoUrl, updated);
  }

  if (delta.state && delta.state.current === 'complete') {
    const [item] = await chrome.downloads.search({ id: delta.id });
    const mime = item?.mime || '';
    const looksLikeErrorPayload = mime.includes('json') && item && item.fileSize < 2048;

    if (looksLikeErrorPayload) {
      log('GET /file returned an error payload, cleaning up', { videoUrl, mime, size: item?.fileSize });
      await chrome.downloads.removeFile(delta.id).catch(() => {});
      await chrome.downloads.erase({ id: delta.id }).catch(() => {});
      const updated = await setState(videoUrl, {
        ...entry,
        status: 'failed',
        error: 'The prepared file was no longer available (it may have expired). Try downloading again.',
      });
      broadcast(videoUrl, updated);
    } else {
      const updated = await setState(videoUrl, {
        ...entry,
        status: 'completed',
        filename: item?.filename ? basename(item.filename) : entry.filename,
      });
      log('download completed', { videoUrl, filename: updated.filename });
      broadcast(videoUrl, updated);
    }
  } else if (delta.state && delta.state.current === 'interrupted') {
    const [item] = await chrome.downloads.search({ id: delta.id });
    const updated = await setState(videoUrl, {
      ...entry,
      status: 'failed',
      error: `Download interrupted (${item?.error || 'network interruption or browser cancellation'}).`,
    });
    log('download interrupted', { videoUrl, reason: item?.error });
    broadcast(videoUrl, updated);
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'GET_STATE') {
    getState(message.videoUrl).then((state) => sendResponse(state || { status: 'idle' }));
    return true; // async
  }
  if (message?.type === 'START_DOWNLOAD') {
    startDownload(message.videoUrl, message.payload).then(sendResponse);
    return true; // async
  }
  if (message?.type === 'CLEAR_STATE') {
    setState(message.videoUrl, { status: 'idle' }).then(() => sendResponse({ ok: true }));
    return true;
  }
  return false;
});
