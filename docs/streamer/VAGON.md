# Vagon as SUB-01's PC (updated 2026-10-23)

Two Vagon products exist and this repository has touched both. **The owner's real PC is a Vagon Cloud Computer** (the
Teams / workstation product): it already exists and works, it is reached at https://app.vagon.io/workstation, it has
Steam and *Detroit: Become Human* installed, and that page requires **his Vagon account login** (opened from the pod's
Chromium it lands on the login page). It is not a Streams link and he does not buy Vagon Streams. Part A below is the road
that connects this existing computer to SUB-01: an authenticated browser session that he opens once himself, plus
desktop capture. Part B keeps the earlier Vagon Streams research for reference (nothing of it is bought or needed).

Nothing here was verified against the live Vagon pages: this environment has no Vagon account and makes no Vagon call.
We never buy, sign up for or start a Vagon service; the owner provides the account and the computer.

## Part A. The owner's Cloud Computer through `--pc-mode vagon`, kind `workstation`

### A1. How it works (scripts/streamer_desktop.py, docs/streamer/DESKTOP.md "Vagon mode")

- The streamer desktop runner's kiosk Chromium (Xvfb :102, 1920x1080, persistent profile under
  `<data-dir>/profile`, i.e. `/home/unreal/.sub01-private/streamer/desktop/profile`) opens the workstation page. The
  profile is reused across relaunches and restarts (the runner only removes Chromium's `Singleton*` lock files), so a
  login survives them until Vagon's own session expires.
- **The runner never has or types credentials.** When the page is a login page (URL path `/login`, `/signin`, `/auth`,
  `/verify`...; a visible password field; sign-in text without any computer control) the state becomes
  `phase: login_required` and the runner serves the **operator console** at `GET /operator`: a self-contained page that
  shows the live kiosk screen (2 fps) and forwards the owner's mouse and keyboard with the admin token he pastes once.
  The owner logs in on the Vagon page himself (section A2). The console disappears a few minutes after the login page is
  gone and never exists while the desktop is connected (`--operator-console` keeps it always).
- After the login, the runner presses the controls it finds by text, every press logged in `events.jsonl` as
  `vagon_button`: `Run` / `Start` / `Turn on` (the computer is off: `machine: off`), then `Connect` / `Open` / `Enter`
  (`machine: on`), waits for the stream (`video`, or a `canvas` covering at least half the viewport), then the existing
  stream mapping applies: click/scroll/type/key over the stream, navigate/search as Ctrl+L, URL, Enter in the remote
  browser, back as Alt+Left. "Session ended / disconnected / turned off" states are handled like the stream mode:
  `Reconnect` or `Run` + `Connect` again, else the page is reopened with 15 s to 5 min backoff (`reconnects`,
  `last_reconnect_utc`). Never pressed: Stop, Shut down, Delete, Reset, Restart, Sign out, Settings, Billing, Team,
  Members, Invite, Upgrade, Buy, Sign in and anything money- or account-like.
- **Privacy lock.** Until the remote desktop is connected, `/desktop/observe` returns a grey "PC not connected" picture
  with `remote_ready: false` and `/pc/frame.png` (the monitor texture, the recording) shows the same picture: the model
  and the viewers never see the login page, the dashboard, the team name or anything of the account; the observation's
  `title` is always `remote desktop` and its `url` is the host only. The kiosk page may navigate only within the site of
  the configured page (`app.vagon.io` and its sibling hosts such as `login.vagon.io`, `stream.vagon.io`): login and
  verification paths are allowed, **billing, payments, invoices, subscription, plans, team, members, organization,
  settings, account, profile, api keys, security, usage, files, storage, sign-up, admin, users, credits** and every other
  site are refused at the network level and, once committed (SPA route changes included), replaced by the workstation
  page; each refusal is logged (`blocked`, host only) and counted in `/pc/state.vagon.blocked`.
- `/pc/state.vagon` in this kind: `kind: "workstation"`, `phase`
  (`login_required | dashboard | starting | connecting | connected | ended | blocked`, plus `opening` right after the
  page is (re)opened, `blank` while nothing is recognised, `restarting` while the browser relaunches), `logged_in`,
  `machine` (`unknown | off | starting | on`) and `machine_source` (`page` or `api`), `blocked`, `login_why`,
  `operator_console` (served right now), `last_reconnect_utc`, `reconnects`, `sessions`, `reloads`.
- Optional Teams API (`vagon_pc.py`, unverified against the live API, see docs/design/vagon-pc/README.md):
  `api_key_file` (mode 0600, one line `KEY:SECRET` or two lines) and `machine_id` in `vagon.json` give the `machine` field
  from `GET /machines` every 60 s and `POST /pc/vagon/start` (admin token) to start the computer; the connect loop also
  starts it through the API when the page offers no start button and the API says it is off (at most once per 5 min).
  Keys stay in memory; errors are scrubbed by `vagon_pc`; nothing is logged but the outcome.

### A2. The owner's one-time login (exact steps)

1. On the pod (uid 1001), write the config, mode 0600:
   ```
   /home/unreal/.sub01-private/streamer/vagon.json
   {"schema": "sub01.streamer-vagon.v1", "kind": "workstation", "url": "https://app.vagon.io/workstation"}
   ```
   (`url` may be left out: that is the default. Without any file, the same is `--pc-mode vagon --vagon-kind workstation`.)
2. Start the desktop runner in vagon mode, e.g. `scripts/streamer_up.py start --child-arg desktop='--pc-mode vagon'`
   (or the manual command in DESKTOP.md with `--pc-mode vagon`). The log says `vagon mode (workstation)`, then
   `the Vagon page needs the owner's login (path); the operator console is at /operator`; `/pc/state.vagon.phase` is
   `login_required`.
3. Read the token on the pod: `cat /home/unreal/.sub01-private/operator-token`.
4. In his own browser, logged into the pod's Jupyter server, open
   `https://<pod>-8888.proxy.runpod.net/proxy/8832/operator`. The page asks for the token: paste it, press **Use token**.
   It stays in that tab only (sessionStorage) and is sent as `X-Admin-Token`; **Forget token** removes it. The kiosk's
   screen appears (the Vagon login page) and the header shows `login_required · logged_in=false · machine=unknown`.
5. Click the e-mail field on the picture, type the e-mail, press Tab, type the password (or paste it with Ctrl+V: the
   console sends the clipboard text as typed text), press Enter. If Vagon asks for a verification code, type it the same
   way. Letters, Tab, Enter, Backspace, arrows, Shift and Ctrl combinations go to the kiosk; the runner logs none of it.
6. When the workstation page appears the runner takes over: `logged_in=true`, then `Run`/`Connect` are pressed by it
   (`vagon_button` events), `machine` goes `off → starting → on`, `phase` ends at `connected`, and the console closes
   itself (the page reports it; `/operator` answers 404). Check:
   `curl -s -H "X-Admin-Token: $(cat /home/unreal/.sub01-private/operator-token)" localhost:8832/pc/state | python3 -m json.tool`.
7. Nothing else to do until Vagon's session expires: then `phase` returns to `login_required`, the console is served
   again and `events.jsonl` has a `vagon` / `login_required` line. The agent meanwhile sees `remote_ready: false` and
   the neutral picture.

Caveats:
- **Sign in with Google / Apple / Microsoft cannot work through the runner**: those hosts are refused by the runner's
  rules (owner services), their popups are closed, and the kiosk is not his browser. Use Vagon's e-mail + password login;
  if the account was created with Google, set a password in Vagon's account settings first (from his own browser, not
  through the console: the console never reaches account pages).
