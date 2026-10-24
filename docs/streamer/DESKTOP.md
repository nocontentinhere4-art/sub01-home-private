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
`--pc-mode chromium|vagon` (default `chromium`), `--vagon-kind streams|workstation`, `--vagon-url`, `--vagon-config`,
`--streamer-dir`, `--operator-console` (see "Vagon mode"), `--allow-credentials` / `--no-allow-credentials` (vagon mode
only, default on, env `STREAMER_ALLOW_CREDENTIALS`; see "Logins on the remote PC").

## PC contract (same as `home_pc_runner.py`)
`GET /pc/state[?since=REV&wait=S]`: `status` (`ready|starting|restarting`), `ready`, `display{kind:"graphical", available,
revision, frame_id, width:1280, height:720}`, `privacy`, `session`, `restarts`, `pc_mode` (`chromium|vagon`; in vagon mode
also `vagon{kind, connected, phase, reconnects, last_reconnect_utc, sessions, reloads, since_utc, api_key_file,
operator_console}` plus, for the workstation kind, `logged_in, machine, machine_source, blocked, login_why`; the privacy
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
- Refused: adult, gambling, banking/payment, crypto, trading, login/account and checkout hosts and paths, owner services,
  private addresses, ports other than 80/443, downloads and common file types, POST navigations, sub-frames of such hosts.
  Wikipedia `/wiki/` titles are exempt from the path rules. Redirects are checked from the 3xx answer and again once
  committed. Host classes (`blocked_host`): `adult`, `gambling`, `banking`, `payment`, `crypto` (exchanges and wallets,
  also when `browse.py` is not deployed next to the runner), `owner-service` (claude.ai, console.anthropic.com, runpod.io,
  railway.app), `login` (`login.`/`signin.`/`sso.`/`auth.`/`accounts.`... hosts and the providers' account hosts:
  accounts/mail/myaccount.google.com, login.microsoftonline.com, login.live.com, outlook, appleid.apple.com, icloud.com),
  then browse.py's `blocked-site`. Only the remote PC's `--allow-credentials` lifts `login` (below).
- Never done: file chooser, clipboard (API, init script, key combos), downloads, popups (closed), password/e-mail/card fields,
  typed card numbers; dialogs are dismissed and listed in `dialogs` / `outcome.dialog`. Cookie banners get the reject button.
- A crashed browser is relaunched in about 2 s, a hung one (no answer to a heartbeat, a 20 s page read) in about 30 s, backoff up
  to 30 s; the new browser starts on `about:blank`. `restarts` counts relaunches.
- No audio (`--mute-audio`); one tab; mark numbers need a fresh observation after any page change.
- Logs: `streamer desktop: ...` on stdout; every action, outcome, block, dialog and relaunch in `<data-dir>/events.jsonl`.

## Vagon mode (`--pc-mode vagon`; research and the owner's part in VAGON.md)
The same kiosk Chromium shows the owner's Vagon page instead of browsing: the remote machine's pixels fill the
1920x1080 display, so the monitor texture, the director and the agent loop do not change. Everything above stays as it
is in `chromium` mode; nothing changes by default. Two kinds (`kind` in the config file, or `--vagon-kind`): `streams`
(a public Vagon Streams link, the default, below) and `workstation` (the owner's Vagon Cloud Computer behind his login,
see "Workstation kind" further down).

Configuration: the stream link comes from `--vagon-url` or, preferably (a command line is visible to other users on the
pod), from `<streamer-dir>/vagon.json` (`--streamer-dir`, default `$STREAMER_DIR` or `/home/unreal/.sub01-private/streamer`;
`--vagon-config PATH` names another file), mode 0600:
```
{"schema": "sub01.streamer-vagon.v1", "stream_url": "https://app.vagon.io/stream/...", "api_key_file": "/path (optional)"}
{"schema": "sub01.streamer-vagon.v1", "kind": "workstation", "url": "https://app.vagon.io/workstation",
 "api_key_file": "/path (optional)", "machine_id": "optional, for the API"}
```
`stream_url` must be https, without credentials, on a host the page rules allow; `--vagon-url` wins over the file (and
`--vagon-kind` over `kind`). In the streams kind `api_key_file` is only checked for presence and mode
(`vagon.api_key_file`: `none|configured|missing|permissive`) and the runner makes no Vagon API call. The link is a
credential: logs, events and `/desktop/observe.url` carry only `https://app.vagon.io/…` (never the path, query string or
fragment; Playwright error texts are scrubbed too). `--start-url` is ignored in this mode.

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

### Logins on the remote PC (`--allow-credentials`, default on; owner's decision of 2026-10-23)
The owner lifted the credentials block for SUB-01's own decisions on HIS PC. In vagon mode only, `navigate{url}` (the URL
typed into the remote browser's address bar) is checked with the `login` host class and the login paths lifted
(`blocked_url(url, allow_login=True)`): accounts.google.com, mail.google.com, login.microsoftonline.com, appleid,
`/login`, `/signin`, `/account`, `/oauth`, `/sso`, `/register`, Wikipedia's Special:UserLogin... are opened. Still refused
with the flag: banking, payment and checkout/cart/billing paths, crypto, adult, gambling, trading, downloads, private
hosts, odd ports, credentials in the URL, the owner's infrastructure consoles (`owner-service`: claude.ai,
console.anthropic.com, runpod.io, railway.app; `login.runpod.io` too: that class is checked whatever else matches), and
account CHANGES (`account-change-path`: change/reset/forgot password, security, recovery, 2FA/MFA, sign-in options,
delete/close/deactivate account: the agent's `account_change` class, authentication is not account mutation). What the
flag does not touch: the pod's own Chromium (chromium mode: every login rule stays), click marks, typed-text rules (card
numbers, adult words), and the Vagon host page's own navigation lock (`workstation_request_blocked`: app.vagon.io account,
billing and team pages and every other site stay blocked for the kiosk page itself).
On the remote PC every navigate also goes through `remote_url_problem`, flag or not (its Chrome profile may already be
signed in; Kimi's review of 2026-10-23): refused there as well are the owner's Vagon console (`vagon.io`, as
`owner-service`), password vaults (passwords.google.com, 1Password, LastPass, Bitwarden, Dashlane, Keeper, NordPass:
`password-manager`), takeout.google.com (`data-export`), account portals beyond their root and sign-in pages
(myaccount/account.google.com, account/myaccount/mysignins.microsoft.com, account.live.com, appleid/account.apple.com:
`account-settings`: only `/`, `/sign-in`, `/signin`, `/login`, `/log-in`, `/servicelogin` pass, fragment routes
included), MediaWiki's account pages (`Special:ChangePassword`, `PasswordReset`,
`ChangeEmail`, `OATHManage`, `BotPasswords`, `Preferences`...: `account-change-path`, also as `?title=`), account security
and delegation (app passwords, passkeys, security keys, backup/recovery codes, access tokens, API keys, SSH/GPG keys,
device activity, security info, third-party/connected/authorized apps, data export, OAuth `consent`/`authorize`, Google's `/o/oauth2/`,
`/settings/tokens|keys|applications|sessions|emails|security...`: `account-security-path`), money inside account pages
(`/payments...`, `/payment-methods`, `/billing`, `/purchases`, `/redeem...`, `/addfunds`, `/gift-cards`, `/buy`, `/sell`,
`/swap`... also in a single-page app's `#/route`, and `?add-to-cart=` / `?checkout=` query actions, also in the route's
own query: `checkout-path`; a password change named inside a segment or with a suffix, `/HelpChangePassword`,
`/reset-password.html`, counts too; wiki articles such as `/wiki/Security` or `/wiki/Payment` keep their exemption),
adult words in the URL itself (`unsafe-text`), a login page over plain http (`insecure-login`), and any URL embedded in
the query or fragment (`continue=`, `redirect_uri=`, `q=`) that the same rules refuse (`redirect-target (...)`, three
levels deep). A `type` whose whole text is one URL (`typed_url`: any scheme, `chrome://...` and `file:` included, which
are refused; or a host with a TLD, an IP literal, localhost or a trailing dot, with a port and path; not an e-mail or a
word) gets the same check: the address bar typed by hand (`http:127.0.0.1/` as Chromium reads it too). Limit: a single-label
name (`intranet.`, `router/`) is not taken for a URL, so passwords such as `Hello123.` or `abc/def` stay typeable. Paths are resolved like a browser does first (`/wiki/../checkout` is `/checkout`, in both modes). Limit:
the runner sees pixels only, so the remote browser's final URL after redirects cannot be checked; these rules check what
is typed, and the agent's own policy and privacy detection are the other half. `/pc/state.allow_credentials` and the
`start` event say whether it is on; `--no-allow-credentials` (or `STREAMER_ALLOW_CREDENTIALS=0`) turns it off; a bare
`Config` defaults to off. Logging (`loggable_url`): a URL that may carry a secret (credentials in it, a login, account,
account-change or account-security page by host or path, a query parameter named like a token, code, key, password or
session, in the query or the fragment such as `#access_token=`) is logged as `scheme://host/…` only, in both modes; every other URL navigated on the remote PC is logged without
its query and fragment; and every `type` on the remote PC is logged as `[typed N chars]` (pixels
cannot tell a password field; the agent keeps its own masked audit). The agent decides what is private and asks the
director to hide the desktop before a credential is typed (AGENT.md "Logins and installs", RUNBOOK.md "Privacy cut").
Tests: `tests/test_streamer_desktop_vagon.py` (the `--allow-credentials` section).

