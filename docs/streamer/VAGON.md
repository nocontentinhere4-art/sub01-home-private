# Vagon Streams as SUB-01's PC (research, 2026-10-23)

Sources: https://docs.vagon.io/streams and its sub-pages (introduction, guides, configurations, integrations, custom
flows), https://vagon.io/streams/pricing, https://vagon.io/streams/terms-and-conditions, the two help-center articles
on Streams, all read on 2026-10-23. Nothing here was verified against a live stream: this environment has no Vagon
account and makes no Vagon call. We never buy, sign up for or start a Vagon service; the owner provides the stream.

Note the two Vagon products. `vagon_pc.py` / `docs/design/vagon-pc/README.md` target the **Teams / Cloud Computer**
API (`api.vagon.io/organization-management/v1`: a persistent Windows computer with a Vagon-hosted connection link).
This document is about **Vagon Streams** (`api.vagon.io/app-stream-management/v2`, `app.vagon.io/stream/...`), the
product the owner chose: an uploaded *application* streamed into a browser page, machines provisioned per visitor.

## 1. What a Stream is

- An **Application** is a `.zip` of a build with its executable at the root; "You can stream both Windows and Linux
  applications". A **Stream** orchestrates **Stream Machines** (GPU VMs) in chosen **Regions** with a **Capacity**; it is
  reached through one **Stream Link** (`https://app.vagon.io/stream/<STREAM_ID>`) or the dashboard's iframe code.
- A **Stream Session** is one machine's life from `waiting` to `terminated`; a **Visitor Session** is one visitor's
  connection. Default `Restart Application for Each Visitor` is **enabled**: the application restarts (and loses its
  state) between visitors; disabling it is documented with a warning about shared session data. Machines are
  ephemeral; the only documented storage is `T:\PreloadedFiles` (uploaded once, present in every session) and
  `T:\Temp Files` (visitor downloads). Nothing says a visitor can reach a Windows desktop: the stream starts the one
  executable chosen in the dashboard. **For SUB-01 that executable has to be a browser** (or a launcher that opens one);
  its profile, history and logins will not persist between sessions unless the owner disables the per-visitor restart
  and the machine stays up.
- Streaming protocols: Vagon Application Streaming (default; "30FPS streaming quality in any network condition", up
  to "4K, 60FPS" from the dashboard), Unreal Pixel Streaming, Unity Render Streaming. Transport: "WebRTC connection
  over a P2P network".

## 2. Creating a stream (dashboard, owner's account)

1. Upload the application `.zip` (main `.exe` in the root), pick the executable, a name and a logo.
2. Choose a **performance type** (section 6), then the cursor mode: **Mouse Control** (desktop apps) or **360 View
   Control** (pointer lock, first-person apps). For a browser: Mouse Control.
3. **Streams > New Stream**: pick the application, the regions (Europe: Dublin, Frankfurt, Stockholm; London, Paris,
   Milan "upon request"), the capacity method: **Cost Optimized** (`on_demand`: a machine starts when a visitor connects,
   "around 2 minutes" to connect), **Balanced** (N reserved idle machines kept running), **Availability Optimized**
   (`always_on`: all capacity running, "less than 10 seconds"). **Automated Setup** (pre-warmed pool, "a few seconds",
   charged "only for your active stream usage") is Enterprise only (a weekly trial can be requested).
4. Configure: resolution (`Scale to Screen Resolution`, `720p`, `1080p`, `4K`; the fixed ones keep 16:9), audio and
   microphone (ON / OFF / users can select), keyboard layout (English US/UK, Dutch, French AZERTY, German, Spanish,
   Turkish), connection page (dark/light; logo and messages are Enterprise), limits (section 6), availability schedule.
5. Copy the **Single Link** or the **iframe** code. The same can be done through the API (section 4).

The API alternative to the link: `POST /streams/{id}/assign-machine {region, user_id?}` returns a `connection_link`
for one machine (`connection_status: assigned`), `POST /streams/{id}/start-machine` pre-starts one, `POST
/streams/stop-machine {machine_id}` stops it.

## 3. Embedding and the web SDK

