# SUB-01's PC: runbook

The computer at the desk is a real x86 Linux guest (Buildroot, BusyBox) running inside v86/WebAssembly in a Node.js
worker that the live server owns (`home_computer.py` + `computer/worker.cjs`). It has no host mounts and no network.
SUB-01 types bounded commands on its serial console while his activity is `use_computer`; viewers see the terminal on
the 3D monitor and in the computer panel; the operator can type too. Everything here runs on loopback.

Three ways the desk PC can be backed, in the order the server picks them:

| Mode | When | What the house shows |
|---|---|---|
| Local guest (default) | `HOME_ENABLED=1`, no `HOME_COMPUTER_ORIGIN` | the Linux serial terminal |
| Remote guest | `HOME_COMPUTER_ORIGIN=http://127.0.0.1:8810` (+ token file) | the same terminal, from `scripts/home_pc_runner.py` |
| Vagon cloud PC | `VAGON_API_KEY` etc. (agent H11, `vagon_pc.py`) | only a reaction in chat for now: no screen source yet |

The browser (`BROWSE=1`, headless Chromium through Playwright) is a separate thing: it fills the same monitor during
`research` / `watch_video`, not during `use_computer`. The PC works with `BROWSE=0`.

## 1. What must be there

- Python env with `requirements-server.txt` installed.
- Node.js on `PATH` (the worker is plain Node; 18+ is fine). Without it the view says `Node.js is not installed`.
- The pinned guest files. `computer/libv86.cjs` and `computer/v86.wasm` are in git; the three `.bin` files are not
  (`computer/*.bin` is gitignored). They come from the official v86 distribution, size- and SHA-256-checked against
  `computer/manifest.json`:

  | File | Bytes | Source |
  |---|---|---|
  | `seabios.bin` | 131,072 | https://copy.sh/v86/bios/seabios.bin |
  | `vgabios.bin` | 36,352 | https://copy.sh/v86/bios/vgabios.bin |
  | `buildroot-bzimage.bin` | 5,166,352 | https://i.copy.sh/buildroot-bzimage.bin |

  about 5.3 MB in all. Nothing else is downloaded, ever.

```sh
python computer/bootstrap.py --status     # says what is installed; exit 1 when incomplete, downloads nothing
python computer/bootstrap.py              # verifies / downloads the three files into computer/ (once)
```

If `bootstrap.py` never ran, the server tries by itself on start into `<data-dir>/computer-assets/` and, failing that
(no network), reports it and retries with a 30 s → 5 min backoff. You do not have to restart the server after running
bootstrap: the next retry finds the files.

## 2. Run it

Without the browser (lightest; the PC is fully functional):

```sh
HOME_ENABLED=1 HOME_ENTRYPOINT=1 BROWSE=0 MIND=0 CLIPS=0 SUB01_SPIKING_LIVE=0 \
SUB01_ADMIN_TOKEN=house-local-test OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python live_server.py --host 127.0.0.1 --port 8798 --data-dir /tmp/sub01-home
```

