# Private headless PC runner

`scripts/home_pc_runner.py` runs SUB-01's real PC without the full brain backend. It is meant for the native first-person bridge, on the private Runpod or localhost. For the PC inside the house (local guest, `HOME_ENABLED=1`, with or without `BROWSE`), the guest files `bootstrap.py` downloads and what each status means, see `docs/pc/README.md`.

It reuses `home_computer.Computer` unchanged:
- the pinned v86/WebAssembly machine: `computer/worker.cjs`, `libv86.cjs`, `v86.wasm`;
- the pinned Buildroot Linux image and BIOS (`computer/manifest.json`, SHA-256 checked by `computer/bootstrap.py`);
- the persistent `computer.bin` guest state.

Isolation is unchanged:
- **Guest access:** input reaches only the guest's serial console. The guest has no host mounts and no network.
- **Host execution:** the runner itself never executes anything on the host.

## Start

```sh
SUB01_ADMIN_TOKEN=... python scripts/home_pc_runner.py --data-dir /private/runtime/pc --port 8810
# or: --token-file /private/operator-token
```

- **Binding:** it binds only to loopback (`127.0.0.1`, `::1`, `localhost`) and refuses other hosts.
- **Credential:**
  - Use the existing operator credential (at least 12 characters).
  - It is never printed, and access logging is off.
- **Runtime data:** it must live outside the repository.
- **Shutdown:** SIGTERM or SIGINT asks the worker to save the guest and shut down.
- **Guest assets:** use the bundled `computer/` assets when present. Otherwise they are fetched once into `<data-dir>/computer-assets` and pinned by hash.

## Contract

Every route except `/healthz` requires `X-Admin-Token: <operator credential>`. Without it the runner answers 403. All responses are JSON with `Cache-Control: no-store`.

| Route | Body | Response |
|---|---|---|
| `GET /healthz` | – | `{"ok": true}` |
| `GET /pc/state` | – | `{status, ready, paused, output, last_command, commands, revision, os, error, privacy: false, session}` |
| `GET /pc/state?since=REV&wait=S` | – | Long-poll: returns as soon as `revision != REV` or privacy changes, or after S seconds (at most 25). |
| `POST /pc/input` | `{"input": str, "raw": false}` | `{"ok": bool, "revision": int}` |
| `POST /pc/session` | `{"active": bool}` | Current view. |
| `POST /pc/privacy` | `{"active": bool}` | Current view. |

**`POST /pc/input`**
- The text goes to the guest serial console, the same path as the house's `POST /api/home/computer`.
- A newline is appended unless `raw` is true. Use raw for keystrokes such as `"\u0003"`.
- The text is limited to 2000 characters. Bodies over 4 KB get 413, and invalid input gets 400.
- `ok: false` means the guest isn't ready yet.

**`POST /pc/session`**
- `active: true` means a first-person player is at the PC. It resumes the VM and keeps it running for 60 s, so the bridge should repeat it at least every 60 s while seated.
- `active: false` ends the session.
- Without a session or recent input (5 s), the VM pauses itself.

**`revision`**
- It is monotonic and increases on every change to any viewed field. That includes equal-length output replacements.
- `output` is the guest serial terminal, at most the last 10,000 characters, with ANSI sequences included. The house strips them for display.

### Privacy

`POST /pc/privacy {"active": true}` turns privacy on (bathroom).

While privacy is on:
- State is `{status, ready, paused: true, output: "", last_command: null, revision: null, privacy: true}`.
- The VM is paused.
- Input and session-start get **409** with the plain-text body `Bathroom privacy is active`.
- An input already in flight when privacy begins also returns 409, without output.
- A long-poll released by the change already sees the masked view.

`{"active": false}` restores the normal view.

The bridge should mirror the house's privacy state. In the full backend, privacy follows the actor's bathroom position.

## Verified

**Unit tests:** `tests/test_home_pc_runner.py` (6) covers:
- authentication on every route;
- the newline and raw input semantics and input limits;
- privacy blanking, including the in-flight 409;
- long-poll on a revision change and on a privacy change;
- the session keeping the VM running, then pausing it when idle;
- refusal of non-loopback hosts, short credentials and repo-local data.

**Live check on 2026-10-13, cloud container, real VM:**
- **Boot:** the guest booted to the Buildroot prompt in under 10 s and paused itself when idle.
- **Input:** `echo hello-from-first-person; uname -m` returned `hello-from-first-person` and `i686`.
- **Privacy:** it blanked the output and refused input with 409. Turning it off restored the terminal.

No GPU, Unreal or native-bridge test has been run here.
