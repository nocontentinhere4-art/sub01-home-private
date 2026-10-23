# Streamer desktop runner (`scripts/streamer_desktop.py`)

A real headed Playwright Chromium on its own X display (default `:102`, 1920x1080, kiosk: the page fills the screen).
One loopback port serves the PC-runner contract (native 3D monitor, web house) and the agent API. Every route except
`/healthz` needs `X-Admin-Token` (`--token-file` or `SUB01_ADMIN_TOKEN`, at least 12 characters).

## Run on the pod (uid 1001; stop the v86 runner on 8832 first; Xvfb :102 must exist)
```
Xvfb :102 -screen 0 1920x1080x24 -nolisten tcp &
DISPLAY=:102 LD_LIBRARY_PATH=/workspace/sub01-home-private/claude-12h/libs/usr/lib/x86_64-linux-gnu \
/home/unreal/.sub01-private/city-readonly-browser/venv/bin/python $SRC/scripts/streamer_desktop.py \
  --data-dir /home/unreal/.sub01-private/streamer/desktop --token-file /home/unreal/.sub01-private/operator-token \
  --port 8832 --display :102 --home-origin http://127.0.0.1:8830
```
Flags: `--host` (loopback only), `--port 8832`, `--data-dir` (required, outside the repo, never a browser profile folder:
holds `profile/` and `events.jsonl`), `--display :102`, `--size 1920x1080`, `--home-origin` (`/devices/*` proxy),
`--start-url`, `--proxy`, `--chromium PATH`, `--headless` (no X, CI), `--no-kiosk`, `--allow-private` (tests only),
`--pc-mode chromium|vagon` (default `chromium`), `--vagon-url`, `--vagon-config`, `--streamer-dir` (see "Vagon mode").

## PC contract (same as `home_pc_runner.py`)
`GET /pc/state[?since=REV&wait=S]`: `status` (`ready|starting|restarting`), `ready`, `display{kind:"graphical", available,
revision, frame_id, width:1280, height:720}`, `privacy`, `session`, `restarts`, `pc_mode` (`chromium|vagon`; in vagon mode
also `vagon{connected, phase, reconnects, last_reconnect_utc, sessions, reloads, since_utc, api_key_file}`; the privacy
view is unchanged). `GET /pc/frame.png[?revision=ID&full=1]`: PNG
from a CDP screencast (acked at once, at most 10 fps; `full=1` is 1920x1080; 409 on a stale `revision`, 404 while restarting).
`POST /pc/graphical-input`: PS/2 scancodes and relative mouse, forwarded to the page as key codes (Shift works) and mouse
events; `native_receipt` is answered. `POST /pc/input`: text into the focused field. `/pc/session`, `/pc/privacy` as the
runner (privacy refuses frames, input and the agent API with 409). `/devices/*` goes to the home backend.

## Agent API
`GET /desktop/observe`: `{frame_id, url, title, jpeg_b64 (1280x720 with numbered marks), width, height, text (visible, at
most 3000 chars), marks[{id, role, label, box:[x,y,w,h], href?}], scroll{y,max}, loading, dialogs[]}`. Marks cover links,
buttons and text fields in view (at most 60); coordinates are in the 1280x720 image. Marks are valid for the latest
observation only. In vagon mode the body also has `mode: "vagon"` and `remote_ready` (see below); `marks` is empty.
`POST /desktop/act`: `navigate{url}`, `click{mark|point:[x,y]}`, `type{text<=500, submit?, mark?}`, `scroll{direction,
amount}`, `key{key}` (`Enter`, `Control+a`...), `back`, `search{query}` (DuckDuckGo HTML), `wait{seconds<=10}`; optional
`frame_id` rejects stale marks. Answer: `{ok, outcome{url_before, url_after, title_after, changed, errors[], load_ms,
dialog}, frame_id}`; it is built from a new observation after load / network idle (cap 10 s). `ok` is false whenever
`errors` is not empty; `changed` is measured (URL, title, text, scroll or pixels). Policy refusals come back as `ok:false`
with `blocked: ...`; malformed bodies get 400; a browser that is down gets 503. `frame_id` is the post-action state: call
`/desktop/observe` for fresh marks.

## Limits
- Refused: adult, gambling, banking/payment, trading, login/account and checkout hosts and paths, owner services, private
  addresses, ports other than 80/443, downloads and common file types, POST navigations, sub-frames of such hosts. Wikipedia
  `/wiki/` titles are exempt from the path rules. Redirects are checked from the 3xx answer and again once committed.
