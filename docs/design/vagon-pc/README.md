# Vagon cloud PC for the persona

Status: client, bridge and offline tests are written, and all offline tests pass. Nothing has run against Vagon: this
environment has no credentials and makes no network calls. Until the steps in "Verify with real credentials" have run
once, these are unverified: the signed path, the JSON field names, the status strings, whether run-script reaches the
desktop, and the length limit of run-script.

Source for the claims about Vagon in the first sections: the Vagon docs and terms pages, read on 2026-10-22. This
revision did not re-read them (no network), so check a detail against the pages before relying on it.

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

## Code

- `vagon_pc.py`: signed calls and the Teams calls listed above. `reset` is not in the file, and a test checks that.
- `vagon_bridge.py`: starts the machine when it is off, then opens one link on it. `live_server.py` imports `enabled`,
  `open_url_async` and `configure_auto_stop`; those keep working. `probe` and `submit_link` are the entry points for the
  wiring described under "Wiring" below.

## Signing

`Authorization: HMAC {key}:{signature}:{nonce}:{timestamp}`. The signature is the hex HMAC-SHA256, keyed with the API
secret, of `key + method + path + timestamp + nonce + body`, with no separators. The timestamp is in milliseconds and must
be less than 60 s old. `call()` signs the exact JSON text it sends (compact separators, the same bytes). The query string
is not signed.

Two readings are not settled by the text quoted here, so the tests and the procedure below check them:

- `path` is the prefixed path, `/organization-management/v1/machines`, which is what the code signs. If Vagon signs the
  path without the prefix, every call returns 401. The procedure has a step for that.
- The field order (key, method, path, timestamp, nonce, body) comes from the design brief, not from a live call.

Known answers, in `tests/test_vagon_pc.py`. Each signature was computed with the openssl CLI, outside the Python code, so
a wrong field order, a wrong separator or a wrong key use fails the test:

| Request | Key / secret | Payload (text that is signed) | Signature |
|---|---|---|---|
| `GET /organization-management/v1/machines`, ts `1700000000000`, nonce `0123456789abcdef`, no body | `test-key` / `test-secret` | `test-keyGET/organization-management/v1/machines17000000000000123456789abcdef` | `c734bd81f890e7db290e0b790dfff9cb74e90ce67a824c8871dc0985d88efe19` |
| `POST /organization-management/v1/machines/machine-1/stop`, ts `1700000000001`, nonce `fedcba9876543210`, body `{"gracefully":true}` | `test-key` / `test-secret` | `test-keyPOST/organization-management/v1/machines/machine-1/stop1700000000001fedcba9876543210{"gracefully":true}` | `d74842de2377abad37a6891244565ed06910d2d4316aa916592bdb585ed6a173` |

## Machine status and waiting

The status is `attributes.friendly_status` in `GET /machines`. The constants are in `vagon_pc.py`:

| Value | Set | What the bridge does |
|---|---|---|
| `ready` (the value the vendor list names) | `READY_STATUSES` | opens the link |
| `running`, `on` | `READY_STATUSES`, candidates only | opens the link |
| `off`, `stopped` | `OFF_STATUSES` | starts the machine once (`POST .../start`), then waits |
| `creating`, `turning_on` | `STARTING_STATUSES` | waits; never starts |
| `turning_off` | `KNOWN_STATUSES` only | waits; never starts (so a shutdown is not reversed by a new start) |
| any other string | not in a tuple | waits; never starts; the string is logged once |
| no status field | `None` | error; nothing is started |

`wait_ready` polls every 15 s and gives up after 300 s with an error. The last sleep ends at the deadline.

## Bridge behaviour

- On only with `VAGON_PC_ENABLED=1` and the three other variables. Nothing else switches it on.
- `submit_link(url)` returns `(True, '')` when the link is queued, or `(False, reason)`: `off`, `invalid` (not a plain
  http or https link without spaces), `full` or `thread`.
