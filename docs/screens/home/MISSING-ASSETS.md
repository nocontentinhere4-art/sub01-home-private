# Missing house assets

Checked on the merged branch (`claude/happy-einstein-1x0561` merged into this worktree).
`web/house/home.js` and the house modules reference 121 unique asset URLs across the full
and lite variants. A page load uses one variant (lite on narrow or coarse-pointer screens).
Every URL resolves on disk and in git except the eight bathroom files below. Those eight are
not tracked by git, not gitignored and not on disk in this repository. Copies may exist on
the owner's pod volume; this check did not inspect it.

## Requested by the page (optional)

| Files under `web/house/assets/` | Manifest entry (`optional-manifest.json`) | Code reference (`web/house/home.js`) | Builder |
| --- | --- | --- | --- |
| `bath-door-original/bath-door.glb`, `bath-door.json` | `bath-door` | `bathDoorReady` through `optionalAssets.get('bath-door')` | `tools/build_home_bath_door.py` |
| `bath-fixtures-original/toilet.glb`, `toilet.json` | `toilet` | `bathFixturesReady` through `optionalAssets.get(name)`, `BATH_FALLBACK_CALLS.toilet` | `tools/build_home_bath_fixtures.py` |
| `bath-fixtures-original/vanity.glb`, `vanity.json` | `vanity` | `bathFixturesReady`, `BATH_FALLBACK_CALLS.vanity` | `tools/build_home_bath_fixtures.py` |
| `bath-light-original/bath-light.glb`, `bath-light.json` | `bath-light` | `bathLightReady` through `optionalAssets.get('bath-light')` | `tools/build_home_bath_light.py` |

Before this change, each fixture fetched its JSON and GLB in parallel, so a headless load
produced eight 404s. The loader now requests the GLB first and skips the sidecar when the
GLB is missing, so there are four 404s, one per file, and no retries.

When a file is missing, the room keeps its placeholder:

- Toilet and vanity: the procedural primitives listed in `BATH_FALLBACK_CALLS` stay visible.
- Bathroom door: the darkwood door slab stays visible.
- Bathroom light: no ceiling fitting and no bathroom point light.

Each missing file logs one `console.warn`. The House panel shows one line:
`4 fixtures missing: bathroom door, toilet, vanity, bathroom light`. The status element
also records `dataset.optionalAssets` as JSON.

## Referenced by committed JSON, not loaded by the page

| Missing file | Referenced from | Field |
| --- | --- | --- |
| `lighting/components/indirect/bake.json` | `lighting/indirect-bake.json` | `day_components[0].manifest_file` |
| `lighting/components/indirect/indirect.exr` | `lighting/indirect-bake.json` | `day_components[0].raw_file` |
| `lighting/components/sky-direct/bake.json` | `lighting/indirect-bake.json` | `day_components[1].manifest_file` |
| `lighting/components/sky-direct/indirect.exr` | `lighting/indirect-bake.json` | `day_components[1].raw_file` |
| `real-linea140/20261014-linea140-inventory.json` | `real-linea140/provenance.json` | `actual_inventory_receipt` |
| `real-steel-shelf/20261014-steel-frame-shelf-inventory.json` | `real-steel-shelf/provenance.json` | `actual_inventory_receipt` |

The page reads `indirect-bake.json` for its own fields. It never opens the four bake
components, so the lighting bake still loads without them.

## Keeping this list honest

`tests/test_home_asset_audit.py` checks every file reference in the house asset JSON and
every literal `/house/assets/` or `/room/` path in the house modules against `git ls-files`.
The allowlist `KNOWN_MISSING` holds exactly the 14 entries above. The test fails on any
new untracked reference and on any allowlisted entry that becomes tracked, so the list can
only shrink.

To restore the bathroom set, rebuild the files with the builders above on the GPU pod, or
copy them into `web/house/assets/`, then `git add` them and remove their eight lines from
`KNOWN_MISSING`.
