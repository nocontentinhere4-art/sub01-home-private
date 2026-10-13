# Private home-state bridge for native Unreal

`tools/unreal_home_state_bridge.py` lets the native Unreal client follow the real running home without new backend endpoints. It is a small protocol adapter. It reads the authenticated home backend (`live_server.py` with `HOME_ENABLED=1`) and republishes only what a native client needs, as one versioned JSON document.

It is private and loopback only, like `scripts/home_pc_runner.py`. Nothing here deploys, publishes or touches the live site.

## What it consumes

| Backend source | When | Used for |
|---|---|---|
| `GET /api/home` (sends `X-Admin-Token`) | On start and on every reconnect | Full `home` view and `stage` |
| `WS /ws?rate=5&lite=1` (sends `X-Admin-Token`) | Continuously | `tick` messages: `home` (the compact `HomeWorld.view()`) and `sleep.stage` |
| `POST /api/home/settings` (sends `X-Admin-Token`) | Only on an operator control request | Door and light operator modes |

**Reconnecting:** after any error or socket close, the bridge waits with exponential backoff (0.5 s doubling to 10 s), then takes a fresh REST snapshot and reopens the socket.

**Credential:** never logged or published. Request logging is off.

## Start

```sh
SUB01_ADMIN_TOKEN=... python tools/unreal_home_state_bridge.py \
    --backend http://127.0.0.1:8765 --port 8811
# or: --token-file /private/operator-token
#     --transform-file /private/ue-import-transform.json
#     --stale-after 3 --unavailable-after 15
```

**Startup refusals:** the bridge refuses to start if any of these holds:
- the bind host is not loopback (`127.0.0.1`, `::1`, `localhost`);
- the backend URL is not loopback;
- the credential is shorter than 12 characters;
- `stale-after` is not below `unavailable-after`.

## Contract

Every route except `/healthz` requires the operator credential, as `X-Admin-Token: …` or `Authorization: Bearer …`. Without it the bridge answers 403. Every response carries `Cache-Control: no-store`.

| Route | Response |
|---|---|
| `GET /healthz` | `{"ok": true}` |
| `GET /home/state` | The state document. |
| `GET /home/state?since=REV&wait=S` | Long-poll. Returns as soon as `revision != REV`, or after S seconds (at most 25) with the unchanged document. A bad `since` or `wait` gets 400. |
| `POST /home/controls` | Body `{"doors": {...}, "lights": {...}}`. Forwarded to `POST /api/home/settings`. |

### The state document (live, actor walking to bed)

```json
{
  "schema": "sub01.home-state.v1",
  "epoch": "a440853d6af7",
  "revision": 2,
  "source": {"status": "live", "backend_url_host": "127.0.0.1", "last_message_age_s": 0.0},
  "privacy": false,
  "brain": {"stage": "AWAKE", "activity": "sleep"},
  "actor": {
    "node": "stair_bottom",
    "target": "bed",
    "path": [
      {"node": "stair_top", "level": "upper", "floor_cm": [30.0, -170.0, 300.0]},
      {"node": "landing",   "level": "upper", "floor_cm": [30.0, -210.0, 300.0]},
      {"node": "loft",      "level": "upper", "floor_cm": [-50.0, -210.0, 300.0]},
      {"node": "bed",       "level": "upper", "floor_cm": [-120.0, -290.0, 300.0]}
    ],
    "path_source": "derived-route-graph",
    "seated": 0.0,
    "moving": true,
    "route_sequence": 1
  },
  "destinations": {
    "mode": "walk",
    "next":  {"node": "stair_top", "level": "upper", "floor_cm": [30.0, -170.0, 300.0]},
    "final": {"node": "bed", "level": "upper", "floor_cm": [-120.0, -290.0, 300.0]}
  },
  "doors": {
    "front":    {"open": false, "locked": false, "mode": "auto"},
    "bathroom": {"open": false, "locked": false, "mode": "auto"},
    "balcony":  {"open": false, "locked": false, "mode": "auto"}
  },
  "lights": {
    "master": true, "dark": true,
    "rooms": {
      "living":   {"on": true,  "mode": "auto"},
      "kitchen":  {"on": false, "mode": "auto"},
      "bedroom":  {"on": false, "mode": "auto"},
      "bathroom": {"on": false, "mode": "auto"}
    }
  },
  "presence": "home",
  "coordinates": {"units": "cm", "frame": "unreal-world", "waypoint_height": "floor",
                  "transform_source": "documented-pivots"}
}
```