- Two-factor codes typed in the page work through the console; a second factor that needs a popup or another device's
  approval has to be approved on that device. A captcha can be solved on the picture (clicks are forwarded).
- If the console is not enough (something the kiosk layout hides, a popup the runner closes), start the runner with
  `--no-kiosk --operator-console` and look at display :102 directly (an `x11vnc -display :102` session on the pod, over
  an SSH tunnel): the same profile, so the login done there is kept. `--operator-console` alone keeps the console up at all
  times, including while connected (then the owner's keys reach the remote desktop too).
- The Windows side is the owner's: Steam must stay logged in on the machine itself ("remember me"), Windows must not
  lock or ask for a password on the stream; the runner only sees pixels there.

### A3. What remains unknown until the real page is seen

The login page's URL and form (e-mail + password, or only social logins); whether the dashboard and the stream are the
same page, an iframe, a sibling host (the lock allows `*.vagon.io`) or **a new tab** (the runner closes popups today; if
Vagon opens the stream in a new tab the fix is to adopt a popup on the site as the main page); the real control texts
(`Run`? `Start`? `Connect`? `Open`?: tune `VAGON_WS_START_RX` / `VAGON_WS_CONNECT_RX`, every press and every unmatched
label list is in `events.jsonl`); the stream element (`video` or `canvas`) and whether it fills the viewport; the exact
"session ended" / "computer turned off" texts (`VAGON_ENDED_RX`); how long Vagon's web session lasts before a new login;
the computer's auto-stop and the cost per hour of the owner's Teams plan (the runner reconnects whenever the session
ends: with an auto-stop that is a machine start each time); whether CDP-dispatched input counts as activity for Vagon's
idle timer; the keyboard layout the remote Windows uses; whether Chromium's software WebRTC decode on Xvfb keeps 1080p
smooth on the pod's CPU; UDP egress from the pod; and the Teams API facts listed in docs/design/vagon-pc/README.md
(signed path, field names, status strings).

### A4. Tests

`tests/test_streamer_desktop_workstation.py`: the navigation lock, the classifier and button choice, the config, the
operator input validation, the neutral frame, the API wrapper against a fake HTTP opener, the HTTP routes against stub
desks, and, in a real headless Chromium on mock pages (`tests/fixtures/vagon_mock_login.html`,
`vagon_mock_workstation.html`, `vagon_mock_account.html`): login detection, the console served only then and only with
the token, the login done through it, Run/Connect/Reconnect/Run again, the neutral picture until connected, the lock
against billing/settings/external pages, the login surviving a restart in the profile, and the console page working
behind a `/proxy/8832/` path prefix in a second real browser.

### A5. The real page, seen on 2026-10-23: what stalled, and what the runner does now

The owner has a personal Vagon Computer (plan "Planet"; Streams and Teams only show onboarding pages on this account). He
logged in through the operator console on the second runner (port 8838, display :103, data dir `streamer/desktop-vagon`,
profile kept). The page then stayed on Vagon's loading cubes for an hour. What `events.jsonl` and the new `vagon_diag` rows
showed, in order:

1. **Widget pressed as a control.** The dashboard's first "connect" candidate was Intercom's launcher, `Open Intercom
   Messenger` (a `role=button` in the main document; "Open" matched `VAGON_WS_CONNECT_RX`). It opened the support panel
   (`Close`, `Send us a message`, `Search for help`, ...). Fixed: `control_verdict` never presses widgets (`VAGON_WS_WIDGET_RX`
   on the label, the `widget` flag the probe sets from the element's ancestors, and sub-frames named/hosted like widgets
   such as `intercom-frame` and `consentcdn.cookiebot.com` lose their controls); the main document's controls come first;
   every candidate set is logged once per page state as `vagon_controls` (labels only, e-mail addresses masked).
2. **Blind reloads.** `connecting` was reloaded every 120 s (10 reloads in an hour). Fixed: `workstation_reload_reason`:
   a connecting page is opened again only after 6 minutes AND when it is dead (`page_dead`: no request, WebSocket frame or
   WebRTC byte for 60 s and no video/canvas), on an explicit ended text without a way back in, or on the owner's request
   (`POST /pc/vagon/reload`, token). `connected` needs `stream_evidence` (decoded frames, or a repainting canvas), not an
   element.
3. **Console closing.** The console vanished 10 minutes after the login although nothing was connected. Fixed:
   `operator_allowed` serves it the whole time the desktop is not connected (and `OPERATOR_CONNECTED_GRACE_S` after).
4. **The actual stall: no H.264 in the kiosk browser.** Vagon's player is Unreal Pixel Streaming's web client
   (`/webRtcPlayer.js`, `getSupportedVideoCodecs`, `PreferredCodec`, `intersectUEAndBrowserCodecs`). The server's WebRTC
   offer carries **H264 only** (`video: 123 H264 pl=42e01f` on all four video m-lines, `111 opus`, a data channel, TURN
   `prod-turn-int-stockholm-1.proxy.vagontech.com:443` udp and tls). Playwright's bundled Chromium 140.0.7339.16
   (`~/.cache/ms-playwright/chromium-1187`) has no H.264 at all: `RTCRtpReceiver.getCapabilities('video')` = VP8, VP9, AV1;
   `MediaSource.isTypeSupported(avc1)` false; `VideoDecoder.isConfigSupported(avc1)` false (the Playwright docs say so: the
   bundled Chromium lacks the proprietary codecs). The browser's answer therefore **rejects every video m-line**
   (`video: 0 | video: 0 | video: 0 | audio: 111 opus | ... | application`), the received video track ends at once
   (`video:ended`, 2x2, hidden `<video>`), ICE never starts (`dtls new`, `ice new`, no candidate pair), the server closes
   the peer connection after about a minute and the client makes a new one (`created` 1, 4, 6, 8...). WebGL2 works (ANGLE/
   SwiftShader, also with `--disable-gpu`), WebCodecs and WebGPU exist, `play()` was never refused, user activation is
   true: GPU, autoplay and rendering are not the cause, and no flag of the bundled Chromium adds H.264.

**What is needed:** a browser with H.264 decoding on the pod, used ONLY with the runner's own profile. None is installed
(`find` for google-chrome/chromium/firefox/libffmpeg: only the Playwright build; Unreal's CEF is not a browser). The runner
already takes `--chromium PATH` (and the supervisor `--child-arg "desktop=--chromium PATH"`); Google Chrome stable
(`google-chrome-stable` .deb, ~110 MB, or `playwright install chrome`) would open the Chromium 140 profile with the login
intact. Installing it is a decision for the owner (disk: 3.7 GB free). A Vagon-side codec change is not available to the
client: the codec intersection is done against the server's H264-only offer. UDP egress from the pod works (STUN binding
requests to stun.l.google.com, stun.cloudflare.com and Vagon's TURN host over UDP all answered, public address mapped;
TCP 443 to the TURN host open), so the H.264 browser is the only missing piece; the `701 STUN host lookup` candidate
errors Chromium logged are internal to it (relay candidates were still gathered over TURN-TLS). Judge the final path once
ICE runs (`vagon_diag.rtc.stats.pair`: `relay`/`tcp` means TURN-TCP only).

**Chromium flags** (`streamer_desktop.py`): `--gpu off|swiftshader|on` (default `off` = `--disable-gpu`), `--autoplay`
(`--autoplay-policy=no-user-gesture-required`), `--chromium-arg=--flag=value` (repeatable). They are recorded in the
`start` event and in `vagon_diag.browser`. Diagnostics: `/pc/state.vagon.diag` and `vagon_diag` rows every 30 s while
connecting (page, iframes, video/canvas elements, WebGL, WebCodecs, codecs, WebRTC states/SDP codecs/candidate pairs/
stats from an init script, console errors, failed requests and HTTP errors by host, network activity).

### A6. Input on the connected desktop (measured live 2026-10-23, runner 8838, Google Chrome)

**The page.** The stream is one `video#player` in the main document (1918x1079, pointer-events auto); nothing covers it
(a 5x4 hit grid finds the video at all 20 points). Vagon's own handle ("Click to Open", a `div` at about x 707-757,
y 16-66 of 1920x1080) opens its toolbar (Audio, Microphone, Webcam, Fullscreen, Display settings, System, Files, **Power**).
Listeners (counted by `INPUT_INIT_JS`): keydown/keyup/keypress on `document` and the React root; mouse/pointer/wheel on
the video. Input leaves on the data channel labelled `control` (idle between actions). No pointer lock, no keyboard lock
outside fullscreen. WebRTC: H.264 1920x1080 at 30 fps, frames_decoded rising, 0 lost, srflx -> relay over UDP, RTT 70-100 ms.