With the browser (the monitor shows real pages when he reads; needs Playwright's Chromium):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/start_home_local.py --port 8798 --data-dir /tmp/sub01-home
# or, on the Mac where Chromium runs as its own process: ./scripts/start-private-browser.command, then
# python scripts/start_home_local.py --browser-service http://127.0.0.1:8799
```

`start_home_local.py` sets `HOME_ENABLED=1 BROWSE=1 MIND=0 CLIPS=0` and the local token `house-local-test`. Keep the
data dir outside the repository. Open `http://127.0.0.1:8798/house`; the **Computer** button (or `E` at the desk) opens
the panel; its **Linux** tab is the terminal, **Browser** the Chromium screen.

Expected log lines (`home computer:` prefix) on a healthy start:

```
home computer: guest worker started (pid 12345, bundled assets, state new at /tmp/sub01-home/computer.bin)
home computer: Linux guest ready after 6 s (bundled assets); it pauses while he is away from the desk
```

Then, while he is not at the desk, the VM pauses (status `ready`, `paused: true`). Snapshots go to
`<data-dir>/computer.bin` once a minute and at shutdown; the next start logs `Linux restored from its saved state`.

## 3. Check it

```sh
curl -s http://127.0.0.1:8798/api/home | python -c "import json,sys; c=json.load(sys.stdin)['computer']; \
print(c['status'], '|', c['summary'], '|', c['hint'])"
```

| `status` | `summary` | Meaning / fix |
|---|---|---|
| `starting`, `preparing` | Starting… / Checking the pinned Linux guest files… | first seconds |
| `booting` | Linux is booting… | the worker is up, no shell prompt yet (logged if over 120 s) |
| `ready` | Buildroot Linux / x86 · running / paused while he is away from the desk | working |
| `unavailable` | Linux guest not installed: N of 3 pinned files missing (…); Could not download … | run `python computer/bootstrap.py`; the server retries by itself |
| `unavailable` | Node.js is not installed | install Node.js, restart |
| `offline` | Linux guest worker exited with code N; stderr: … | the worker died; its last stderr lines are in the log; it restarts by itself (30 s → 5 min) |
| `private` | Bathroom privacy is active | nothing is shown while he is in the bathroom (server-enforced) |

`/api/home` also carries `computer.guest` (`assets`: bundled/cache, `worker`: starting/running/exited, `restarts`,
`exit_code`) and `browser` (`state`: up/down/off/idle/waiting with `why`, e.g. `the browser is turned off (BROWSE=0)`).
The monitor and the panel print these same lines, so a black monitor is never the way you find out.

Operator command (needs the token; the panel's "Operator key" field stores it for the tab):

```sh
curl -s -X POST -H 'X-Admin-Token: house-local-test' -H 'Content-Type: application/json' \
  -d '{"input":"uname -a"}' http://127.0.0.1:8798/api/home/computer
# {"ok": true}   or   {"ok": false, "status": "...", "error": "...", "hint": "..."}
```

## 4. Make him use it

- Chat impulse (phone panel → Messages, or any WS client): a message containing `pc`, `computer` or `laptop`
  (`impulse.py`) → `life.request_impulse` → his next tick starts `use_computer` (he walks to the desk if needed, sits, the
  VM resumes and he types a command within ~1 s of being seated, then one every 18 s). The chat ack carries the reaction
  "Sure, heading to the computer." and the house shows it as a notice.
- Operator nudge: `POST /api/home/intent {"activity":"use_computer"}` (a vote-strength nudge, not a command).
- The monitor switches to the terminal the moment `home.activity` becomes `use_computer`, even before he sits; the panel
  refreshes on every revision of the computer view (WebSocket `devices.computer`), so a new line shows within a second.

## 5. What the screens look like

| Situation | Monitor | Panel › Linux |
|---|---|---|
| guest ready, he is at the desk | `SUB-01 / LINUX` + the last 29 serial lines | the serial output, `[ready] Buildroot Linux / x86 · running` |
| guest ready, he is elsewhere | the browser page (BROWSE=1) or "His browser is off: the browser is turned off (BROWSE=0)." | the last output, `[ready] … paused while he is away from the desk` |
| guest not installed | `SUB-01 / LINUX`, the "not installed" line, the bootstrap command, `[unavailable]` | `Connecting to his Linux computer…`, `[unavailable] Linux guest not installed…`, the hint |
| worker died | the exit line and `guest worker restarts: N` | the same, `[offline]` |
| bathroom | the privacy screen (no pixels, no text) | closed |

## 6. The headless runner and the remote mode

`scripts/home_pc_runner.py` runs the same `Computer` without the brain (see `docs/home-pc-runner.md`). The house can use it
instead of its own worker:

```sh
HOME_COMPUTER_ORIGIN=http://127.0.0.1:8810 HOME_COMPUTER_TOKEN_FILE=/abs/path/operator-token python live_server.py ...
```

When the runner is down the view says `Actual private guest is unavailable` with the hint naming the origin; the
transition is logged once each way (`home computer (remote): … is unavailable` / `… answers`).

## 7. Verified on 2026-10-23 (cloud container, loopback, `BROWSE=0`, no GPU)

`live_server.py --host 127.0.0.1 --port 8947` with the command from section 2 and an empty data dir:

- `/healthz` answered 2 s after import. The server fetched the three guest files itself into
  `<data-dir>/computer-assets/` (5,333,776 bytes) and logged `guest worker started (pid …, cache assets, state new at …)`.
- `/api/home.computer` went `booting` → `ready` (`Linux is booting…` → `Buildroot Linux / x86 · running`); the log read
  `Linux guest ready after 33 s (cache assets)` for this first boot without a snapshot (a restored snapshot is faster).
- Chat over `/ws`: `{"type":"chat","text":"use the pc please"}` → ack `{"ok": true, "reaction": "Sure, heading to the
  computer.", "impulse": "activity"}`; the next home message on the same socket (0.1 s later) already had
  `activity: use_computer` and a new `devices.computer` revision; `life.say` read `asked in chat: use_computer`.
- He walked from the balcony to the desk, `seated: 1`, `activity_ready: true`, and typed `cat /proc/uptime`, `ls /`,
  `date` at 18 s intervals; `output` ended with `~% date\r\nFri Oct 23 01:58:43 UTC 2026\r\n~% ` (real guest output).
- `POST /api/home/computer` while booting answered `{"ok": false, "status": "booting", "error": "Linux is booting…"}`;
  without the token, 403.
- `/house/computer_screen.mjs` was served as `text/javascript`.
- `SIGTERM` stopped the server; the worker was asked to save and exited; `<data-dir>/computer.bin` was written.

Not verified here: the 3D page in a browser (no display), `BROWSE=1` (the venv's Playwright wants a newer Chromium
than `/opt/pw-browsers` holds), the remote runner mode against a live runner, the Vagon PC (no credentials).

## 8. Tests

```sh
BROWSE=0 python -m pytest -q tests/test_home_computer_failure.py       # run() retries, stderr, view, bootstrap, the route
BROWSE=0 python -m pytest -q tests/test_home_remote_computer.py
BROWSE=0 python -m pytest -q tests/test_home_pc_runner.py
node tests/js/computer_screen_check.mjs                                 # monitor/panel text without and with guest output
node tests/js/computer_snapshot_check.cjs                               # worker snapshots
```
