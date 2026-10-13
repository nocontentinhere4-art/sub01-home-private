# Native live PC bridge

The existing real v86 Linux computer was verified through the existing local API: unauthorized command input returned HTTP 403; authenticated `printf 'SUB01_NATIVE_PC_BRIDGE_OK\n'; uname -s` returned the actual marker and Linux output. The local browser had no current desk frame and remains suspended. This evidence is in `out/native-pc-api-proof.json`; it does not prove a connected native Unreal monitor.

`Sub01PCBridge.h/.cpp` defines an independent Unreal actor component. It reads actual terminal output from `GET http://127.0.0.1:8798/pc/state`, draws that output into a transient 1024×600 canvas, and binds it to the exact monitor screen through a `PCFrame` material parameter. It sends typed commands to `POST /pc/input`. Authentication comes from the existing operator token in `SUB01_ADMIN_TOKEN`; there is no embedded token or newly generated access credential.

The Claude runner API contract is a flat `{privacy:boolean,ready:boolean,output:string,...}` state. POST `/pc/input` accepts `{input:string}`; POST `/pc/session` keeps a focused PC awake with a 30-second heartbeat; POST `/pc/privacy` mirrors native bathroom privacy. Browser JPEG support was removed from this helper so the actual Linux serial output has one clear source. No browser image is fabricated.

Integration:

1. Copy the two C++ files into the existing `Source/Sub01HomeLab` module; add HTTP, Json, JsonUtilities, RenderCore and RHI dependencies.
2. Run `create_pc_screen_material.py` inside the actual UE editor on Runpod. It creates only the unlit `M_Sub01LivePC` material; it does not apply it to any actor.
3. Instantiate/register the component in the actual native character and call `Configure(exactMonitorScreen,slot,material)`. The source monitor surface is 0.68×0.4 m at source coordinates `(2,1.16,-3.276)`. Root identified GLB node 75 / Mesh_58, material 18, with actual screen center UE `(200,-327.6,116)` cm and size `(68,0,40)` cm; confirm this component and slot 0. Do not replace every surface tagged Desk. A precisely placed noncolliding screen plane is appropriate if the exported monitor geometry is merged.
4. Desk interaction calls `SetOperatorFocus(true)`; enter/typed text call `SetTypedLine` and `SubmitTypedLine`; leaving PC calls `SetOperatorFocus(false)`. The native bathroom trigger must call `SetLocalPrivacy(true)` and clear it on exit. Input is refused while native or backend privacy is active.
5. Deploy the real private PC runtime on **Runpod**, bound only to 127.0.0.1:8798. The same-server HTTP bridge does not connect to the Mac's localhost. Root/Claude own this runtime; preserve its actual VM snapshot/state. Do not expose a public backend port or ship a token inside a material/asset/source file.

Privacy is checked before and after asynchronous state/command operations. Entering privacy clears cached pixels, terminal text and pending typed input, invalidates older requests, and blocks input. Unavailable backend shows an honest disconnected status. Credentials and terminal content are not written to UE logs.

The renderer successfully compiled these helpers with the native character and hands module in 78.18 seconds. Actual UE monitor rendering and browser typing are awaiting its viewport capture. Acceptance needs actual on-server PC command output visible in native viewport, an E/keyboard-triggered command, and privacy/input checks; static terminal art or an API-only test is insufficient.

## Actual Runpod runtime evidence

The selected PC runtime files, pinned VM assets and current `data/computer.bin` snapshot were transferred through the existing authenticated Jupyter file API. Claude's standalone runner runs on Runpod at **127.0.0.1:8798 only**, using the existing local test operator credential (not a newly generated key or a claim of strong random authentication). Its token file is owner-readable only and no token is embedded in native files or viewer assets. The guest has no host mounts or network.

On 2026-10-13, the actual restored guest accepted `printf 'SUB01_RUNPOD_PC_REAL\n'; uname -m; date` and returned the standalone marker, **i686**, and the guest's date output. Unauthorized state access returned **403**; bathroom privacy blanked output and refused input with **409**. Privacy was turned off and the session ended after testing. Evidence: `out/actual-runpod-pc-api-proof.json`.

The existing pod budget guard PID 12900 was verified alive, and the PC runner was bounded to the existing 18:16 UTC deadline. No Mac Chromium or Minecraft process was resumed. This is actual on-server PC API evidence; native monitor display and browser typing are awaiting the renderer's combined build.

