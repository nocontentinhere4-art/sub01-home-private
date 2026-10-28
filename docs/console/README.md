# The wall TV console (Pong, chess, Minecraft)

How the console in the private home works end to end, what must be installed for each game,
and what the TV shows in every state. Nothing on the TV is simulated: Minecraft is a real
local Java server and Mineflayer player captured by Playwright, Pong and chess are server
state drawn by the page. When Minecraft cannot run, the TV says so and he plays Pong.

## The path from a chat message to the picture on the TV

1. `live_server.handle_chat` filters the message, then calls `life.hear(text, t)` and
   `impulse.parse(text)`.
   - `console_requests.game_request` reads a named game ("play minecraft", "switch to pong",
     "put on Pong", "gioca a Minecraft", a bare "pong"). A soundtrack request is music, not a
     game. The name becomes `life.console_wish = (game, t)` when that game is configured
     (`life.console_games`), and lives `console_requests.TTL` = `life.CONSOLE_WISH_TTL`
     (3600 sim seconds).
   - `impulse.parse` maps tv/console/game/pong/minecraft to the activity `play_console`;
     `life.request_impulse` keeps the latest request and the reaction is broadcast at once.
2. `life.update` carries the impulse out on the next tick (awake, not walking):
   `life.start('play_console')` turns the wish into `life.console_choice` when it is still
   within the TTL, and clears the wish. The latest named game wins.
3. `home_world.HomeWorld.update` reads the life snapshot: with `activity == 'play_console'`
   and a new `console_choice`, `console_game` becomes that game; the destination of
   `play_console` is the sofa. Pong runs only once he is settled (`activity_ready`).
4. The page (`web/house/home.js`) follows `home.console_game` from the WebSocket/`/api/home`
   and draws the TV canvas: Pong from `home.pong`, chess from `/api/chess`, Minecraft from
   `/api/home/minecraft/frame.jpg` (conditional requests, `ETag` = frame identity).
5. The player:
   - Pong: `home_world.Pong` moves the left paddle from live motor/attention signals; viewers
     move the right one through `POST /api/home/pong` (rate limited, no key needed).
   - Chess: `live_server.chess_step` plays on the TV while `console_game == 'chess'`.
   - Minecraft: `home_minecraft.MinecraftConsole.agent_step` sends the worker
     `{"type": "active"}` while he is settled at the sofa with Minecraft selected, then an
     action every 2 s chosen from the structured observation (`choose`). With
     `SUB01_BRAIN_CONTROLLER=1` the actions go through `home_minecraft_controller` as bounded
     gamepad input instead, gated on the native seat/grip receipts.

The operator can also pick a game with `POST /api/home/game {"game": ...}` (owner key). It
clears the pending chat wish. Minecraft is refused with HTTP 409 and the reason while the
console is offline, so the TV is never switched to a game that cannot show anything.

## Running the console locally

Pong and chess need nothing beyond the server:

    HOME_ENABLED=1 BROWSE=0 python live_server.py --host 127.0.0.1 --port 89xx --data-dir <dir>

or `python scripts/start_home_local.py` (loopback only, paid integrations off). The TV at
`/house` shows Pong as soon as he sits on the sofa. `BROWSE=0` only disables the desk/phone
browser screens and videos; the console does not use the browse service.

Minecraft (`--minecraft`, i.e. `SUB01_MINECRAFT=1`) needs, in this order:

| Requirement | How to get it | Checked by |
| --- | --- | --- |
| Official server + Java 17 in `data/minecraft/` (`server.jar`, `downloads.json`, `server.properties`, `eula.txt`) | `python games/minecraft/bootstrap.py` (downloads from Mojang/Adoptium, checksummed) | `missing_requirements`: "the official server is not prepared" / "the Java runtime is missing" |
| EULA accepted by the owner | set `eula=true` in `data/minecraft/eula.txt` after reading https://www.minecraft.net/en-us/eula | status `needs_eula` |
| Node 18+ and the pinned packages | `cd games/minecraft && npm ci` (creates `node_modules/`, never committed) | "node is not installed" / "Node packages missing ... (run `npm ci` ...)" |
| Playwright for Python with Chromium | `pip install playwright && playwright install chromium` | "the playwright Python package is not installed" |
| Loopback binding `server-ip=127.0.0.1`, `server-port=25569` (or `SUB01_MC_SERVER_PORT`) | written by bootstrap | "server.properties must bind 127.0.0.1:<port>" |

`SUB01_MC_SERVER_PORT` / `SUB01_MC_VIEW_PORT` (defaults 25569 / 8803) keep a test instance
apart from the main one; `SUB01_MC_HARDWARE_WEBGL=1` is the opt-in GPU capture path.

`MinecraftConsole.run` polls these requirements every 2 s **before** starting anything: a
missing piece is logged once as `console offline: <reason>` and nothing heavy runs, so a
broken install never boots and kills the Java server in a loop. Once everything is in place
the server starts without a restart of the home.

## What the TV shows

| State (`/api/home` → `minecraft.status`) | TV | Who plays |
| --- | --- | --- |
| `disabled` (`SUB01_MINECRAFT` unset) | Pong court / chess board; the Minecraft button is absent | Pong or chess |
| `offline` (runtime missing, reason in `error`) | `Minecraft · Console offline: <reason>` while Minecraft is selected; the console then switches the TV to Pong at once, with a dim band "Minecraft offline: <reason>" over the court | Pong |
| `needs_eula` | same as offline, reason "the owner has not accepted the Minecraft EULA" | Pong |
| `preparing`, `starting_server` | `Minecraft · Starting the Minecraft server…` | nobody yet |
| `ready`, `connecting` | `Minecraft · Connecting the player to his world…` | the worker connects while he is at the sofa |
| `paused` | the last real frame (`frame_kind: initial_idle` or `active`), or `Paused · he is not at the TV` | nobody: he is elsewhere |
| `playing` | live JPEG frames at up to ~7 fps, 640×360 captured, drawn on the 800×460 TV | the console (`last_action`), or the gamepad controller |
| `error` (crash) | `Console offline: <error>`; after 15 s (`OFFLINE_GRACE`) without a recovered restart the TV switches to Pong | Pong after the grace |

The TV panel (`E` at the sofa, or the TV button) shows the same status line under the
picture for every game, the game buttons (Minecraft reads "Minecraft (offline)" while it
cannot run and a click explains why), and the ↑/↓ paddle controls for Pong.

`minecraft.offline_reason` and `minecraft.fallback` in `/api/home` carry the reason and the
last automatic switch (`{"from": "minecraft", "to": "pong", "reason", "at"}`) for other
clients. Bathroom privacy hides frames, observations and the controller, as before.

## Checks

    BROWSE=0 python -m pytest -q tests/test_home_minecraft.py tests/test_console_requests.py \
        tests/test_home_game_api.py tests/test_home_minecraft_etag.py tests/test_minecraft_renderer_idle.py
    node tests/js/minecraft_render_budget_check.cjs      # the 15 fps viewer draw budget
    node tests/js/minecraft_viewer_readiness_check.cjs   # real terrain/texture readiness before a frame counts

`tests/js/minecraft_item_rendering_check.cjs` needs `games/minecraft/node_modules` (it loads
the pinned prismarine packages); without them it fails with `Cannot find module`, which is
the same "not installed" state the console reports.