Limits: the remote application must be a browser with its window focused for navigate/search to mean anything; no DOM,
so no marks, no page text, no URL of the remote page, no dialogs from the remote machine; Vagon's own limits (session and
idle durations, capacity, cost per minute) are the owner's settings and are in VAGON.md; the connection page's real
button texts are unknown until the owner's stream is seen. Tests: `tests/test_streamer_desktop_vagon.py` (pure mapping
logic, and a real headless Chromium against the mock stream page `tests/fixtures/vagon_mock_stream.html` /
`vagon_mock_embed.html` when a Chromium build is available; skipped with a reason otherwise).

### Workstation kind (`kind: "workstation"` or `--vagon-kind workstation`; the owner's steps in VAGON.md, A2)
The page is the owner's Vagon Cloud Computer, https://app.vagon.io/workstation (the default `url`), which needs his
account login. The runner never has or types credentials; the persistent profile (`<data-dir>/profile`, reused across
relaunches and restarts) keeps the login once he has done it.

Phases (`/pc/state.vagon.phase`, `events.jsonl` kind `vagon` with `state`): `opening` (page being (re)opened),
`login_required` (login page: URL path `/login|/signin|/auth|/verify|...`, a visible password field, or sign-in text on a
page without a computer control; `login_why` says which), `dashboard` (a control was found: `Run|Start|Turn on` means
`machine: off`, `Connect|Open|Enter` means `machine: on`), `starting` (the page says the computer is turning on),
`connecting`, `connected` (a playing `video`, or a `canvas` covering at least half the viewport, and no ended text),
`ended` (ended/disconnected text or a `Reconnect|Try again` control), `blocked` (an account page reached: the runner
returns to the workstation page), `blank`, `restarting`. Every press is an event `vagon_button{label, button:
start|connect|reconnect, phase, attempt}`; a phase without a matching control logs the visible button labels (first 12,
32 chars) so the heuristics (`VAGON_WS_START_RX`, `VAGON_WS_CONNECT_RX`, `VAGON_WS_NEVER_RX`, `VAGON_ENDED_RX`) can be
tuned against the real page. Never pressed: stop/shut down/turn off/delete/reset/restart/sign out/invite/settings/
billing/team/members/profile/upgrade/download and every login or money control. Presses: at most one per 6 s, six per
page load; `ended` → the control or the page reopened with 15 s to 5 min backoff; `starting` stuck 10 min, `connecting`
2 min, `dashboard` without a control 3 min, `blank` 1 min → page reopened. `logged_in` is true once workstation content
was seen and false on a login page; `machine` is `unknown|off|starting|on` from the page, or from the API when configured
(`machine_source`).

