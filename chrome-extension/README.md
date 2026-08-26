# YouTube Downloader — Chrome Extension

A Manifest V3 popup UI for the existing Flask + yt-dlp + FFmpeg backend in this
repo. The extension never does any downloading itself — it only calls your
local backend's `/youtube/qualities` and `/download` endpoints and lets Chrome
handle the actual file transfer.

## Folder structure

```
chrome-extension/
├── manifest.json      MV3 manifest — permissions, popup, service worker
├── background.js      Service worker: owns chrome.downloads lifecycle + state
├── popup.html          Popup markup
├── popup.css           Popup styling
├── popup.js            Popup logic: tab detection, Check Video, Download
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md           This file
```

## Backend changes made

Two backend changes, both in `app.py`:

- A CORS `after_request` hook scoped to `chrome-extension://*` origins (plus
  `127.0.0.1`/`localhost` for direct testing) — not a blanket
  `Access-Control-Allow-Origin: *`. The POST + `Content-Type: application/json`
  requests this extension makes are "non-simple" per the CORS spec, so the
  browser preflights them with an `OPTIONS` request first; Flask's automatic
  OPTIONS handling combined with this hook answers that correctly.
- `POST /download` no longer streams the finished file in its own response.
  It now returns JSON with a `download_url` pointing at a separate
  `GET /file/<download_id>` route that serves the already-completed file
  (with proper Range/206/416 support), because a POST-only JSON endpoint
  can't be intercepted by download managers like IDM — see the main
  project's notes on that redesign for the full reasoning. `background.js`
  below was updated to match.

## Installing the extension

1. Make sure the Flask backend is installed and can run (see the main
   project README) and that `ffmpeg`/`ffprobe` are on `PATH`.
2. Start the backend: `myenv\Scripts\python.exe app.py` (from the repo root).
   Leave it running — the extension talks to `http://127.0.0.1:5000`.
3. In Chrome, go to `chrome://extensions`.
4. Enable **Developer mode** (top-right toggle).
5. Click **Load unpacked** and select the `chrome-extension` folder.
6. Pin the extension (puzzle-piece icon in the toolbar → pin) so it's
   visible.

## Using it

1. Open any `youtube.com/watch?v=...` or `youtu.be/...` video.
2. Click the extension icon.
3. Click **Check Video**. This calls `/youtube/qualities` and shows the
   title plus only the resolutions that really exist for that video.
4. Pick **Video** or **Audio only**. For video, pick a quality chip (or
   leave **Best Available**) and a mode: **Original Quality** or
   **Max Compatibility**.
5. Click **Download**. Only now does `/download` get called — nothing
   downloads automatically at any earlier step.
6. Watch the status line: `Starting download… → Processing… →
   Downloading… → Completed`. The file lands in your normal Downloads
   folder, named exactly what the backend's `Content-Disposition` header
   says (`.mp4`, `.webm`, `.mkv`, or `.mp3` — never forced).

## How the download actually happens (two steps)

1. `background.js` sends `POST /download` via `fetch()` and waits for JSON.
   This *is* the slow part — the backend runs yt-dlp/FFmpeg/validation
   synchronously here — but the payload is tiny either way, so buffering it
   costs nothing. On failure, the backend's real error message (e.g.
   `REQUESTED_QUALITY_UNAVAILABLE`, an FFmpeg failure) comes back verbatim
   and is shown as-is — no guessing required.
2. On success, the JSON contains `download_url` — a plain `GET /file/<id>`
   resource that the backend already finished preparing. `background.js`
   hands that URL to `chrome.downloads.download({url: data.download_url})`.
   Chrome's own network stack fetches it and streams straight to disk; the
   extension's JS is never in the data path and never buffers the video
   itself, regardless of size.

This two-step split is also *why* IDM/other download managers can now
intercept the file at all: they hook into normal GET downloads, and can't
replay a POST body. `GET /file/<id>` is a completely ordinary, range-capable
download URL as far as any download manager is concerned.

A lightweight safety net still exists in `background.js`'s
`chrome.downloads.onChanged` handler: if the registered file ever expired
between step 1 and step 2 (a 45-minute window server-side, so only possible
if step 2 is delayed a long time), `GET /file/<id>` answers with a small
JSON error instead of the file. Chrome would otherwise silently save that
JSON as a wrongly-named "video" — this is detected by mime/size and cleaned
up automatically instead of being shown as a completed download.

## Permissions used (and why)