### Document fields

**`revision`**
- Increases by one each time the published content changes. That includes a change of `source.status`.
- It stays the same while the backend keeps sending identical state.
- `last_message_age_s` is not part of the comparison.

**`epoch`**
- Changes when the bridge restarts.
- When `epoch` changes, the client resets its `since`.

**`brain`**
- Published only while `status` is `live` and privacy is off.
- It contains exactly the backend's sleep stage and the home's current activity. The bridge never infers or invents it.

**`actor`**
- `node` is the last graph node the actor reached (`home.place`).
- `target` is the node of the current destination.
- `path` is the list of remaining waypoints. The current `HomeWorld.view()` does not publish its `path`, so the bridge re-derives it with the backend's own `home_world.route()`:
  - It starts from the edge that the walking position lies on, which covers a replan in the middle of an edge.
  - A test compares the result with `HomeWorld.path` on every tick of a long walk; it matches every time.
  - `path_source` is `derived-route-graph`. It becomes `backend` once the backend change below lands.
  - **Edge case:** within about 1 mm of a node, between two nearly collinear edges, the planned edge wins.
- `moving` is the backend's `walking` value.
- `seated` is the backend's seated progress, from 0 to 1.

**`destinations`**
- `next` and `final` are walking waypoints, with `mode: "walk"`.
- The field is only present while the state is live. A stale route is not something to act on.

**`doors`, `lights`, `presence`**
- Server-authoritative state from `home_interactions.py`, with the operator modes.

**No position field**
- The backend's `position`, `entry_position` and `look` are deliberately never published.
- The native pawn must walk to `destinations.next` with CharacterMovement. Nothing in the contract can move it instantly.
- The tests reject any key named `position`, `entry_position`, `look`, `location`, `teleport`, `set_position` or `transform`.

### Status: live, stale, unavailable

| `source.status` | When | Published |
|---|---|---|
| `live` | The socket is connected and the last `home` message is at most `stale-after` seconds old (default 3). | Everything. |
| `stale` | The socket dropped, or the feed has been quiet for longer than `stale-after` but not `unavailable-after`. Also a REST snapshot before the socket is connected. | Last known `actor`, `doors`, `lights`, `presence`. `brain` and `destinations` are null. The client should hold still. |
| `unavailable` | Nothing received yet, or quiet for longer than `unavailable-after` (default 15). | `privacy`, `actor`, `doors`, `lights`, `presence`, `brain` and `destinations` are all null. The client shows a disconnected state. |

A status change bumps `revision`, so a long-poll wakes up on it. The bridge re-checks status ageing every 0.5 s.

### Privacy (bathroom)

When the backend reports `privacy: true` (`HomeWorld.privacy()`), the document keeps only these:
- `schema`, `epoch`, `revision`, `source`, `coordinates`;
- `privacy: true`;
- `doors`, `lights` (with modes) and `presence`.

`brain`, `actor` and `destinations` are null. That means no activity, sleep stage, node, route or waypoint.

**Why the house fields stay:** they are physical house state. A visitor would see a closed, locked bathroom door and a lit bathroom anyway. Native rendering needs them to keep the door closed and the light correct. `privacy: true` already implies that someone is in the bathroom, so the door lock adds nothing identifying.

**Device fields are never forwarded.** That covers `devices`, phone, console, PC and screens, even outside privacy. Device content goes through the existing PC runner and device APIs and their own masking.

This is stricter than `GET /api/home`. During privacy that route still returns `home.activity`, `home.phone` and the position.

### Operator controls: `POST /home/controls`

- **Body:** `{"doors": {"front|bathroom|balcony": "auto|open|closed"}, "lights": {"living|kitchen|bedroom|bathroom": "auto|on|off"}}`. Each part is a partial patch, and the bridge validates it with `home_interactions.validate_modes`, exactly like the backend.
- **Rejected with 400:** any other key (`lamp`, `position`, …), an empty object, unknown names or unknown modes. Bodies over 4 KB get 413.
- **Accepted:** the patch is sent with the operator credential to `POST /api/home/settings`. The bridge answers `{"ok": true, "doors": {...modes}, "lights": {...modes}, "note": …}`.
- **Backend errors:**

  | Backend outcome | Bridge answer |
  |---|---|
  | Refuses the request | 502 `{"ok": false, "backend_status": N}` |
  | Unreachable | 503 |