```html
<script src="https://app.vagon.io/vagonsdk.js"></script>
<iframe id="vagonFrame" src="__Stream_URL__" style="height:100vh;width:100vw"
        allow="autoplay; microphone *; camera *; fullscreen; clipboard-read *; clipboard-write *; encrypted-media *;"></iframe>
```
"If you can not establish a connection, please be sure that you copied the iFrame tag from the Vagon Streams
dashboard." Methods on `window.Vagon` (all plans): `isConnected()`, `startStream()` (what the play button does;
"Browsers block unmuted playback and microphone capture without a user gesture"), `focusIframe()` (the documented fix
for keyboard input problems), `resizeFrame()` (stream resolution follows the iframe size), `keepAlive()` (resets the
idle timer with a simulated input), `shutdown()` (ends the session and turns the machine off), `setQuality("standard"|
"moderate"|"high")`, `setVideoVolume(0..1)`, `showKeyboard()/hideKeyboard()`, `enableGameMode()/disableGameMode()`,
`sendApplicationMessage()`, `getSessionInformation()`. Events: `onConnected`, `onDisconnected`, `onApplicationMessage`
on every plan; `onInitialization`, `onInstalling`, `onFailed`, `onInactive`, `onPlayButtonClicked`,
`onSessionInformation` and the rest are **Enterprise only**.

URL parameters (Application Streaming only): `?launchFlags=<url-safe flags>` appended to the application's launch
flags for that session (stored in local storage and re-applied on a reconnect), `&newSession=true` to reset them.
`?visitor_email=` when visitor data collection is on. The stream link therefore may carry secrets: the runner never
logs its path or query (section 8).

## 4. API credentials and authentication

Per Stream, from the dashboard: **API Public Key**, **API Secret**, **Application ID** (the Stream must already exist
in the dashboard). Every call: `Authorization: HMAC {key}:{signature}:{nonce}:{timestamp}`, signature = hex
HMAC-SHA256(secret, `key + METHOD + path + timestamp_ms + nonce + body`), path without the host but with the
`/app-stream-management/v2` prefix (e.g. `/app-stream-management/v2/applications`), body `""` for GET. Endpoints:
`GET /applications`, `GET|POST|PUT|DELETE /streams`, `PUT /streams/{id}/activate|pause`, `GET
/streams/{id}/machines`, `start-machine`, `assign-machine`, `stop-machine`, `POST /users`, `GET /machines`, `GET
/sessions` (duration, region, ping, cost per machine). Machine `connection_status`: `waiting`, `available`, `assigned`,
`connected`, `terminated`, `proxy-in-migration`. Error codes: 4601 insufficient capacity, 4603 region not active,
4609 stream not active, 4610 start-machine needs Cost Optimized. `VagonPinger.getRegionPings()` picks the best region
client-side. The desktop runner does **not** call this API today; `vagon.json` only records where a key file would be.

## 5. How keyboard and mouse reach the remote machine

The stream page captures the browser's own DOM input events (mouse buttons, movement, wheel, keys; clipboard through
the iframe `allow` list; drag-and-drop file transfer when Stream Files is on) and sends them over the WebRTC data
channel; the remote machine applies them with the configured keyboard layout and cursor mode. The docs document no
other input path (no input API, no SDK method to inject a key). In our runner the kiosk Chromium *is* the visitor's
browser: Playwright dispatches real, trusted key and mouse events at page coordinates through CDP, the Vagon client
forwards them like a human's. `navigate`/`search` therefore mean "Ctrl+L, type the URL, Enter" in the remote browser.
Documented pitfalls: focus can be lost in an iframe embed (`focusIframe()`; the runner re-focuses the stream element
before every key); the play page needs a gesture (the runner clicks the button it finds by text).

Network from the visitor's side (pod): TCP/UDP 443, TCP/UDP 3478, UDP 49152-65535 to Vagon's per-region addresses.
The pod's egress for UDP is not verified.

## 6. Costs and limits as documented (2026-10-23)

Pay per minute of machine time ("Stream Server usage time will be charged in minutes", terms 2022); prepaid balance
possible; "effective prices considering performance usage and standard streaming quality", region and quality can
change them.

| Performance type | GPU | vCPU / RAM | $/min | ~$/hour |
|---|---|---|---|---|
| Starter | NVIDIA Tesla T4 16 GB | 4 / 16 GB | 0.025 | 1.50 |
| Pro | Tesla T4 16 GB | 8 / 32 GB | 0.035 | 2.10 |
| Starter - G2 | NVIDIA A10G 24 GB | 4 / 16 GB | 0.036 | 2.16 |
| Pro - G2 | A10G 24 GB | 8 / 32 GB | 0.046 | 2.76 |
| Starter - G3 | NVIDIA L4 24 GB | 4 / 16 GB | 0.036 | 2.16 |
| Pro - G3 | L4 24 GB | 8 / 32 GB | 0.047 | 2.82 |