- One worker thread opens the links in arrival order. Up to 3 links wait behind the one in progress. When 3 are waiting,
  the newest is dropped; the reason goes to `status()['last_refusal']` and to the log.
- Each link: read the status, start the machine only if it is off, wait until it is ready, open the link. Nothing retries,
  HTTP 429 included.
- `probe()`: once, at startup, one `GET /machines`. It logs `outcome=ok status=...` at INFO, or at ERROR when the call
  fails or the machine id is not listed. The outcome is in `status()['probe']`.
- `configure_auto_stop()`: once per process, 900 s. The outcome is in `status()['auto_stop']`, and a failure there does not
  overwrite the last open step.
- `status()` returns `enabled`, `state`, `detail` (the last step), `waiting`, `last_refusal`, `probe` and `auto_stop`.
- Logs carry the action, the host and the outcome. Never the link's path or query, a key, a secret or a signature.

## Running a script on the PC: safety

A link must pass `vagon_pc.is_plain_link`: `http://` or `https://`, printable ASCII, no space, at most 2000 characters.
Its bytes travel as base64 inside one fixed line:

```
Start-Process -FilePath ([System.Text.Encoding]::ASCII.GetString([System.Convert]::FromBase64String('<base64>')))
```

The link is never written into the script as text. So quotes, `$()`, backticks, separators and newlines in a link are data,
whichever shell the vendor's agent uses to run the script. `tests/test_vagon_pc.py` sends hostile links through
`open_url`, and checks that the script holds nothing but the base64 literal. The vendor's length limit for a script is not
documented; a 2000-character link makes a script of about 2.8 kB.

## Environment

| Variable | Set on | Used by |
|---|---|---|
| `VAGON_PC_ENABLED` | the pod | `1` switches the bridge on; any other value keeps it off |
| `VAGON_MACHINE_ID` | the pod | the machine's id, from `GET /machines` |
| `VAGON_API_KEY` | the pod | the Teams API key; not in git, not in chat |
| `VAGON_API_SECRET` | the pod | the HMAC key; never printed |
| `VAGON_PLAN_ID` | the pod, for one manual create | no code reads it; the create step of the procedure does |
| `VAGON_REGION` | the pod, for one manual create | no code reads it; the create step of the procedure does |

Railway: leave the four bridge variables unset. The bridge then stays off, and the public chat answers "I cannot open
links yet." Setting `VAGON_PC_ENABLED=1` there would let any visitor of the public chat open a link on the PC. That is the
owner's decision, not a default.

## Verify with real credentials (owner, once)

Run these in a shell on the pod, or on any machine with `python3`, `curl` and `base64`. Type the key and the secret at the
prompts. Do not paste them into chat or into a file. Replace `<machine-id>` with the id from step 1.

Setup:

```bash
read -rs VAGON_API_KEY && export VAGON_API_KEY        # paste the key, press Enter
read -rs VAGON_API_SECRET && export VAGON_API_SECRET  # paste the secret, press Enter
export VAGON_MACHINE_ID='<machine-id>'
export VAGON_API='https://api.vagon.io/organization-management/v1'

# Signs one request. The secret is read from the environment, never from the command line.
vagon_auth() {
  python3 -c '
import hashlib, hmac, os, sys, time, uuid
method, path, body = sys.argv[1:4]
key, secret = os.environ["VAGON_API_KEY"], os.environ["VAGON_API_SECRET"]
ts, nonce = str(int(time.time() * 1000)), uuid.uuid4().hex
sig = hmac.new(secret.encode(), f"{key}{method}{path}{ts}{nonce}{body}".encode(), hashlib.sha256).hexdigest()
print(f"HMAC {key}:{sig}:{nonce}:{ts}")
' "$1" "$2" "$3"
}
```