**Why input looked broken, and the fixes in `streamer_desktop.py`:**
1. *Control chords never arrived.* Vagon's keyboard layer (client bundle: `keyDownHandler`, `startPendingCtrl`) holds a
   Left-Control keydown 15 ms to tell it from AltGr and drops a key that arrives inside that window, the pending Control
   with it. Playwright's `press("Control+a")` sends the "a" microseconds later: Ctrl+A, Ctrl+Escape and the navigate
   action's Ctrl+L never reached Windows (measured: 2 keydowns, only the 2 keyups on the channel). Fix: `_vagon_chord`
   holds the modifiers `VAGON_CHORD_HOLD_S` (0.1 s) before the key; the scancode path waits after a Control keydown.
   After it: Ctrl+A selects the YouTube search text (8 control messages), Ctrl+Escape opens Start.
2. *The "dim".* The player forwards Ctrl+A without preventing it, so Chrome also ran the HOST page's select-all and
   painted its selection tint over the whole video until the selection was cleared (the dark overlay of the first
   attempt). Fix: `VAGON_FOCUS_JS` clears a host Range selection before keys and adds, once, a window-bubble keydown
   listener that cancels the host page's default for modifier chords, Tab, Escape and F1-F12 aimed at the stream
   (after the player's own listeners; propagation and plain characters untouched). This also stops Alt+Left (`back`)
   from navigating the host page.
3. *Focus.* Keys need only the DOM focus on the stream element (Meta opened Start with no mouse event at all); no click,
   hover or pointer lock first. Every key path focuses it and fails closed when it does not take the focus.
4. *Clicks.* `VAGON_HIT_JS` lets a click/wheel through only when the stream element itself is the top element at the
   point (and, for a stream inside an iframe, the iframe is the top element of the parent page there), checked before
   the pointer moves, 0.1 s after it, and before every wheel step; anything but an explicit yes is a refusal. The handle,
   its menu, dialogs, dim/backdrop and transparent layers are refused (`blocked` event, the error says why). A click on
   the handle position was refused live.
5. *The earlier session end and stop* (a click at the taskbar Start position, then "Rate Session" two minutes later with
   no input) are not explained by the input path; the dashboard shows an idle setting "15 minutes" (unverified).

**Diagnostics.** `GET /pc/vagon/diag` (token; at most one per 2 s) returns a fresh snapshot; `vagon_diag` rows come at
connect, 8 s later (the first stats) and every 60 s while connected. `diag.rtc`: the live peer connection first
(`live`, `bytes`, `frames_decoded`, `fps`, `pair`, `dc_out` per label, `ws_out`); `diag.input`: focused element, pointer
lock, host selection, the cover grid and the counters (key/mouse/wheel events, how many the player prevented,
listeners by target). Counts and element tags only: never a key, a character or page text.

## Part B. Vagon Streams research (kept for reference; not the owner's product)

Sources: https://docs.vagon.io/streams and its sub-pages (introduction, guides, configurations, integrations, custom
flows), https://vagon.io/streams/pricing, https://vagon.io/streams/terms-and-conditions, the two help-center articles
on Streams, all read on 2026-10-23. `vagon_pc.py` / `docs/design/vagon-pc/README.md` target the **Teams / Cloud
Computer** API (`api.vagon.io/organization-management/v1`), the product the owner actually has; this part is about
**Vagon Streams** (`api.vagon.io/app-stream-management/v2`, `app.vagon.io/stream/...`): an uploaded *application*
streamed into a browser page, machines provisioned per visitor. The runner's `kind: "streams"` (the default) targets it
and stays available.

