# Private Minecraft console

This is a real Minecraft Java server and Mineflayer player, not a simulated
Minecraft scene. The owner explicitly accepted the Minecraft EULA on 2026-10-12. The local
live check confirmed exploration, wood collection, block placement, and the
actual first-person image on the wall TV. Switching games disconnects the
player. Inventory and position survived a server restart.
The player now refuses to dig its current support block, limits risky drops,
and chooses a destination away from the nearest hostile for escape. The
support-block refusal was observed in the live event ledger. Escape direction
has a geometric regression check; a controlled live hostile trial is still
pending. It can still fail a path or placement and reports those failures.

Prepared components:

- Official Minecraft Java 1.20.1 server, pinned to the publisher's SHA-1.
- Official Eclipse Temurin Java 17 runtime, verified against SHA-256.
- Pinned Mineflayer, pathfinder and Prismarine viewer packages in package-lock.
- A read-only first-person viewer bound to 127.0.0.1:8803. The game server is
  bound to 127.0.0.1:25569. Offline player identity is for this local NPC only;
  the game server must never be exposed outside loopback.
- The home backend captures this actual viewpoint for the TV. The observer
  browser does not run another Minecraft client or world simulation.
- A basic controller receives structured block/entity/inventory observations
  and uses cortical network activation plus saved action outcomes. This is
  not a claim of pixel-based understanding, general game intelligence or
  consciousness. First skills are exploration, visible wood collection,
  soil collection, eating, escaping and placing individual blocks.

The world, player saves, event ledger, action gains, runtime and server binary
stay under ignored `data/minecraft/`. They must not be committed or uploaded.

## Prepare and run

From this repository, install this directory's dependencies with `npm ci` and
run `python games/minecraft/bootstrap.py`. Bootstrap downloads and validates
official files and leaves `eula=false`. Do not change it without owner approval.
The EULA is at https://www.minecraft.net/en-us/eula.

After the owner has explicitly accepted it, set the local EULA flag and run the
private home launcher with `--minecraft`. The backend waits at the EULA gate;
when enabled it starts the real server, preserves its world and connects the
player only while SUB-01 is using the Minecraft console. Putting it away
disconnects the player and stops actions. Inventory/world persistence relies
on Minecraft's actual save files; the local restart check preserved collected oak and birch logs.

Console selection is shared server state and changes require the existing
owner access key. Pong and chess remain in the catalog. Future native games
can use the same TV frame interface with a different game provider.

## Attribution

The viewer transport is based on PrismarineJS/prismarine-viewer's Mineflayer
example, under its MIT license; see PRISMARINE-LICENSE. Dependencies retain
their own licenses. Minecraft and its game assets are governed by Mojang's
terms and are downloaded locally, not redistributed in this repository.

The private TV may capture one genuine initial idle view before autonomous play.
A one-time 20-second worker lease permits only the connection, with action and
reward authority remaining inactive. A captured idle frame is labeled
`initial_idle`; the renderer releases that client after capture, and timeout
releases it even if rendering fails. Later brain play still requires the actual
home activity/physical-readiness gate. This does not move the saved player,
change the world or manufacture a game frame.
