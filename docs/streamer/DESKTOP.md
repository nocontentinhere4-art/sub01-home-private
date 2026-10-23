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
`--start-url`, `--proxy`, `--chromium PATH`, `--headless` (no X, CI), `--no-kiosk`, `--allow-private` (tests only).

## PC contract (same as `home_pc_runner.py`)
`GET /pc/state[?since=REV&wait=S]`: `status` (`ready|starting|restarting`), `ready`, `display{kind:"graphical", available,
revision, frame_id, width:1280, height:720}`, `privacy`, `session`, `restarts`. `GET /pc/frame.png[?revision=ID&full=1]`: PNG
from a CDP screencast (acked at once, at most 10 fps; `full=1` is 1920x1080; 409 on a stale `revision`, 404 while restarting).
`POST /pc/graphical-input`: PS/2 scancodes and relative mouse, forwarded to the page as key codes (Shift works) and mouse
events; `native_receipt` is answered. `POST /pc/input`: text into the focused field. `/pc/session`, `/pc/privacy` as the
runner (privacy refuses frames, input and the agent API with 409). `/devices/*` goes to the home backend.

## Agent API
`GET /desktop/observe`: `{frame_id, url, title, jpeg_b64 (1280x720 with numbered marks), width, height, text (visible, at
most 3000 chars), marks[{id, role, label, box:[x,y,w,h], href?}], scroll{y,max}, loading, dialogs[]}`. Marks cover links,
buttons and text fields in view (at most 60); coordinates are in the 1280x720 image. Marks are valid for the latest
observation only.
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