- **Backend safety rules still apply.** For example, the backend will not open a door onto an occupied bathroom. The published state follows on the next tick. The bridge does not echo the new state optimistically.

## Coordinates

Waypoints use the existing `tools/unreal_home_coordinates.py`. The bridge imports `infer_import_transform` and `convert_position` and does not modify them.

**Conversion steps:**
- `home_world.NODES` are walking-eye points in metres. The bridge lowers each one by 1.65 m to the floor, then converts it.
- `floor_cm[2]` is the floor height: 0 on the ground floor and 300 upstairs.
- Compare it with the capsule bottom, which is the capsule centre minus its half height. In the route test the capsule centre is at 96/396.

**Default transform:** `infer_import_transform` re-verifies the transform from three pivots already documented in this repository:

| Pivot | Source (m) | Unreal (cm) | Where it is recorded |
|---|---|---|---|
| PC monitor screen centre | (2, 1.16, -3.276) | (200, -327.6, 116) | `tools/native_pc_bridge/README.md` |
| `stair_bottom` route checkpoint, floor level | (0.3, 0, 2.55) | (30, 255, 0) | `tools/unreal_native_route.py` |
| `bed` route checkpoint, floor level | (-1.2, 3, -2.9) | (-120, -290, 300) | `tools/unreal_native_route.py` |

- **Unique solution:** axes (0, 2, 1), signs (+, +, +) and zero offset, so `UE = (100·x, 100·z, 100·y)`.
- **Matches the native route:** a test checks that every native route checkpoint the native pawn reached produces matching waypoints. The checkpoints are `front`, `stair_approach`, `stair_bottom`, `stair_top`, `landing`, `loft` and `bed`.
- **The `door` checkpoint is not in that list.** The route test deliberately puts it at y = 310 cm. The node is at 320.
- **Replacing the default:** `--transform-file` accepts either `{"pairs": [[src_m, ue_cm], …]}`, which is re-verified, or the dict that `infer_import_transform` returns (`axes`, `signs`, `offset_cm`, `scale_cm_per_meter: 100`). The document's `coordinates.transform_source` says which one is in use.

## Proposed backend change (not applied)

The bridge must not edit backend files. One additive line would make `actor.path` authoritative instead of derived. In `home_world.py`, `HomeWorld.view()`, after `"destination": self.target,`:

```python
            "path": list(self.path),
```

Older pages ignore the new key. The bridge prefers it automatically and reports `path_source: "backend"`.

**Backend bug found (not fixed here).** Against the real local backend, `GET /api/home` answers 500 whenever the screens browser is off (no `--browse`). In `home_api.state()`, `screen()` checks `live.screen_status` but not `live.browser`, and `Live.screen_status` dereferences `self.browser.restarting`. A proposed fix, in `home_api.py` `state()`:

```python
        def screen(device):
            if not getattr(live, 'screen_status', None) or not getattr(live, 'browser', None):
                return None
```

The bridge tolerates the failed snapshot (it counts `snapshot_failures`) and follows the WebSocket `home` view, which carries the same state.

A second change is needed only if the gated password mode (`SITE_GATE=1`) is ever used privately. `/ws` and `/api/home` would then need the admin credential to pass the password gate. Today, in `live_server.password_gate`, only `ADMIN_PATHS` (`/api/costs`, `/api/health`) accept `X-Admin-Token`. Adding `"/ws"` and `"/api/home"` there would let the bridge through. In the default ungated local mode, nothing is needed.

## Proposed C++ integration hooks (proposals only, for Codex)

These are names only. Nothing below has been written or compiled. The component would follow the existing `Sub01PCBridge` pattern (HTTP, Json and JsonUtilities modules, credential from `SUB01_ADMIN_TOKEN`, never logged).