Plus datacenter storage **$0.67/day per region** and application maintenance **$0.67/day** (pricing calculator). Plan
fees (Basic / Pro / Enterprise) are not published; the plan table: 25 / 50 / custom applications, 25 / 50 / 125 GB per
application, concurrent capacity per link **25 / 50 / custom per region**, custom stream URL and versioning from Pro,
white label, custom connection messages, port access, **budget limits** and SDK events on Enterprise. Example: a browser
streamed 8 h/day on Starter (T4) is 480 min x $0.025 = **$12/day** + $1.34 storage/maintenance, about $400/month; on
Starter - G2 about $17.3/day. Reserved machines (Balanced) and Availability Optimized capacity run, and bill, while idle;
whether the `waiting` minutes of a Cost Optimized machine are billed is not stated.

Limits: **Session Duration Limit** (owner-set; a warning 1 minute before, then the visitor is redirected), **Idle
Duration Limit** (session ends after the set time without user action), **Auto Turn-Off Duration** for machines (not on
Availability Optimized or Balanced reserves), **Stream/Application Budget Limit** (pauses the streams when reached;
Enterprise), availability schedule (outside it: "Stream is Expired" page), stream `paused` status (same page).
Resolution: scale-to-screen or 720p/1080p/4K; 30 FPS adaptive, 4K60 configurable; higher settings "may cause high
bandwidth usage". Latency is not quantified; "choose the closest regions" (EU: Dublin, Frankfurt, Stockholm). No
documented maximum session length or reconnect rate limit.

## 7. Usage rights

Vagon Streams terms (last updated 18.02.2022): the Service is reached "via Channels", defined to include the website,
APIs and SDKs; prohibited: illegal use, "disabling or circumventing features that prevent or limit access", reverse
engineering, malware, interfering with networks; "VAGON CAN PAUSE THE SERVICES ANYTIME IT WANTS"; charges per minute;
account needs an e-mail and password, users over 13. Nothing addresses a scripted visitor on one's own stream, bots or
automation either way. Before SUB-01 goes live on it the owner should ask Vagon (support@vagon.io) whether an automated
browser visitor on his own stream, re-entering after session limits, is acceptable, and whether `keepAlive()`-style
activity is meant to defeat the idle limit he himself sets (the runner does not call `keepAlive()`; it only re-enters).

## 8. What the owner has to provide (we never sign up or pay)

1. A Vagon account with Streams, an uploaded application that is a browser, and an active Stream.
2. The **Stream Link** (or the dashboard's iframe page), placed on the pod in `<streamer-dir>/vagon.json`, mode 0600,
   uid 1001: `{"schema":"sub01.streamer-vagon.v1","stream_url":"https://app.vagon.io/stream/...","api_key_file":
   "/home/unreal/.sub01-private/vagon-api-key"}` (`api_key_file` optional, unused today). The link is a credential:
   anyone with it connects and spends his minutes (restricting it needs Enterprise visitor authentication).
3. Stream settings that fit the runner: 1080p or scale-to-screen resolution, Mouse Control, English US keyboard, audio
   off (the pod has no audio device), a Session Duration / Idle limit and a budget he accepts, the per-visitor restart
   decision, and the region nearest the pod (EU-RO-1: Frankfurt or Stockholm).
4. Optionally the API key pair + application id for a later start/stop/cost integration (root-only file).

## 9. What we cannot know without an account

The connection page's DOM (button text, `video` vs `canvas`, element ids) and whether the single link renders the same
page as the dashboard's iframe; the exact text and controls of the "session ended" / "stream expired" pages; whether
our CDP-dispatched input counts as user action for the Idle Duration Limit; whether a visitor can see the Windows
desktop or only the executable's window; whether the per-visitor restart can be disabled on Basic; connect times in
Frankfurt for a given performance type; plan prices and the Team's current balance; whether Chromium's software WebRTC
decode (the runner runs with `--disable-gpu` on Xvfb) keeps 1080p30 smooth on the pod's CPU; whether UDP egress from
the pod reaches Vagon's relays. The runner's behaviours that depend on these (button labels, ended-state texts) are
text heuristics in `scripts/streamer_desktop.py` (`VAGON_CONNECT_RX`, `VAGON_ENDED_RX`) that may need one round of
tuning against the real page; `events.jsonl` records every press and phase change for that.

## 10. How the runner uses it

`scripts/streamer_desktop.py --pc-mode vagon` (docs/streamer/DESKTOP.md, "Vagon mode"): the kiosk Chromium opens the
stream link, presses the connect/play button it finds by text, waits for the stream element, tracks `connected`,
re-enters after a session end (press "Reconnect", else reopen the page with 15 s to 5 min backoff), maps the agent's
primitives onto the stream, and exposes `pc_mode` and `vagon{connected, phase, reconnects, last_reconnect_utc, ...}` in
`/pc/state`. The monitor texture, the director and the agent loop are unchanged; the agent receives `mode: "vagon"` and
`remote_ready` in `/desktop/observe` and no marks (clicks are by point).