### B1. What a Stream is

- An **Application** is a `.zip` of a build with its executable at the root; "You can stream both Windows and Linux
  applications". A **Stream** orchestrates **Stream Machines** (GPU VMs) in chosen **Regions** with a **Capacity**; it is
  reached through one **Stream Link** (`https://app.vagon.io/stream/<STREAM_ID>`) or the dashboard's iframe code.
- A **Stream Session** is one machine's life from `waiting` to `terminated`; a **Visitor Session** is one visitor's
  connection. Default `Restart Application for Each Visitor` is **enabled**: the application restarts (and loses its
  state) between visitors. Machines are ephemeral; the only documented storage is `T:\PreloadedFiles` and
  `T:\Temp Files`. Nothing says a visitor can reach a Windows desktop: the stream starts the one executable chosen in
  the dashboard, so for SUB-01 that executable would have to be a browser.
- Streaming protocols: Vagon Application Streaming (default; "30FPS streaming quality in any network condition", up
  to "4K, 60FPS"), Unreal Pixel Streaming, Unity Render Streaming. Transport: "WebRTC connection over a P2P network".

### B2. Creating a stream (dashboard, owner's account)

Upload the application `.zip`, pick the executable, a performance type, the cursor mode (Mouse Control for a browser);
**Streams > New Stream**: application, regions (Europe: Dublin, Frankfurt, Stockholm), capacity (Cost Optimized
`on_demand`: "around 2 minutes" to connect; Balanced: reserved idle machines; Availability Optimized `always_on`);
resolution, audio, keyboard layout, connection page, limits, availability schedule; copy the Single Link or the iframe.
API alternative: `POST /streams/{id}/assign-machine {region, user_id?}` returns a `connection_link`;
`start-machine`, `stop-machine`.

