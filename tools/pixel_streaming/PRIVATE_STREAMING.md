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


## Private compute recovery — 2026-10-13 20:12 UTC

The owner explicitly raised the **total** home-work allowance to $20 and approved necessary replacement private compute, with every authorized home runtime stopped by **21:45 UTC / 23:45 Rome** (epoch1791927900). The earlier $10/19:16 limits above describe historical runs only.

The old home pod713u6mnmxu4y1a had no free GPU and only2GB host memory available. Generic `podResume` with gpuCount0 did not invoke its minimal recovery path. The first-party Runpod console uses the distinct `podResumeZeroGpu` operation; the same existing authorized account key successfully invoked it. That opened the existing volume without a GPU at the provider-reported $0.295/hour. It did not create a new CPU pod, migrate the original volume, or alter the brain pod.

A single private replacement A40 pod80lf8giw6ft61v, named `sub01-home-private-recovery`, was created at the verified $0.59/hour. Before workload startup, its identity-checked authenticated guard was installed with the exact stop epoch and total cap20. Existing Jupyter and home-only operator credentials were reused privately; no account/key permission expansion or public application port was added. Conservative provisioning estimate13.80 included a full10 allowance for prior home work, both home runtimes through the deadline, and2 reserve. This is a conservative planning bound, not an actual billing statement.

The existing licensed engine archive and selected authored project/PC/service files transferred **directly server-to-server** through existing authenticated Jupyter file access. No engine bytes were downloaded to or processed on the Mac. The source volume, real VM snapshot, and original pod were preserved; the temporary source CPU runtime was stopped after verification.

Full source/target SHA256 and every128MiB block matched:

- Engine ZIP39,818,576,005 bytes: `81985a9542e15761fa3cc0d4483a26ebe5fd0b448120faddaa2fe05d94142934`.
- Actual project TAR392,120,320 bytes: `6282a23544958fdce3c5111c730708bab36d3b0ea57f71e6a99e16c7f2e4cbe6`.
- Home services TAR769,259,520 bytes: `d4b5670df1c0650ef08a342172afbeb24f47c8ed2ff01df5910cd15fa2e8e06c`.

A parallel extraction sharing one ZIP reader initially failed. After switching each worker to an independent reader, all **300,132 entries /76,966,193,342 uncompressed bytes** extracted with per-entry CRC verification. No transfer block repair or engine redownload was necessary. The transfer helper now also validates exact Content-Range/Content-Length and uses identity encoding plus cache-busted, no-store requests.

The actual project was extracted as its exact nonroot owner UID/GID1001 because this volume restricts root chown. Content permissions and source skin/animation assets were preserved. Vulkan run as that user validated NVIDIA A40/Vulkan1.4.312 after restoring libEGL and standard runtime tools. Engine/project paths remain unchanged. GuardPID73 was verified active for21:45/$20 before the renderer received its GPU lease. Actual new graphical PC8811 readiness/input/frame acceptance belongs to its separate device owner; baseline8798 snapshot remains preserved without a duplicate VM launch.

Recovery helper code is in `tools/private_home_recovery_guard.py`, `private_home_transfer.py`, `private_home_asset_integrity.py`, and `private_home_engine_extract.py`. The terminal client allows only the two exact authorized home pod URLs. These recovery checks establish preserved assets and ready private compute; they do not themselves establish a new native video, working remote viewer, or autonomous brain behavior.


The replacement volume does not enforce Unix mode bits reliably. API control credentials were moved to rootfs `/root/.sub01-home-private/control.json` (root 0600), and the native computer operator credential to rootfs `/home/unreal/.sub01-private/operator-token` (UID1001 0600), each inside 0700 directories; old volume copies and transfer-session credentials were removed. Two authorized CI users are confined by rootfs `/usr/local/bin/sub01-ci-landlock`, with kernel Landlock ABI4, read-only system libraries, their own writable home/tmp/toolcache, and TCP connect ports80/443 only. Actual tests for both UIDs denied volume files, both credential files, and private service ports8811/8798/8820/8888/8890, while allowing GitHub443 and their own home writes. This wrapper must precede both runner configuration and execution. The live deadline guard was left running. The provider startup embeds the historical guard payload and must be refreshed at the next safe cold restart; changing that job during an active GPU capture would reset the container.


After both authorized pods were confirmed EXITED at21:45:25UTC and CI registrations zero, the owner authorized one additional hour on the same replacement only. Startup was updated while stopped to a rootfs-owned guard before resume; live guardPID77 authenticated pod80lf8giw6ft61v and verified deadline22:57:36UTC (epoch1791932256), totalcap20. Conservative cumulative allowance15.54 includes all prior work and a2USD reserve. Originalpod713 remained stopped. Rootfs accountUID1001 and protected same-role operator token were restored; both CI UIDs passed actual secret/volume/private-port denial and ephemeral listener rebinding checks under the restored rootfs Landlock helper. No third pod was created.
