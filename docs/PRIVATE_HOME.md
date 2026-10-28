# Private local home

This repository is private. Run the home on loopback only. Do not deploy this
repository, connect it to Railway, or modify the public SUB-01 service.

## Run locally

Requirements:

- Python 3.12. CI and the Docker image use 3.12; 3.13 also works locally. Create
  the environment with `python3.12 -m venv .venv`, activate it, and run
  `pip install -r requirements-server.txt`.
- The official Playwright Chromium for the screens: `python -m playwright install
  chromium`. The browser launcher below uses the existing environment and cache
  when available.
- Node.js on the PATH. The home's Linux computer needs it; without it the
  computer reports "Node.js is not installed".

Start the isolated browser first (macOS, leave it running):

```sh
./scripts/start-private-browser.command        # 127.0.0.1:8799
```

In another terminal, from this repository:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/start_home_local.py \
  --browser-service http://127.0.0.1:8799     # 127.0.0.1:8798
```

Open `http://127.0.0.1:8798/house`. The launcher sets `HOME_ENABLED=1`,
`HOME_ENTRYPOINT=1` and `BROWSE=1`; it blanks the paid keys and turns off the
mind, clips, the trade feed and cloud pod startup. Both services bind only to
loopback. The browser uses an isolated profile, not the operator's personal
Chrome profile. Its fixed operator token is for local development only and must
never be used for a public deployment. Without `--browser-service` the home
starts its own Chromium child process, if Playwright is installed. The CPU spiking process runs with
500,000 neurons by default: `--neurons` changes the count and `--no-spiking`
skips it.

### Without a browser (BROWSE=0)

Use this when Chromium is not installed or the screens are not needed. There is
no screen image: `/api/screen/desk.jpg` and `/api/screen/phone.jpg` answer 404,
and `GET /api/screens` gives the reason. This direct run does not blank API keys
as the launcher does, so do not export them in this shell.

```sh
HOME_ENABLED=1 BROWSE=0 MIND=0 CLIPS=0 SUB01_SPIKING_LIVE=0 \
  python live_server.py --demo --data-dir data/house-no-browser
```

Open `http://127.0.0.1:8765/` for the house, or `/room-classic` for the classic
room. Without `HOME_ENABLED=1`, `/` is the classic room.

### Ports

| Port | Process | Bind |
|---|---|---|
| 8798 | the private home (`scripts/start_home_local.py`, `--port`) | 127.0.0.1 |
| 8799 | isolated browser service (`scripts/start-private-browser.command`) | 127.0.0.1 |
| 8765 | `live_server.py` run directly (`PORT` changes it) | `HOST`, default 127.0.0.1 |

## Troubleshooting

**Black monitor**

- `http://127.0.0.1:8798/api/screens` says whether the browser is up and why not.
  Common reasons: `the browser is turned off (BROWSE=0)`, which means start
  through the launcher or set `BROWSE=1` (`live_server.py:2302`); and
  `playwright is not installed`, which means run `python -m playwright install
  chromium` in the environment that starts the server (`live_server.py:2312`).
- With `--browser-service`, start `scripts/start-private-browser.command` first;
  the browser service must answer on 8799.
- The script keeps the browser under `/private/tmp/sub01-house-chromium`. If that
  folder was cleared, reinstall Chromium with the command above.
- Bathroom privacy is on: the screen images answer 409 on purpose
  (`live_server.py:2325-2349`; the privacy gate is also in `home_api.py:53-56`).
- The computer shows "Node.js is not installed" (`home_computer.py:191-193`):
  install Node.js and restart.

**404 on assets**

- `/house/assets/bath-fixtures-original/`, `bath-light-original/` or
  `bath-door-original/`: the eight bathroom files are not in the repo. The
  console says `Bath <name> stays procedural` (`web/house/home.js:978`), or
  `Bath light fallback` / `Bath door fallback` (`home.js:1009, 1016`), and the
  bathroom is drawn in code. Restore the files from where they were built, or
  rebuild them in Blender with `blender -b --python tools/build_home_bath_fixtures.py`
  (then the `build_home_bath_light.py` and `build_home_bath_door.py` scripts).
- Any other 404 under `/house/assets/`: the file is not under `web/`, which is the
  only static root (`live_server.py:2471`). The other asset files named in the
  house code existed on 2026-10-23.