- Never done: file chooser, clipboard (API, init script, key combos), downloads, popups (closed), password/e-mail/card fields,
  typed card numbers; dialogs are dismissed and listed in `dialogs` / `outcome.dialog`. Cookie banners get the reject button.
- A crashed browser is relaunched in about 2 s, a hung one (no answer to a heartbeat, a 20 s page read) in about 30 s, backoff up
  to 30 s; the new browser starts on `about:blank`. `restarts` counts relaunches.
- No audio (`--mute-audio`); one tab; mark numbers need a fresh observation after any page change.
- Logs: `streamer desktop: ...` on stdout; every action, outcome, block, dialog and relaunch in `<data-dir>/events.jsonl`.

## Vagon mode (`--pc-mode vagon`; research and the owner's part in VAGON.md)
The same kiosk Chromium shows the owner's Vagon Streams page instead of browsing: the remote machine's pixels fill the
1920x1080 display, so the monitor texture, the director and the agent loop do not change. Everything above stays as it
is in `chromium` mode; nothing changes by default.

Configuration: the stream link comes from `--vagon-url` or, preferably (a command line is visible to other users on the
pod), from `<streamer-dir>/vagon.json` (`--streamer-dir`, default `$STREAMER_DIR` or `/home/unreal/.sub01-private/streamer`;
`--vagon-config PATH` names another file), mode 0600:
```
{"schema": "sub01.streamer-vagon.v1", "stream_url": "https://app.vagon.io/stream/...", "api_key_file": "/path (optional)"}
```
`stream_url` must be https, without credentials, on a host the page rules allow; `--vagon-url` wins over the file.
`api_key_file` is only checked for presence and mode (`vagon.api_key_file`: `none|configured|missing|permissive`); the
runner makes no Vagon API call. The link is a credential: logs, events and `/desktop/observe.url` carry only
`https://app.vagon.io/…` (never the path, query string or fragment; Playwright error texts are scrubbed too). `--start-url`
is ignored in this mode.

Session handling (`events.jsonl` kind `vagon`): the page is opened at launch and after every relaunch; every 2 s the main
frame and its frames (the dashboard's iframe embed works too) are probed for visible text, buttons and the largest
`video`/`canvas` of at least 320x180. A connect/start/play/launch button found by its text is pressed (never a login or
money control; at most one press per 6 s, six per page load); a playing video or a canvas means `connected` (`phase`
`ready`); a page that says "session ended / expired / disconnected / insufficient capacity" or offers "Reconnect / Try
again" is `ended`: the button is pressed, else the stream link is opened again with a 15 s, 30 s, 60 s, 2 min, 5 min
backoff (`reloads`); a page with nothing usable for 60 s is opened again too. Each new session after the first counts as a
reconnect (`reconnects`, `last_reconnect_utc`). A stalled video is tolerated for three probes before `connected` drops.
Button labels and the ended texts are heuristics (`VAGON_CONNECT_RX`, `VAGON_ENDED_RX`) written without access to the
real page; expect one round of tuning.

Agent API in this mode: `/desktop/observe` returns the screenshot, `mode: "vagon"`, `remote_ready` (the stream is
playing right now), `marks: []`, `text: ""`, `scroll {0,0}`; `title` is the stream page's. `/desktop/act`: `click{point}`
clicks that point on the stream (page pixels over the stream element), `scroll` sends wheel events over the stream
centre, `type`/`key` focus the stream element and send real key events (`submit` presses Enter), `navigate{url}` and
`search{query}` type into the remote browser's address bar (Ctrl+L, the URL or the DuckDuckGo HTML URL, Enter), `back`
is Alt+Left, `wait` waits. The URL, text, key and clipboard policies still apply before anything is sent; `click{mark}` is
refused (no marks). Every action but `wait` is refused with `the remote desktop is not connected (stream <phase>)` while
the stream is not playing. There is no load state: the outcome's `changed` is the pixel difference after 0.8 s (2.5 s
for navigate/search/back), so the agent must verify through the next observation. `/pc/graphical-input` keys and mouse
go to the stream (no DOM field policy, clipboard combinations still dropped); `/pc/input` types real key events.

Limits: the remote application must be a browser with its window focused for navigate/search to mean anything; no DOM,
so no marks, no page text, no URL of the remote page, no dialogs from the remote machine; Vagon's own limits (session and
idle durations, capacity, cost per minute) are the owner's settings and are in VAGON.md; the connection page's real
button texts are unknown until the owner's stream is seen. Tests: `tests/test_streamer_desktop_vagon.py` (pure mapping
logic, and a real headless Chromium against the mock stream page `tests/fixtures/vagon_mock_stream.html` /
`vagon_mock_embed.html` when a Chromium build is available; skipped with a reason otherwise).