```cpp
// Source/Sub01HomeLab/Sub01HomeStateBridge.h  (proposed)
UCLASS(ClassGroup=(Sub01), meta=(BlueprintSpawnableComponent))
class USub01HomeStateBridge : public UActorComponent {
  // GET http://127.0.0.1:8811/home/state?since=<Revision>&wait=20, re-issued on completion
  void PollState();
  void OnStateResponse(FHttpRequestPtr, FHttpResponsePtr, bool bOk);
  // Applies one document; ignores revisions <= LastRevision within the same Epoch.
  void ApplyDocument(const TSharedPtr<FJsonObject>& Doc);
  // Door/light operator modes -> POST /home/controls (no optimistic local change).
  void RequestDoorMode(FName Door, FName Mode);        // front|bathroom|balcony, auto|open|closed
  void RequestLightMode(FName Room, FName Mode);       // living|kitchen|bedroom|bathroom, auto|on|off

  DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSourceStatus, FName, Status);   // live|stale|unavailable
  DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FPrivacy, bool, bActive);
  DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FDoor, FName, Door, bool, bOpen);
  DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FLight, FName, Room, bool, bOn);
  DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FRoute, const TArray<FVector>&, FloorWaypointsCm, FName, FinalNode);
  FString Epoch; int64 LastRevision = 0;
};
```

The character would hook these up as follows:

- **`ASub01HomeCharacter::FollowBackendRoute(const TArray<FVector>& FloorWaypointsCm)`**
  - Replaces `RouteTargets` in the existing route-test movement code: `AddMovementInput` toward the next XY, capsule bottom checked against `floor_cm.Z`.
  - It never calls `SetActorLocation` or `TeleportTo`.
  - Called only when `status == live`.
  - On `stale` it stops input (`StopMovementImmediately`); on `unavailable` it shows a disconnected overlay.
- **`ASub01HomeCharacter::OnBackendPrivacy(bool)`**
  - Forwards to the existing `USub01PCBridge::SetLocalPrivacy`.
  - Blanks device surfaces and hides the bathroom interior camera.
- **`ASub01HomeDoor::SetServerOpen(bool bOpen, bool bLocked)` and `ASub01HomeRoomLights::SetServerOn(FName Room, bool bOn)`**
  - Only animate what the server says. This mirrors `web/house/house_interactions.mjs`.
- **`ASub01HomeCharacter::OnBackendSeated(float Seated)`**
  - Drives the existing seated transition at the desk, sofa and bed.
  - Only once the pawn has physically arrived at the final node.
- **Writing the import transform:** the UE setup (`tools/unreal_setup_home.py`) would write its verified `infer_import_transform` result to a private JSON file, which the bridge loads with `--transform-file`. This is a proposal; that file is not edited here.

## Verified

`tests/test_unreal_home_state_bridge.py` has 16 tests, run against aiohttp fake backends with the real `HomeWorld` producing the views. They cover:
- live, stale and unavailable transitions;
- a REST snapshot alone not counting as live;
- reconnect with a fresh snapshot;
- monotonic revisions, unchanged when the state is unchanged;
- long-poll, both on a change and on timeout;
- privacy masking;
- auth on every route but `/healthz`;
- loopback, backend and credential refusal;
- coordinate conversion against the native route checkpoints and the monitor pivot;
- transform files;
- route derivation equal to `HomeWorld.path` on every tick, including mid-edge replans;
- no position or teleport keys;
- control validation and forwarding, with 502 and 503;
- the credential never appearing in documents;
- a failing REST snapshot still followed through the WebSocket.

**Live local smoke test (2026-10-13, CPU, loopback, scratch data dir, not committed).** Real `live_server.py` ran with `HOME_ENABLED=1` on 127.0.0.1:8797, and the bridge on 127.0.0.1:8812.
- An unauthenticated request got 403.
- The document was `live` with `brain {"stage": "NREM", "activity": "sleep"}` and the actor seated at `bed`.
- The revision stayed unchanged while he slept.
- `POST /home/controls {"lights": {"kitchen": "on"}}` was accepted by the real backend. A long-poll then returned the next revision with the kitchen light `{"on": true, "mode": "on"}`. It was reset to `auto` afterwards.
- After the backend was stopped, the document went `stale` (age 5.6 s, brain null, last-known actor). It then went `unavailable` at 15.1 s through a long-poll wake-up. Controls answered 503.

**Not verified:**
- Unreal, GPU and Runpod: no consumer exists yet.
- A gated (`SITE_GATE=1`) backend.
- Long-running reconnect behaviour against the full brain server under load.
