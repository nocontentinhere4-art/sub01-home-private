# Private native activity feedback

Source contract implemented; physical seating and native runtime acceptance are pending.

The authenticated loopback state bridge accepts `POST /home/native_state` and
forwards to the actual backend `POST /api/home/native_state` using its existing
operator credential. Both routes require authentication and an actual loopback
peer; forwarded-address headers cannot bind a native consumer.

Example initial binding (substitute the current published values):

```json
{"epoch":"current bridge epoch","sequence":1,"activity":"research","node":"desk","phase":"walking","bind":true}
```

`epoch` comes from the state document, `sequence` from `actor.route_sequence`,
and `activity` from `brain.activity`. The bridge requires a live, nonprivate
source and matching command values. The backend independently checks its
current sequence/activity/destination and privacy. Explicit `bind:true` is
accepted only with `walking`; it clears earlier physical evidence. Later reports
omit `bind` or use `false`. No native binding occurs just by polling state.

Phases are `walking`, `arrived`, `seated`, and `blocked`. Arrival/seating must name
the current destination. Seating must identify the corresponding registered
protocol seat: `desk_chair` at desk, `sofa` at sofa, or `bed` at bed. These names
are protocol identifiers, not proof of a physical trace: the native sender must
validate the corresponding actual component before reporting seating.

Readiness at desk/sofa/bed requires fresh seated evidence; other stations require
fresh arrived evidence. Evidence lasts three monotonic seconds, must match the
current epoch/sequence/activity/node, and is renewed only by an accepted report.
A blocked report inhibits readiness. This endpoint does not force a brain
activity, move an actor, change privacy, or invent a seat result. Native binding
remains in force after evidence expires, so losing the native consumer cannot
silently fall back to the browser seating timer. Restarting the backend clears
all ephemeral native evidence; browser-only mode retains its prior behavior
until explicitly bound again.

Success: `200 {"ok":true,"fresh_for_s":3}`. Malformed input/unknown seat: 400;
unauthenticated/nonloopback: 403; stale epoch/command, privacy or unbound epoch:
409; unavailable bridge/backend: 503 (unexpected upstream failures: 502).

Tests exercise the actual registered bridge and backend routes with HTTP
requests, including rejected reports and a backend privacy change ahead of its
next bridge tick. They isolate the router's literal activity catalog dependency;
they do not start the numerical brain, a browser, emulator or native renderer.
