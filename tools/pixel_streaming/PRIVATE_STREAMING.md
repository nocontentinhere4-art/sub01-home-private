# Private Unreal Pixel Streaming

Prepared for the already authorized Runpod `713u6mnmxu4y1a`, UE 5.8.3, and `/Game/Sub01Home/ActualHome`. No other pod is authorized. The absolute runtime deadline is **2026-10-13 18:16 UTC**. The existing pod budget guard remains authoritative; this adapter also exits at that deadline.

`private_signaller.cjs` uses Epic's official `@epicgames-ps/lib-pixelstreamingsignalling-ue5.8` implementation. It binds player HTTP/WebSocket to `127.0.0.1:8890` and streamer WebSocket to `127.0.0.1:8891`, limits the home to one viewer, and disables SFU. It does not start the engine or a relay. It contains no token or credential.

## Required gateway

Install `jupyter-server-proxy` into the Runpod Jupyter Python environment, enable its server extension, and activate it during a coordinated Jupyter restart. The existing Jupyter authentication then protects `/proxy/8890/`. Do not expose ports 8890 or 8891 through Runpod. Do not distribute token-bearing URLs or write Jupyter tokens into viewer files. The browser must first sign in to the existing Jupyter session.

Use Epic's UE5.8 infrastructure source from `https://github.com/EpicGamesExt/PixelStreamingInfrastructure/tree/UE5.8`. Build its official frontend and signalling library **on Runpod**. Inspect and use its setup/build steps only: the stock `start.sh` also launches STUN/TURN and public listeners, and is not appropriate for this private setup.

Run the adapter with the official infrastructure directory as its sole argument, for example:

```
node /workspace/sub01-home-private/streaming/private_signaller.cjs /workspace/sub01-home-private/streaming/PixelStreamingInfrastructure
```

The adapter sets the official frontend’s `ss` URL query setting before its bundle executes, using a same-origin WebSocket URL at `wss://[existing Jupyter host]/proxy/8890/`, preserving the proxy prefix. Verify the actual connection in the browser before claiming success.

Coordinate the native engine launch with other engine jobs. The intended launch arguments are `-game /Game/Sub01Home/ActualHome -RenderOffscreen -ResX=1280 -ResY=720 -ForceRes -PixelStreamingURL=ws://127.0.0.1:8891 -PixelStreamingID=Sub01HomePrivate -AudioMixer -Unattended`, with the PixelStreaming2 plugin enabled. Run as `unreal`, under the existing budget deadline. Do not launch another engine concurrently with native asset imports/captures.

## Media transport constraint

Authenticated Jupyter HTTPS/WebSocket proxying carries viewer files and signalling, **not WebRTC media**. Real video/audio and keyboard/mouse data channels need reachable ICE transport. The current rule permits no new unauthenticated public ports. A separately authorized authenticated TURN relay or private network is therefore required; do not open pod UDP/TCP media ports as a workaround.

An optional owner-readable-only JSON peer options file can be passed using `SUB01_PRIVATE_PEER_OPTIONS_FILE`. It must contain an authorized authenticated relay configuration; never commit it or print it. The adapter does not generate credentials, provision relay services, or assume permission for them.

## Completion evidence

A working browser session needs all of the following: protected viewer loads; official streamer handshake identifies `Sub01HomePrivate`; browser ICE connects; video frames display the actual UE map; WASD/mouse moves the native character; E changes an actual device; hand interaction is visible. Signalling alone, a PNG capture, or a simulated home does not prove this.

At inspection time, UE’s PixelStreaming and PixelStreaming2 plugins were present. Epic’s official UE5.8 source revision `7202a04cdce557f6ecc3a2913b1a296b6b88a2d4` was fetched on the designated pod and its official build completed with its prescribed Node 22.14.0, unpacked locally on Runpod. The adapter was uploaded and a bounded loopback protocol test passed: the official library sent streamer configuration, and the official player endpoint listed the synthetic probe streamer. Both listeners were verified bound to 127.0.0.1 and stopped after the test. This is signalling evidence only; an actual UE streamer has not connected. `jupyter-server-proxy` 4.6.0 was installed and validated as enabled, but the existing Jupyter process has not been restarted to activate it. The actual project does not yet enable PixelStreaming2. No live stream or browser input validation has occurred.

## Bounded public relay investigation (not a shipped default)

The coordinator authorized a single short transport test using Metered's documented public static-auth route, with protocol session tokens expiring within 30 minutes and fictional-house media only. No account, subscription, payment, persistent access credential, or public viewer was permitted.

Primary documentation:

- [Metered OpenRelay](https://www.metered.ca/tools/openrelay/) documents `staticauth.openrelay.metered.ca:80` and `:443`, its published static-auth secret, and peer DTLS/SRTP encryption.
- [Official coturn REST-auth documentation](https://github.com/coturn/coturn/blob/master/README.turnserver) defines expiry timestamps and `base64(HMAC-SHA1(shared-secret, temporary-username))`.
- [OpenRelay terms](https://www.metered.ca/tools/openrelay/terms-and-conditions/) explicitly provide no availability warranty or guarantee.
- [Metered Trust Center](https://www.metered.ca/trust-center) states that relay media is not inspected, stored, or recorded; endpoint IP metadata is retained for 30 days.

The general OpenRelay page advertises 20 GB/month. It does not specify a separate public-static pool quota, throughput allowance, or SLA. A 60-second 4 Mbps viewport test would send about 30 MB of media payload before protocol overhead; that is a planning estimate, not a measured usage result.

`test_public_static_turn.py` performs one short authenticated allocation and immediate release, sends no media, writes a private test-only peer-options file only on successful allocation, and never prints protocol tokens. It permits only the two vendor-documented ports, with eight-second network timeouts and a 20-minute protocol token expiry.

**Actual result:** TCP 443 timed out; fallback TCP 80 also timed out before TCP connection. No allocation, token file, media transmission, decoded frame, or input verification resulted. Do not configure this public route as a default or describe it as working. The ordinary current Metered account/API-key path and legacy undocumented shared username/password were not used.

## Actual native loopback browser proof — 2026-10-13 16:49 UTC

A bounded native Unreal run on the designated Runpod enabled PixelStreaming2 using `-EnablePlugins=PixelStreaming2`, opened the actual `/Game/Sub01Home/ActualHome` map in game mode, and connected the real streamer `Sub01HomePrivate` to the official loopback signaller. Engine settings confirmed H.264 Baseline; the NVENC module loaded. Browser video decoding, rather than module loading alone, supplies the useful encoder proof below.

A headless Chromium browser was installed and run **only on Runpod**, with browser GPU processing disabled. It loaded the official private loopback viewer. ICE and the peer connection reached `connected`; the official data channel reached `open`. The browser decoded the actual home viewport at **1280×720**: decoded frames increased from **2 to 147**, while video bytes received increased from **335,522 to 11,249,567**. Input-channel messages sent increased from **16 to 98** after keyboard/mouse events. Before/after screenshots show the actual office/stairs and a resulting native camera look change.

Evidence downloaded locally through the existing authenticated Jupyter file API:

- `out/local-proof.json`
- `out/local-proof-before.png`
- `out/local-proof-after.png`

`local_browser_proof.cjs` reproduces this server-local test. The browser closed, the bounded native engine exited, and the owned signaller was stopped after testing. The pod budget guard and absolute stop remained in place. No Jupyter restart or new public port was used.

**Scope limits:** this confirms real UE video encoding/decoding and browser input delivery with observable native mouse-look response on the same server. Native WASD displacement and E device state changes were not isolated/verified. The authenticated Jupyter viewer route was not exercised; external-browser ICE/media remains blocked by the failed public relay transport. Do not present the local proof as a working remote private browser session or as complete device/hands verification.


## Actual hands and native guest keyboard proof — 2026-10-13 17:59 UTC

A bounded run of the final compiled actual home streamed through the official loopback viewer. The viewer sent ordinary keyboard events: E focused the authored desk monitor, a fresh `echo SUB01_NATIVE_KEYBOARD_REAL_1791914277348; uname -m` command was typed, and Enter submitted it through the native Unreal HTTP bridge into the real restored v86 Linux guest. The authenticated state poll observed the **exact fresh marker as a standalone output line** and `i686`. No direct API command injection was used by this recorder. A frame decoded from the final recorded video visibly shows the same new output on the authored monitor.

The native input preprocessor now tracks both Shift keys itself because consuming modifier events occurs before Slate updates its default modifier state. Exact uppercase letters, underscores, semicolon, and hyphen were exercised in the successful command. A previous attempt before that fix produced lowercase/hyphens and failed the strict criterion; it is not the accepted final evidence.

The browser recorded the actual incoming native MediaStream, rather than compositing screenshots. Decoded video frames rose **593 to 1768** during **17.829 seconds**; the input channel was open with **237 messages sent**. The measured interval corresponds to about 65.9 decoded frames per second; this is one local proof interval, not a remote-performance guarantee. The genuine imported source skeletal typing clip was running as a private pose diagnostic; this does not establish autonomous brain-driven hand use or final animation/contact acceptance.

Evidence in `out/house-evidence/`:

- `native-hands-pc-browser-proof.json` — strict marker, RTC counters, scope.
- `native-hands-pc-actual.webm` — original incoming viewport recording, 11,329,758 bytes.
- `native-hands-pc-actual.mp4` — H.264 1280×720, 16.556 seconds, 17,911,934 bytes; encoded only on Runpod using two CPU threads and preserved variable frame timestamps.
- `native-hands-pc-final-frame.png` — real decoded frame from that video showing fresh guest output and source hands.
- `native-hands-pc-before.png`, `native-hands-pc-typing.png`, `native-hands-pc-after.png` — real browser stills; the immediate after-state still precedes the next native monitor poll, so use the final decoded video frame for visible completion evidence.

The owned native engine exited, GPU was released, and budget guard PID12900 remained alive. The 18:16 UTC absolute stop was unchanged. The private Jupyter file API delivered artifacts without a new public endpoint. This validates actual server-local browser media, native keyboard delivery, real guest execution, and monitor display. It **does not validate an external authenticated browser media session**; the Jupyter viewer route and external ICE remain unproven.
