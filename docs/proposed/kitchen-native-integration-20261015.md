# Authentic kitchen: next-window source and native integration

The previous actual source pass is commit `7ff55b9`, GLB SHA256 `687d9c6d9bdaca124d59dc55047783b223c3ae6fb8bfaed1d20dfd89e2961d2a`. It proves the sink cut, 16 rigid feet and eight door-to-carcass opening sweeps. It does **not** prove retained-house or independent door-to-door clearance. The new importer intentionally rejects that earlier receipt.

The new code is source preparation only. No October 15 Blender, Unreal import, native compile or interaction acceptance has run. The expired October 14 deadline grants no additional server time. The renderer must authenticate the next approved window and hold the sole Blender/Editor lease before executing these steps.

## One source job

Use official Blender 4.5.3 on the verified target, UID1001, nice19, isolated source CPUs and a **maximum120second** job with guard checks before and after. Keep the frozen office files unchanged. The asset root must be a fresh owned `/workspace/...` directory containing the packaged `tools` and `web/house/assets` files. Output must be fresh/empty. The helper has a110second internal budget, atomic `source-progress.json` phase/door/pair receipts and45second stack dumps; a bounded refusal should be profiled rather than blindly retried.

```text
blender -t 2 -b --factory-startup --python-exit-code 2 \
  --python <asset-root>/tools/prepare_real_kitchen_native_bundle.py -- \
  --root <asset-root> --home <actual-955-full-home.glb> --output <owned-output>
```

The job retains the reviewed sink/feet/eight-door checks, then checks every static part and 720 door poses against the actual retained source triangles. It skips only retired cabinet nodes63/178. Only measured floor-top/counter-underside coplanar contact faces receive a 1µm floating-point contact bound; sink, wall and other geometry have no exemption. First, an analytic whole-arc AABB checks each door pair, including between-endpoint extrema. Proven disjoint pairs reject all8100 configurations without a triangle call. Remaining pairs use cached per-pose AABBs before exact epsilon-zero BVHs. All28 pairs/90×90 configurations are accounted for. All proposed vertices must remain inside the audited house region. A failure prevents `native-kitchen.json` generation and must be solved physically.

Success produces `native-kitchen.glb` and `native-kitchen.json`. All16 assemblies and152 authored parts remain present. All node, scene and mesh names receive a deterministic unique prefix; this JSON-only rename must leave the complete GLB BIN bytes, geometry attributes and embedded PBR unchanged. Positions, triangle counts, eight original hinge pivots and five moving parts per hinge are recorded from the actual exported bytes. Identified feet and door pulls retain their reviewed rigid sizes; the reviewed fitted body/panel geometry remains explicitly derived rather than original manufacturer sizing.

## One closed-pose native transaction

In the sole already-loaded warm ActualHome Editor:

```python
import importlib, unreal_import_real_kitchen
importlib.reload(unreal_import_real_kitchen)
unreal_import_real_kitchen.run(output_root, dry_run=True)
# After successful actual preflight, same sole Editor:
unreal_import_real_kitchen.run(output_root, dry_run=False)
```

The importer checks the current native countertop65, strip66 and sink164 against their actual source triangle positions, independent of vertex/index order. It stages a unique owned version, validates152 native world-space part bounds/counts and the actual primitive-to-material slots, and fixes texture roles only on new owned textures. Door hardware uses the exact source material-slot binding; `Material_0`/`Material_0.001` are not resolved by a global substring search.

Eight closed five-part hinge assemblies receive exact digest-bound component tags and non-simulating movable simple box collision. Static bodies retain triangle collision. Only exact original cabinet meshes63/Mesh47 and178/Mesh135 are hidden and made NoCollision, after all staged checks pass. Every other original mesh, transform, material, tag, visibility and light intensity remains protected. Map/external-actor backups precede staging; failures restore original actors/components and remove only the newly owned import. The receipt records interactions and visual acceptance as false.

First inspect the actual kitchen from the room and close up at the sink/door edges. This closed-pose visual import does not require a character rebuild or bridge change. Do not block the first real house view waiting for optional interaction compilation.

## Optional later functional activation

`unreal_kitchen_hinge_runtime.install(header, cpp, actual_manifest)` supplies reviewable character source hooks. It is off unless `SUB01_KITCHEN_RUNTIME=1`. It requires exactly40 digest-bound native parts at their measured closed bounds. Backend origin must be authenticated loopback `127.0.0.1:8821` with the existing admin token; no token is printed or embedded.

The small `unreal_kitchen_state_bridge.install(source_text)` adapter extends only cabinet controls and published cabinet state. It preserves existing door/light validation, forwards exactly four booleans per existing backend setting, and exposes no fabricated closed state when unavailable, stale, malformed or private. The native adapter reads the published accepted state before moving; manual E requests the opposite setting and never asserts backend success locally.

Movement is bounded to0..88.2° at70°/s and0.25° substeps, including a sagitta-enclosed swept box for every part. All five parts are tested before any is moved that tick. Only that hinge's own five components are ignored; the pawn, other doors and all room collision remain active. A blocker stops motion with an actual component/angle diagnostic. The build and actual blocked/open/close/input/state/privacy checks remain pending; policy tests are not Unreal acceptance.

## Lightweight validation

```text
out/server-api-client/bin/python -m unittest discover -s tests -p test_real_kitchen_native.py -v
```

Seven tests exercise old-receipt refusal, missing/changed part/hinge guards, narrowly allowed contact planes, retained native shape comparison, between-endpoint swept bounds, the actual patched bridge's live/stale/private behavior and C++ motion-policy execution through intermediate obstacles. Full UE compilation and the next-window source job are additional required evidence.