| Permission | Why |
|---|---|
| `activeTab` | Read the current tab's URL when the popup is opened |
| `tabs` | See `url` in `chrome.tabs.onUpdated` events, needed to detect YouTube's SPA navigation between videos without a page reload |
| `downloads` | `chrome.downloads.download()` / `onChanged` / `removeFile` |
| `storage` | `chrome.storage.session` — per-video download state that survives the popup closing and the service worker being suspended |
| `host_permissions` (`127.0.0.1:5000`, `localhost:5000`) | Only these two local origins — lets the popup `fetch()` them without CORS getting in the way |

No `scripting` or content-script permission is requested — SPA navigation
is detected via `chrome.tabs.onUpdated`, not by injecting anything into
youtube.com.

## Security

- The extension never touches `cookies.txt` or any YouTube authentication.
  All of that stays exclusively on the backend (yt-dlp, cookies, Deno/EJS
  challenge solving, FFmpeg/FFprobe, format selection, validation).
- Nothing is written to disk or storage except: (a) the per-video download
  *status* (strings like `"downloading"`, a filename, an error message —
  no credentials ever flow through this path), and (b) the actual media
  file, saved by Chrome's own download manager exactly as it would for any
  other download.
- Console logging (`DEV_MODE = true` in both `popup.js` and `background.js`)
  only ever logs URLs, statuses, selections, and error text — never cookies
  or secrets, because the extension never has access to any.

To turn off the development logging, set `DEV_MODE = false` in both files.

## Testing

With the backend running and the extension loaded:

1. **1080p, Original Quality** — open a 1080p+ video, Check Video, pick
   1080p + Original Quality, Download. Confirm nothing happened before you
   clicked Download, and the file arrives as the native codec (may be
   `.webm`/AV1+Opus, may be `.mp4`/H.264+AAC depending on the source).
2. **4K availability** — open a video with a real 4K source, Check Video,
   confirm `2160p / 4K` appears in the chips (and only genuinely-available
   resolutions — nothing hardcoded).
3. **4K, Max Compatibility** — same video, pick 2160p + Max Compatibility,
   Download. Open your browser's Network/console logging
   (`popup.js`/`background.js` logs) and confirm the payload sent was
   `{"quality": 2160, "quality_mode": "compatibility", ...}`. Verify the
   resulting file is MP4/H.264/AAC (`ffprobe` it if you want to be sure).
4. **Audio only** — pick Audio only, Download, confirm an `.mp3` arrives.
5. **Backend offline** — stop the Flask server, open the popup or click
   Check Video. You should see "Downloader backend is not running…", never
   a raw "Failed to fetch".
6. **Non-YouTube tab** — open any other site, open the popup. You should
   see "Open a YouTube video first." and nothing else usable.
7. **SPA navigation** — with the popup open on one video's results, click
   a different video from YouTube's own UI (same tab, no reload). The
   popup should reset (title/qualities/selection cleared, "Check Video"
   required again) and must not auto-download anything.
8. **Duplicate-click guard** — click Download, then immediately click it
   again (or close and reopen the popup and click Download again) while
   the first one is still `processing`/`downloading`. The second attempt
   should be refused with "A download for this video is already in
   progress." — not a second parallel download.

## Debugging

- **Popup logs**: right-click the extension's popup while it's open →
  *Inspect*. The `[YT-DL/popup]` console lines show tab URL, quality
  request/response, selections, and download status transitions.
- **Service worker logs**: `chrome://extensions` → this extension → click
  *service worker* (under "Inspect views"). The `[YT-DL/bg]` lines show
  every `chrome.downloads` state change, including the mime-sniff decision
  when a backend error gets caught.
- **Backend logs**: the Flask console (this session's earlier work made it
  log every stage — `FETCHING FORMATS`, `STARTING YT-DLP`, `FFMPEG STDERR`,
  `FFMPEG EXIT CODE`, `DOWNLOAD COMPLETE`, etc., plus full tracebacks on
  failure). This is the definitive source for *why* a `/download` call
  failed, since the extension can't read that response body itself.
- **`chrome://downloads`**: shows every download Chrome ever made for this
  extension, including ones `background.js` auto-removed after detecting
  them as error payloads (they'll show as removed/missing).

## Known limitations

- The two `BACKEND_URL` constants (`popup.js`, `background.js`) point at
  `http://127.0.0.1:5000`. If you run the backend on `localhost:5000`
  instead, change both constants (host_permissions already covers both).
- Icons are simple generated placeholders (a download-arrow glyph), not
  branded artwork.
