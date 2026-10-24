# Pod access tools (any agent: Claude, Codex, ...)

The pod is RunPod `3u7g6drf5fiiql` (RTX PRO 4000, network volume `/workspace`). Everything goes through its Jupyter
server at `https://3u7g6drf5fiiql-8888.proxy.runpod.net` with the pod's Jupyter password as a token.

## Secrets (never in git, logs or chat)

Create `pods.json` OUTSIDE the repository (for example `~/.sub01/pods.json`, mode 600). It is the RunPod pod listing;
the tools only need this shape:

```json
[{"id": "3u7g6drf5fiiql", "env": {"JUPYTER_PASSWORD": "<the pod's Jupyter password, from the owner>"}}]
```

`netvol.py` (network volume get/grow) also needs `pods_body.txt` with the owner's RunPod API key in
`SUB01_HOME_CONTROL_API_KEY`; point `SUB01_POD_SECRETS_DIR` at its folder. Growing the volume costs money: only with
the owner's explicit OK. NEVER use "Edit Pod" on the container disk (it wipes everything outside `/workspace`).

The tools mask the token in their output. `podterm.py` and `podrun.py` propagate the remote command exit status; missing completion evidence, kernel errors and failed HTTP requests return nonzero. A signal termination maps to the usual shell status (128 + signal) in `podrun.py`. TLS certificate and hostname verification stay enabled; the existing custom CA bundle is used when present, otherwise the system trust store is used. Python needs `aiohttp` (podterm, podrun) and `curl` (jupput, vagon_dl).

## Tools (run locally)

| Tool | Use |
|---|---|
| `podterm.py pods.json POD 'bash cmd' [timeout_s]` | run bash through a Jupyter terminal (max ~230 s per call; for long jobs `setsid nohup ... > log 2>&1 < /dev/null & disown`, then poll) |
| `jupput.py pods.json POD local tmp/<dir>/<name>` | upload; lands at `/tmp/<dir>/<name>` (create the dir first) |
| `vagon_dl.py pods.json POD OUTDIR path...` | download from `/tmp/sub01-share/<path>` (copy the file there first) |
| `podrun.py pods.json POD 'cmd'` | one command through a short-lived kernel (fallback) |
| `netvol.py get|grow ...` | RunPod network volume (needs the API key; cost: owner's OK) |

## On-pod scripts (`onpod/`; copies live in `/tmp/sub01-share/` on the pod, `/tmp` is wiped on a pod restart)

| Script | Use |
|---|---|
| `frames.sh TAG [STATE]` | webcam frame (x11grab of the game on `:99`) + `room` layout frame from the local HLS + cam2 crop into `/tmp/sub01-share/tune/`; restores `webcam_only` |
| `tstep.sh TAG STATE key=value...` | apply live tuning keys (`/home/unreal/tune.py`), wait, capture frames, print the v23 receipt measurements; logs to `pod-changes.log` |
| `motion.sh` | 18 s typing → reading → typing webcam clip + contact sheet |
| `relaunch-m3-now.sh` | relaunch the game with the plain m3 launcher (loads whatever is in `Sub01HomeLab/Binaries/Linux`), write `game.pid`, keep the CPU partition loop, wait for new PERF lines |
| `build-v24.sh` | guarded coordinator build only; requires frozen source manifest, dry-run plan, installer checksums and binary marker in `deploy/v24`; refuses existing v24 backups, drift, missing STOP or a measurement lease; does not restart services |
| `build-v22.sh`, `build-v23.sh` | apply a native installer (`/tmp/sub01-share/deploy/vNN/`) with backups and build (refuse under `MEASURING`) |
| `deploy-sidecars.sh` | install scripts with backups and restart the supervisor with the full child-argument set (the reference supervisor command line) |

Other pod helpers already on the pod: `/tmp/sub01-share/gc.py` (live console cvars, as unreal, sequence in ms),
`/home/unreal/tune.py key=value` (live tuning file), `/home/unreal/camera-check.py camera state seconds` (drive the
visual by hand while the agent is held), Kimi CLI `runuser -u unreal -- python3
/home/unreal/.sub01-private/latest-source-20261023/tools/ask_kimi.py "q" --file F --image I --max-tokens 24000 --timeout 600`
(files readable by unreal; Kimi often answers HTTP 429: retry every 60-120 s; smaller token budgets end with
"max_tokens reached while reasoning").

Rules that bind these tools: `/tmp/sub01-share/MEASURING` = measurement lease (no builds, deploys, restarts or heavy
jobs while it exists); every build, deploy, restart or runtime change gets a line in `/tmp/sub01-share/pod-changes.log`
and later in `docs/streamer/POD-CHANGES.md`.