The final Claude runner privacy race fix was applied on Runpod. A graceful stop saved the real guest; restart showed the saved-state restore banner, then returned a new actual command marker and i686. Privacy hid output and paused the guest, while session start during privacy returned 409. Native privacy synchronization is idempotent when called every Tick, serializes flag requests and retries failures at most once every two seconds. A scoped Slate input processor handles real printable ASCII key events, Shift punctuation, Backspace and Enter while focused; Escape releases focus. World movement and mouse look remain available outside PC focus.

## Actual joint runtime proof

The official FBX fallback imports the authentic owner mesh and captured clips, and the native viewport renders both hands with the live Linux monitor. A real same-server browser sent keyboard events through official Pixel Streaming, typed a fresh uppercase/underscore marker and `uname -m`, and the guest returned the exact standalone marker and i686. No direct API command was injected by the recording test. The first run exposed lost Shift modifiers; explicit modifier tracking fixes that and the final exact-match test passes.

Evidence is private and ignored: `out/house-evidence/native-hands-pc-browser-proof.json`, the actual incoming-stream recording, and the corrected viewport PNG. This is a controlled typing-pose diagnostic; it does not validate autonomous brain behavior, seating transitions, every physical hand contact, graphical desktop applications, or external authenticated viewing. Normal body validation gates remain disabled.


## Conditional actual VGA pixel support (not a graphical desktop claim)

`computer/vga_framebuffer.cjs` captures the actual emulator graphical VGA RGBA buffer through v86's existing headless adapter. It requires no browser, canvas, screenshot renderer or fake desktop. Serial mode remains a real serial terminal. The currently pinned Buildroot guest has not been verified to contain an installed graphical desktop or graphical applications.

The worker sends pixels only when a graphical buffer changes, with a session-specific frame identity. `Computer.view()` exposes truthful `display` metadata. The private runner adds authenticated `GET /pc/frame.png?revision=<frame_id>`, returns 404 when there is no graphical VGA frame, 409 during privacy or revision mismatch, and a revision ETag for unchanged frames. Privacy takes precedence over an ETag match.

The native component fetches an available graphical PNG, then rereads authenticated PC state before decoding/applying it. It refuses stale generations/revisions and clears the texture upon privacy. In graphical mode the focused native input processor sends bounded real PS/2 key taps, modifier combinations, relative mouse motion and mouse buttons to authenticated `/pc/graphical-input`; serial mode preserves actual serial-console commands. Escape releases native PC focus. The optional graphical-input path is source-tested and still needs native compile/runtime acceptance. This does not claim a desktop installation. Native compilation and actual graphical guest frame acceptance remain pending.

Deploy the additional `computer/vga_framebuffer.cjs` beside the existing worker. Python worker output buffering is bounded at 8 MB; generated images are bounded at 1280×1024 and HTTP frame bodies at 6 MB. No credentials or screen contents are logged.

Phone and TV have separate actual home APIs: phone browser pixels at `/api/screen/phone.jpg?frame_id=...`, home state at `/api/home`, and configured Minecraft frames at `/api/home/minecraft/frame.jpg`. The standalone PC runner at 8798 does not implement those endpoints. A real full-home backend must be connected before those native devices can claim functionality; a serial runner or static page is not a substitute.


Optional graphical guest boot: `scripts/home_pc_runner.py --guest-cdrom /private/path/owned-guest.iso ...` boots that actual CD-ROM with 128 MB guest RAM and a separate `computer-graphical.bin` snapshot. The existing Buildroot `computer.bin` is preserved. The official v86 repository currently documents `https://i.copy.sh/TinyCore-11.0.iso` as a supported test image; that is a candidate for a real lightweight X desktop, not evidence that it has been downloaded, booted or accepted here. Never run the guest on the overheating Mac for acceptance; use the authorized private server.

## Private graphical guest and shared backend, 2026-10-13

The replacement private Runpod runs the authoritative guest on loopback **8811** with the existing operator credential loaded from `/home/unreal/.sub01-private/operator-token`. Set `SUB01_PC_ORIGIN=http://127.0.0.1:8811` for the native components. The old Buildroot snapshot is preserved; the GUI candidate uses separate `pc-vga-state-fresh/computer-graphical.bin`. TinyCore 11's real Xvesa desktop and real aterm were inspected as actual VGA pixels. Physical PS/2 keyboard events executed `uname -a` in that terminal and the resulting Linux output appeared in the real PNG. This is guest output, not a home-rendered imitation of a desktop.

