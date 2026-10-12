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
