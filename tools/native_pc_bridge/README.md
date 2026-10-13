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