### B3. Embedding and the web SDK

`<script src="https://app.vagon.io/vagonsdk.js">` and an iframe with `allow="autoplay; microphone *; camera *;
fullscreen; clipboard-read *; clipboard-write *; encrypted-media *;"`. `window.Vagon`: `isConnected()`, `startStream()`
(what the play button does; needs a user gesture), `focusIframe()` (the documented fix for keyboard input problems),
`resizeFrame()`, `keepAlive()`, `shutdown()`, `setQuality()`, `setVideoVolume()`, `showKeyboard()/hideKeyboard()`,
`enableGameMode()`, `sendApplicationMessage()`, `getSessionInformation()`. Events `onConnected`, `onDisconnected`,
`onApplicationMessage` on every plan; the rest Enterprise only. URL parameters: `?launchFlags=` (stored in local
storage, re-applied on reconnect; `&newSession=true` resets), `?visitor_email=`. The link may carry secrets: the runner
never logs its path or query.

### B4. API credentials and authentication

Per Stream: API Public Key, API Secret, Application ID. `Authorization: HMAC {key}:{signature}:{nonce}:{timestamp}`,
signature = hex HMAC-SHA256(secret, `key + METHOD + path + timestamp_ms + nonce + body`), path with the
`/app-stream-management/v2` prefix. Endpoints: `GET /applications`, `GET|POST|PUT|DELETE /streams`, `PUT
/streams/{id}/activate|pause`, `GET /streams/{id}/machines`, `start-machine`, `assign-machine`, `stop-machine`,
`POST /users`, `GET /machines`, `GET /sessions`. Machine `connection_status`: `waiting`, `available`, `assigned`,
`connected`, `terminated`, `proxy-in-migration`. Error codes: 4601 insufficient capacity, 4603 region not active,
4609 stream not active, 4610 start-machine needs Cost Optimized.