Operator console: `GET /operator` (no token: the page holds none) serves a self-contained HTML+JS page, available only
while the phase is `login_required` and for 10 minutes after it (second factors, consent pages), never once connected,
or always with `--operator-console`; otherwise 404 with a one-line explanation. It polls `GET /operator/frame.jpg` (the
raw screencast JPEG of the kiosk, 2 fps, ETag/304; token required) and `GET /pc/state`, and forwards the owner's input to
`POST /operator/input` (token required; refused without it): `{type: mouse, x, y}` as fractions 0..1 of the frame with
optional `buttons: [l, m, r]` and `wheel`, `{type: key, key: <code such as Tab, Enter, Backspace, ShiftLeft, KeyA>, down}`
and `{type: text, text}` (printable characters and pastes travel as text, so the owner's keyboard layout does not matter;
newlines press Enter). Clipboard combinations are dropped as everywhere; nothing typed is logged (the served page is
logged as `operator`). Every URL in the page is relative to its own location, so it works behind the pod's Jupyter proxy
(`https://<pod>-8888.proxy.runpod.net/proxy/8832/operator`); the token lives in that tab's sessionStorage and is sent as
`X-Admin-Token`. Bathroom privacy refuses the frame and the input with 409 like every other route.

Privacy lock: until `connected`, `/desktop/observe` returns the grey "PC not connected" picture (1280x720,
`remote_ready: false`, `title: "remote desktop"`, `url` host only, no text, no marks) and `/pc/frame.png` the same
picture, so the model, the monitor texture and the recording never see the login page or the account; `/desktop/act`
refuses everything but `wait` with `the remote desktop is not connected (PC <phase>)`. `/pc/input` and
`/pc/graphical-input` reach the page only while connected or while the console is allowed (the house's own input is the
owner's). Navigation lock: main-frame navigations (redirects, SPA route changes and link clicks included) may only stay
on the configured page's site (`app.vagon.io` and `*.vagon.io`); login/verification paths are allowed, account paths
(`VAGON_ACCOUNT_PATH`: billing, payments, invoices, subscription, plans, team, members, organization, settings, account,
profile, api keys, security, usage, files, storage, sign-up, admin, users, credits, cards) and every other site are
refused (`events.jsonl` kind `blocked`, host only; `/pc/state.vagon.blocked` counts them) and the kiosk is brought back to
the workstation page; a login form may POST. Sub-resources from the site are allowed, others follow the generic host
rules (CDNs yes, banks and the owner's services such as `accounts.google.com` no: Google sign-in cannot work here).

Optional Teams API (`vagon_pc.py`, never verified live): `api_key_file` (mode 0600; `KEY:SECRET` on one line, or two
lines) with `machine_id` → the key pair is read once into memory, `GET /machines` every 60 s feeds `machine`
(`machine_source: api`; `off|stopped` → `off`, `creating|turning_on` → `starting`, `ready|running|on` → `on`),
`POST /pc/vagon/start` (token) starts the computer when it is `off` (`{ok, machine, started, error}`; 409 without an
API, 502 on an API error, at most one start per 5 min), and the connect loop starts it the same way when the page offers
no start control and the API says `off`. Errors come from `vagon_pc` (credentials and links scrubbed); events
`vagon_api{action: start, why, ok}` and `error{where: vagon-api}`.

Limits of this kind: the real login page, control texts, stream element and ended texts are unknown until the owner's
page is seen (VAGON.md A3); if Vagon opens the stream in a new tab the runner still closes popups (fix: adopt a same-site
popup as the main page); social logins and popup-based second factors cannot be done through the console; the Windows
side (Steam login, screen lock) is the owner's to prepare. Tests: `tests/test_streamer_desktop_workstation.py` (pure logic,
HTTP routes with stub desks, and a real headless Chromium on `tests/fixtures/vagon_mock_login.html`,
`vagon_mock_workstation.html`, `vagon_mock_account.html`, including the console in a second real browser behind a
`/proxy/8832/` prefix).
