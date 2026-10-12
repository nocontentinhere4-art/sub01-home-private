# Private device integration check

This check used `data/qa-daytime-03` on localhost 8804 with isolated Minecraft ports 25570/8805. The fixture explicitly initializes a fed body and console activity; it does not prove spontaneous game selection. The main house listener on 8798 (PID 42900 during this check) and its data were not changed.

The QA runtime rebuilt the copied learned weights and growth state: 510,000 neurons and 51,498,978 synapses. No paid model, trading or remote GPU service was enabled.

Verified through actual HTTP/WebSocket/device processes:

- Minecraft was connected, playing and producing a 26,256-byte JPEG from the real local game. Switching to Pong disconnected/paused Minecraft; the Pong ball moved. Switching back resumed Minecraft with the same six oak logs and four birch logs.
- Unauthenticated game selection, note editing and Linux input returned HTTP 403. Authenticated actions worked in the isolated fixture.
- The restored Linux guest read `/root/sub01-home-check.txt` and returned `SUB-01 guest filesystem check`. Manual input resumed the guest; it paused again after the five-second operator grace period while SUB-01 remained at the TV.
- A blank message received a negative real `chat_ack`; a valid English impulse received a positive acknowledgement.
- A phone note was saved and remained in the fixture's persisted state after graceful shutdown. The Linux snapshot after shutdown was 26,532,516 bytes.
- An authenticated QA nudge toward the computer was accepted. Observed getting up, walking and settling at the desk. The computer remained paused throughout seated progress 0.033–0.942; its first automatic command appeared only at seated progress 1.

The underlying bug was that an empty route was treated as arrival before the camera had finished sitting. `HomeWorld.activity_ready` now gates activity timers, browser/reading/music/chess tasks, Linux, Minecraft and Pong on the correct destination and completed seat transition. Automatic device pause/resume checks now run on each home tick; their existing decision limits remain 18 seconds for Linux and two seconds for Minecraft. Brain reward feedback retains its previous one-second cadence. The final cadence change was checked by source inspection and targeted tests; the live seating observation above preceded that final change.

83 relevant tests passed, covering arrival timers, settled device activation, departures, Minecraft selection, API authorization, console requests, browser navigation, shutdown/port handling and music wishes. This is not a full-suite or whole-house fidelity claim. Minecraft still uses bounded structured observations; an observed pathfinding timeout remains a normal reported failure rather than evidence of general game intelligence.