### B5. How keyboard and mouse reach the remote machine

The stream page captures the browser's own DOM input events and sends them over the WebRTC data channel; no other input
path is documented. In our runner the kiosk Chromium *is* the visitor's browser: Playwright dispatches real, trusted key
and mouse events through CDP and the Vagon client forwards them like a human's. `navigate`/`search` therefore mean
"Ctrl+L, type the URL, Enter" in the remote browser. The runner re-focuses the stream element before every key and
clicks the button it finds by text. Network from the visitor's side: TCP/UDP 443, TCP/UDP 3478, UDP 49152-65535 to
Vagon's per-region addresses; the pod's UDP egress is not verified.

### B6. Costs and limits as documented (2026-10-23)

Pay per minute of machine time; Starter T4 $0.025/min (~$1.50/h), Pro T4 $0.035, Starter G2 A10G $0.036, Pro G2 $0.046,
Starter G3 L4 $0.036, Pro G3 $0.047; plus storage **$0.67/day per region** and maintenance **$0.67/day**; plan fees
unpublished; concurrent capacity per link 25 / 50 / custom. A browser streamed 8 h/day on Starter: about $12/day plus
$1.34, about $400/month. Limits: Session Duration Limit, Idle Duration Limit, Auto Turn-Off, budget limit (Enterprise),
availability schedule ("Stream is Expired" page), `paused` status; resolution 720p/1080p/4K or scale-to-screen; 30 FPS
adaptive.

