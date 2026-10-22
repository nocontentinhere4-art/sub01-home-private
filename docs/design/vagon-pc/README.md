# Vagon cloud PC for the persona

Status: client and tests written, not run. This environment has no Vagon credentials and made no calls to Vagon. Source
for every claim below: the Vagon docs and terms pages, read on 2026-10-22.

## What the Teams API does (documented)

- Create (`POST /machines`, needs `plan_id`, `region`, `os`), start, stop (`gracefully`), update auto-stop (0, 900, 3600,
  10800 or 21600 s of idle time), change performance (stopped machines only), reset (irreversible wipe, not exposed by
  `vagon_pc.py`), connection link (`POST /machines/{id}/access`), run-script (PowerShell on Windows; the vendor gives it
  about 5 s to answer).
- Status: there is no single-machine GET. Read `friendly_status` from the list (`off`, `creating`, `turning_on`,
  `ready`, `turning_off`, ...).
- Auth: HMAC-SHA256 on every request; timestamps in milliseconds, rejected after 60 s.

## What it does not do (as documented)

- Keyboard or mouse input from outside the Vagon client. "Input recording" records; it does not send.
- A screen image or a raw stream. The connection link is a Vagon-hosted session page.
- Direct RDP or VNC, internet access from the machine, admin rights, or installing software. The pages read do not cover
  these.

## Consequence for the room

Until there is a screen source, the room can show the PC's status and the last command, as text, not the real desktop.
Two ways to get a real picture, both needing Vagon's answer first:

1. A frame or stream API from Vagon.
2. Opening the session link in a headless browser and capturing it. Terms 5.1 say the machine is "accessed and used
   through the interface provided by the Company", so do not do this without Vagon's written OK.

## Terms (Vagon terms page; it says "Last Updated: 15.04.2021", so confirm it is current)

- 5.1: the machine is used through the Company's interface. No clause on scripts or automation either way.
- 9.1: no illegal purpose, no circumventing access limits, no reverse engineering.
- 9.2: no malware, network scanning, fraud, impersonation, or collecting personal data about others.
- 13.1: use at your own risk. 14.3: access ends for unlawful use. 18: suspension without prior notice.
- Consequence: the persona may open links through the documented run-script path. The prohibitions in 9.1 and 9.2 still
  apply to what it does, and the chat guardrails stay in place.

## Cost

- Teams: a subscription per team computer. The pages read give no Team price (the region-prices page has no Team
  figures). Ending the subscription deletes all team computers and their data.
- Per-minute Computer prices, which are a different product from the Teams API: Sand $0.25/h (2 cores, 4 GB) up to
  Ocean $4.59/h (24 cores, 192 GB); GPU A10G 24 GB from $1.67/h; T4 16 GB from $0.99/h.

## The adapter (`vagon_pc.py`)

Signs requests as documented, wraps create/start/stop/auto-stop/connection link/run-script, and has `open_url`, which
accepts only plain http(s) links without spaces and quotes them for PowerShell. Reset is deliberately absent.

## Needed before a test on a pod

1. API key and secret, set as `VAGON_API_KEY` and `VAGON_API_SECRET` in the pod environment. Not in git, not in chat.
2. `VAGON_PLAN_ID` and `VAGON_REGION`, from the Team Console.
3. The screen decision: a frame API from Vagon, or browser capture with Vagon's written OK.
4. The Team price, confirmed.

## Test plan on a pod

1. `GET /machines` with the signature. A 200 confirms the payload order; a 401 means the order or encoding differs.
2. Create, wait for `ready`, run-script `Write-Output hello`, check the returned text.
3. `open_url` to a harmless page; check manually, through the connection link, that the browser opened.
4. Stop, then check that auto-stop is applied.

## Questions to send to Vagon (support@vagon.io / info@vagon.io)

- Is scripted control of a Team computer through run-script allowed by the terms?
- Is there an API to read a screen frame or a stream of a running machine?
- Do the machines have internet access and admin rights for the user?
- What are the Team prices per performance option?