1. List the machines. HTTP 200 proves the signature. Note the machine's `id` and its `friendly_status`, exactly as sent.

   ```bash
   curl -sS -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth GET /organization-management/v1/machines '')" \
     "$VAGON_API/machines"
   ```

   If this is 401, repeat with the path without the prefix. A 200 from this one means the prefix is not signed: report it,
   and the code's `call()` changes.

   ```bash
   curl -sS -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth GET /machines '')" \
     "$VAGON_API/machines"
   ```

   If both return 401, check the clock (`date -u`; a request is valid for 60 s), then the key and secret pair.

2. Start the machine, only when the status is `off` or `stopped`. It costs money while it runs. Then repeat step 1
   every 15 s until the status is the ready value. Give up after 5 minutes and record the last value.

   ```bash
   curl -sS -X POST -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth POST "/organization-management/v1/machines/$VAGON_MACHINE_ID/start" '')" \
     "$VAGON_API/machines/$VAGON_MACHINE_ID/start"
   ```

3. Run a script. Expected: the output text `hello`. The code reads the field `result`; record the real field name if it
   differs.

   ```bash
   BODY='{"script_body":"Write-Output hello"}'
   curl -sS -X POST -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth POST "/organization-management/v1/machines/$VAGON_MACHINE_ID/run-script" "$BODY")" \
     -H 'Content-Type: application/json' --data-binary "$BODY" \
     "$VAGON_API/machines/$VAGON_MACHINE_ID/run-script"
   ```

4. Open a harmless link, with the same script the code builds. Expected: the page opens on the PC. Check it in the Vagon
   client, or through step 5. If the answer is 200 but no page opens, run-script does not reach the interactive desktop.
   Record that: it decides the design.

   ```bash
   LINK='https://example.com/'
   ENC=$(printf '%s' "$LINK" | base64 | tr -d '\n')
   SCRIPT="Start-Process -FilePath ([System.Text.Encoding]::ASCII.GetString([System.Convert]::FromBase64String('$ENC')))"
   BODY="{\"script_body\":\"$SCRIPT\"}"
   curl -sS -X POST -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth POST "/organization-management/v1/machines/$VAGON_MACHINE_ID/run-script" "$BODY")" \
     -H 'Content-Type: application/json' --data-binary "$BODY" \
     "$VAGON_API/machines/$VAGON_MACHINE_ID/run-script"
   ```

5. Create a connection link. Expected: a URL. Does it open in a browser outside the Vagon app?

   ```bash
   BODY='{"expires_in":30}'
   curl -sS -X POST -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth POST "/organization-management/v1/machines/$VAGON_MACHINE_ID/access" "$BODY")" \
     -H 'Content-Type: application/json' --data-binary "$BODY" \
     "$VAGON_API/machines/$VAGON_MACHINE_ID/access"
   ```

6. Set the auto-stop. Expected: HTTP 200.

   ```bash
   BODY='{"auto_stop_threshold":900}'
   curl -sS -X PATCH -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth PATCH "/organization-management/v1/machines/$VAGON_MACHINE_ID" "$BODY")" \
     -H 'Content-Type: application/json' --data-binary "$BODY" \
     "$VAGON_API/machines/$VAGON_MACHINE_ID"
   ```

7. Stop the machine when done.

   ```bash
   BODY='{"gracefully":true}'
   curl -sS -X POST -w '\nHTTP %{http_code}\n' \
     -H "Authorization: $(vagon_auth POST "/organization-management/v1/machines/$VAGON_MACHINE_ID/stop" "$BODY")" \
     -H 'Content-Type: application/json' --data-binary "$BODY" \
     "$VAGON_API/machines/$VAGON_MACHINE_ID/stop"
   ```