### B7. Usage rights

Streams terms (18.02.2022): prohibited illegal use, "disabling or circumventing features that prevent or limit access",
reverse engineering, malware, interfering with networks; "VAGON CAN PAUSE THE SERVICES ANYTIME IT WANTS". Nothing
addresses a scripted visitor on one's own stream. The Cloud Computer terms (docs/design/vagon-pc/README.md, 5.1) say the
machine is "accessed and used through the interface provided by the Company": the runner uses exactly that interface
(the web client in a real Chromium) with the owner's own login; before SUB-01 goes live the owner should still ask Vagon
(support@vagon.io) whether an automated operator of his own computer, reconnecting after session ends, is acceptable.

### B8. What a Streams setup would need from the owner (not pursued)

A Streams account, an uploaded application that is a browser, an active Stream, the Stream Link in `vagon.json`
(`kind` left at `streams`, `stream_url`), settings 1080p or scale-to-screen, Mouse Control, English US keyboard, audio
off, limits and a budget, region Frankfurt or Stockholm; optionally the Streams API key pair.

### B9. What we cannot know without an account

The connection page's DOM; the exact "session ended" / "stream expired" texts; whether CDP-dispatched input counts as
user action for the idle limit; whether the per-visitor restart can be disabled on Basic; connect times; plan prices;
whether Chromium's software WebRTC decode keeps 1080p30 smooth on the pod's CPU; UDP egress. The runner's text heuristics
(`VAGON_CONNECT_RX`, `VAGON_ENDED_RX`) may need one tuning round against the real page; `events.jsonl` records every
press and phase change for that.

### A7. Starting the computer needs arming (2026-10-23)
Turning the owner's Vagon computer on spends his balance ($0.99/hour on his plan). The runner never starts it on its
own: when the computer is off it logs `vagon start_held` once and waits. `POST /pc/vagon/arm {"minutes": N}` (admin
token, 0-120, 0 disarms) allows ONE start within N minutes, through any path (the page's Run/Start button, the Teams API
fallback, `POST /pc/vagon/start`). `--vagon-autostart` restores starting on its own. `/pc/state.vagon` shows
`autostart`, `start_armed_s`, `start_held`, `starts`. Connect/Reconnect on a computer that is already on are not gated.
The computer also stops by itself after the owner's idle setting (seen: 15 minutes).