- `/house` answers "Home is not enabled": `HOME_ENABLED` is not `1`
  (`home_api.py:49-51`).

**No reactions**

- The house page (`/`) does not show reactions. It shows "Impulse received. He
  chooses what to do." (`web/house/home.js:2771-2772`). Open `/life.html`.
- The page prints "not sent: <reason>" when the server refuses a message
  (`web/life.html:307`). Common reasons: "one message every 10 s" (rate limit),
  "duplicate", "links are not allowed" (`chat.py:309-326`).
- With the PC bridge off, a link gets the reply "I cannot open links yet."
  (`live_server.py:643`). That reply is a reaction, so it does show.
- Reactions are broadcast to every open page, and the duplicate copy is removed
  (`web/life.html:337-347`). If nothing arrives at all, check the browser console
  for the `/ws` connection; the page retries with backoff.

## What is running

- One shared cortical/life model and one CPU spiking process, initially 500,000
  neurons. The existing growth mechanism can increase that count.
- A real isolated v86 Linux guest with snapshots under ignored `data/` files.
- A separate Chromium process that browses pages chosen by the brain.
- One rendered first-person home. The monitor uses the browser's current image
  during research and the Linux terminal during `use_computer`.
- Separate computer and phone app selection. Opening the computer initially
  selects the app matching SUB-01's current activity.

## Verification recorded on 2026-10-12

The local browser started successfully after execution permissions changed.
The private backend served `/api/screen/desk.jpg` with HTTP 200 and a real image.
The running browser moved from Sky Sports to PC Gamer without a visitor choosing
the second page. The monitor and enlarged computer panel displayed that browser
in Chrome. Linux reported restoration from its saved state after the private
backend restarted. `/api/spiking/live` reported a live 505,000-neuron process.

This is progress toward the complete home, not a claim of completion. The visual
quality of the architectural reference, interaction fidelity, mobile performance,
and full end-to-end activity coverage still require further work and verification.

## Offline indirect lighting

The home now uses separate diffuse light bakes for daylight and indoor lamps.
Cycles calculates four diffuse bounces offline; the browser samples the two HDR
textures. Daylight strength follows the life clock, and the lamp contribution
switches off with the actual lamp setting. The lighter path uses 512-pixel-wide
maps. Dynamic sunlight and point lights still run normally. `?ao=1` selects the
previous contact-lighting path for comparison.

To rebuild after changing the house, open the local home with `?bake=1`, wait for
its assets to load, then click **Export house geometry**. The exported GLB is
saved under ignored `out/home-bake-source.png` (the extension is historical).
Prepare a new atlas with `tools/prepare_home_lightmap.py`, then run
`tools/bake_home_indirect.py` in Blender once with `day` and once with `night`.
`tools/pack_home_indirect.py` validates the floating-point result and writes the
desktop and light RGBE HDR maps. Keep source exports and EXRs outside Git.

The shipped maps and their hashes are recorded in
`web/house/assets/lighting/indirect-bake.json`. Source model/texture attribution
remains in the existing asset manifest. Geometry compatibility checks reject
outdated bakes rather than applying them to a changed object.

The day view was checked on a separate accelerated-clock QA server. The night
view and lamp-off transition were checked on the real private backend with the
505,000-neuron process and browser active. This does not establish performance
on other computers or on phones.

## First-person interactions and games

The gaze command now checks reach and opaque occluders before opening a device.
It is a button, so it works with E, click, or tap. The TV's console controls are
reachable from the sofa; nearby devices retain the shorter default reach.
Hidden parents and transparent glass/contact decals are handled separately from
opaque walls, doors, and furniture. The current target is rechecked on activation
and disabled while bathroom privacy is active. Room commands and the reticle hide
when a device panel is open.

Pong holds use periodic bounded input while a keyboard key or pointer is held.
Release, pointer cancellation, focus loss, closing the panel, and switching games
clear the hold. A late response cannot discard a newer stop command. The court
is keyboard-focusable. The server's existing short input expiry remains in place.

Checks: `tests/js/home_interaction_check.mjs` and
`tests/js/home_held_controls_check.mjs`, plus the home movement and API tests.
The real private backend was also checked through Chrome: opening the TV from
the gaze button and holding the keyboard/button during SUB-01's console activity.
The game remains governed by his activity, so it pauses when he leaves the console.