8. Run the code path once, from the repository root, with the variables from the setup and `VAGON_PC_ENABLED=1`.
   Expected: the probe logs `outcome=ok status=<value>`, and the last line shows `state` `ready`.

   ```bash
   VAGON_PC_ENABLED=1 python3 -c '
   import logging, time, vagon_bridge as b
   logging.basicConfig(level=logging.INFO)
   b.probe()
   print(b.submit_link("https://example.com/"))
   time.sleep(1)
   while b._worker_running:
       time.sleep(5)
   print(b.status())
   '
   ```

Record for the design: the status values seen, the field names that differ from this document, whether the prefix is
signed, whether the page opened, and the HTTP codes.

## Offline tests

```bash
BROWSE=0 python -m pytest -q -p no:cacheprovider tests/test_vagon_pc.py tests/test_vagon_bridge.py
```

They cover: the known answers, the body inside the signature, no retry on 429, error text without credentials, JSON and
timeout errors, no redirects, bounded waiting, unknown status values, the link gate, hostile links reaching the script
only as base64, the queue order and the drop of the newest link, the probe outcomes, and the absence of secrets and links
from status and logs. They do not cover the HTTP exchange or PowerShell; only the steps above do.

## Wiring

`live_server.py` is not changed on this branch. It works as it is: `open_url_async` returns a bool, and the chat then says
"The PC is busy..." for any refusal. Three edits make the new behaviour visible (not applied):

1. Import (`live_server.py`, lines 65-66):

   ```python
   from vagon_bridge import (configure_auto_stop as vagon_auto_stop, enabled as vagon_enabled,
                             probe as vagon_probe, submit_link as vagon_submit_link)
   ```

2. Chat reply for a link (`live_server.py`, lines 638-643). The reasons map to in-character lines of at most 60 characters:

   ```python
   VAGON_REFUSED = {"full": "The PC already has links waiting. Send it again shortly.",
                    "thread": "The PC is busy. Send it again shortly.",
                    "invalid": "I cannot open that link.", "off": "I cannot open links yet."}
   ...
           elif imp.kind == "open_url":
               if links_open:
                   queued, why = vagon_submit_link(imp.url)
                   reaction = imp.reaction if queued else VAGON_REFUSED.get(why, "I cannot open that link.")
               else:
                   reaction = "I cannot open links yet."
   ```

3. Startup (`live_server.py`, lines 2503-2504): one listing, then the auto-stop, both off the event loop.

   ```python
           if vagon_enabled():                                    # the PC: one listing at startup, then the idle auto-stop
               tasks.append(asyncio.to_thread(vagon_probe))       # blocking HTTP: a thread, never the event loop
               tasks.append(asyncio.to_thread(vagon_auto_stop))
   ```

## Questions to send to Vagon (support@vagon.io / info@vagon.io)

- Does the signature cover the path with the `/organization-management/v1` prefix? One worked example (key, method, path,
  timestamp, nonce, body and the resulting signature) would settle it.
- Is the field order key, method, path, timestamp, nonce, body, and is the body signed as the exact bytes sent?
- Is `GET /machines` paginated? Which field is the id? Is the status in `attributes.friendly_status`? Which status values
  exist (for example: is a running machine `ready`, `running` or `on`; are `stopped` and `turning_off` real)?
- The JSON field names: `script_body` and `result` (run-script), `expires_in` (access), `auto_stop_threshold` (auto-stop),
  `gracefully` (stop), `plan_id`, `quantity`, `region`, `os` (create).
- Run-script: which shell runs it (Windows PowerShell 5.1 or 7), as which user (admin?), and does `Start-Process` show a
  browser on the logged-in desktop? What is the maximum script length?
- Is a start on a machine that is on, or still turning on, an error? The bridge does not send one in those states.
- How often may `GET /machines` be polled? The bridge polls every 15 s while it waits for a machine.
- Does the connection link work outside the Vagon app?
- Is run-script used to open links allowed under the terms (5.1, 9.1, 9.2)? Is it allowed for the persona's own use?
- Team prices per performance option.
- Is there any API path for keyboard, mouse or a screen image? None is documented; "use the PC" depends on the answer.