`computer/guest_keyboard.cjs` preserves key ordering and a 20 ms interval, cancels pending key input on privacy and releases held keys. `computer/vga_framebuffer.cjs` copies the guest's actual RGBA buffers to a bounded PNG. `/pc/frame.png?revision=<frame_id>` requires operator authentication, checks the exact frame identity and refuses privacy with 409. Actual runtime checks returned 403 for unauthenticated state and 409 for private pixels and keyboard input. Native and full-home privacy are separate OR-combined sources; clearing one cannot clear the other.

To share this guest with the full backend without starting another VM, set `HOME_COMPUTER_ORIGIN=http://127.0.0.1:8811` and `HOME_COMPUTER_TOKEN_FILE=/home/unreal/.sub01-private/operator-token` **only on the full backend**. `home_remote_computer.py` retrieves real state and pixels, rechecks privacy and frame identity after fetching, and clears all cached data when unavailable. It does not claim that serial commands sent to an unused GUI UART are real graphical terminal actions. Agent GUI command generation remains gated pending focus and action validation.

`--home-origin http://127.0.0.1:8820` connects the standalone runner's authenticated `/devices/*` proxy to the actual same-server home backend. The separate native device component displays real phone/Minecraft JPEGs when those services exist, and draws Pong from actual server game state with actual server paddle actions. Missing services stay unavailable. Native Chess rendering has not been implemented. Four C++ files must be staged, and the native interaction handler must call `TryNativeHomeDevice` before desk focus. Native phone/TV runtime acceptance still requires a real viewport and input test.

Graphical mouse control remains **unaccepted**: real PS/2 movement bytes were observed inside the Linux kernel, but the Xvesa cursor did not move in the inspected frames. No substitute mouse result or fabricated browser page was introduced. The authorized server hard stop remains 21:45 UTC, with guest save termination armed at 21:44:47 UTC.

Private guest input checkpoint (2026-10-13): the GUI keyboard executed `uname -a`
in the actual TinyCore terminal. Mouse interaction remains **unaccepted**. The
recorded guest `/dev/input/mice` bytes `28 14 f6` correspond to dx=20, dy=-10;
the instruction counter advanced 796,839 while an active operator session sent
movement/clicks, but the VGA frame and window state did not change. Xvesa had
`/dev/input/mice` open as root, and its `,5` argument means five buttons according
to its own help, not a five-byte packet format.

The source correction in `computer/guest_mouse.cjs` matches the bundled v86
browser adapter: always send `mouse-delta` (screen dx, negated screen dy), and
add `mouse-absolute` when unlocked absolute mode is advertised. Previously the
absolute branch omitted relative events, which could starve the PS/2 device
used by Xvesa. Button order remains left/middle/right. This is a bus-contract
correction, **not a verified fix for X window input**. No guest was restarted or
runtime acceptance changed during this CPU-only review.

At the next authorized runtime, record advertised absolute mode and X's open
input descriptor, keep an authenticated native focus lease alive, capture the
actual frame and instruction counter before/after movement and a held click
on the terminal/titlebar, and require an actual window/focus change. If absent,
capture Xvesa stderr and the guest input protocol rather than flipping movement
signs or replacing the display. Operator/native and home/actor session leases
now expire independently; actor release cannot cancel native focus. Privacy
clears both leases and requires a fresh focus request after exit.

Native module staging now requires **both** additional headers
`Sub01GuestInputQueue.h` and `Sub01GuestFrameLayout.h` beside `Sub01PCBridge.cpp/.h`.
The CPU queue test covers ordered press/drag/release, dropping unsent input on
focus loss while releasing buttons after the active request, and ignoring stale
completion after privacy cancellation. The frame test preserves every source
BGRA pixel and verifies opaque padding and bounded dimensions. The bridge derives
aspect from the actual authored monitor X/Z extents (34/20), so a 1024×768 guest
is padded to 1306×768 instead of stretched. No guest pixels are invented in the
padding. These checks do not confirm native compile or live interaction.

A later live check on the restored guest accepted **relative mouse movement and
left click/drag**. A two-second stationary control kept the identical VGA frame;
+40/-40 screen-Y movements changed the actual cursor/menu images. Selecting the
real Terminal task closed the desktop menu. A held left button with dx=20, dy=20
then moved the actual terminal window from (0,0) to (40,40), with VGA frame 19→21.
The evidence is private `out/native-device-vga/mouse-window-before.png`,
`mouse-window-after.png`, `mouse-window-proof.json` and the `mouse-control-*`
frames/proof. The earlier large-delta clamp probe is not a verified stress test.
The current guest protocol is PS/2 Explorer ID4, streaming active, controller
register 0x43; VMware/absolute mode is disabled. No mouse-sign or X configuration
changes were needed for the successful real interaction.
