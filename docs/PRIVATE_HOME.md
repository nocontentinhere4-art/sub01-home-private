# Private local home

This repository is private. Run the home on loopback only. Do not deploy this
repository, connect it to Railway, or modify the public SUB-01 service.

## Run locally

Use a Python environment with `requirements-server.txt` installed. The browser
also requires the official Playwright Chromium installation. The local browser
launcher uses the existing local environment and cache when available:

```sh
./scripts/start-private-browser.command
```

Leave that process running. In another terminal, from this repository:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/start_home_local.py \
  --browser-service http://127.0.0.1:8799
```

Open `http://127.0.0.1:8798/house`. Both services bind only to loopback. The
browser uses an isolated profile, not the operator's personal Chrome profile.
The launcher disables paid AI integrations, coin trading, and cloud pod startup.
Its fixed operator token is for local development only and must never be used
for a public deployment.

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
