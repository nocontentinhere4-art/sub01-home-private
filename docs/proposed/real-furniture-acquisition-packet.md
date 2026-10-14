# Real furniture acquisition packet: office shelves and kitchen (root runbook)

Status: proposed and source-only. Nothing has been imported, rendered or placed. No visual match to the SimbasJungles reference is claimed. The machine-readable copy is `real-furniture-acquisition-packet.json`, which holds every URL, md5, sha256, bound and citation. `tests/test_real_furniture_packet.py` checks it.

Out of scope: the desk. The texture agent is handling LINEA 140 (Innerscene). The approved stairs and chair stay as they are.

## How this was sourced
- **Web access.** The Poly Haven public API (`api.polyhaven.com/assets?t=models`, `/info/<id>`, `/files/<id>`) and `dl.polyhaven.org` worked through curl. No browser was used, personal or isolated.
- **Downloads.** The 1k glTF sets were downloaded to session scratch only. Every file's md5 equals the API value, sha256 was computed locally, and nothing is committed.
- **Bounds.** Measured from the glTF POSITION data with node transforms. The API `dimensions` field matches every measurement.
- **Licence.** CC0. The source is https://polyhaven.com/license: *"Our assets are all licensed as CC0, which is effectively Public Domain"*.
- **Commit `25f5b4e`.** It does not exist here: it is not on `origin/main` (after fetch) and not in `git log --all`. I used the repo provenance in `web/house/assets/manifest.json` and `web/house/assets/*/provenance.json` instead.

## Slots (source metres, Y up)
| Slot | Limits | Citations |
|---|---|---|
| Office shelf wall | x 0.80..3.91; back z -3.8775 (baseboard face); front limit z -3.50 (desk back), so **max depth .3775**; height < 2.85 under the art | home.js:406, 489, 490-496, 407, 781, 877; build_home_office_desk.py:61 |
| Kitchen table area | x -3.91..-0.20 (stair), z -2.28..-0.76. This keeps a 0.9 m aisle in front of the counter (front z -3.18; lower-door swing reaches about -2.54). Exclusions are the sofa (x -2.435..-1.165, z ≥ -1.31) and the coffee table (z ≥ -0.76), both with the obstacle() padding of 0.16 m | home.js:663-672, 549-550, 409, 442, 1362; lower_kitchen_cabinet.mjs:2-5 |
| Counter top | y .9225; x -2.38 (sink edge)..-1.415 (espresso); z -3.88..-3.18 | home.js:663-672, 740-745 |

## Chosen assets
UE cm = (x, z, y) × 100, and UE yaw = −source yaw. The contract is `tools/build_real_lamps.py:168-193`; Unreal re-verifies it with `infer_import_transform`.

| Asset | Authors / polys | Measured size W×D×H (m) | Placement source (m), yaw | UE cm, yaw | Clearance |
|---|---|---|---|---|---|
| `wooden_display_shelves_01` ×2 ([page](https://polyhaven.com/a/wooden_display_shelves_01)) | James Ray Cock / 3174 | 1.0778 × .3715 × 1.5566 (width on glTF Z) | (1.5861, 0, -3.6918) and (2.6639, 0, -3.6918), yaw −90° | (158.61, -369.18, 0) and (266.39, -369.18, 0), yaw 90 | **6 mm** to desk back; .194 spare in 2.35 span; 1.29 under art |
| `round_wooden_table_02` ([page](https://polyhaven.com/a/round_wooden_table_02)) | Ulan Cabanilla / 4254 | .7962 Ø × .746 | (-2.90, 0, -1.60), 0° | (-290, -160, 0), 0 | 1.18 to counter, .23 to sofa, .60 to coffee table |
| `dining_chair_02` ×2 ([page](https://polyhaven.com/a/dining_chair_02)) | James Ray Cock / 22013 | .4336 × .5764 × .9747 (front = +Z) | W (-3.4434, 0, -1.60) yaw +90°; E (-2.3566, 0, -1.60) yaw −90° | (-344.34, -160, 0) yaw −90; (-235.66, -160, 0) yaw 90 | W back .046 to window frame; .10 seat tuck; E .23 to sofa |
| `wooden_cutting_board` ([page](https://polyhaven.com/a/wooden_cutting_board)) | Kuutti Siitonen / 3520 | .4499 × .2467 × .0413 | (-1.90, .9225, -3.62), 0° | (-190, -362, 92.25), 0 | .256 to sink, .259 to espresso |

Shelf measurements:
- No back panel: the cubbies are open front and back.
- Board tops are at .038, .414, .790, 1.165 and 1.542 (pitch .376).
- There are 3 columns of about .326 clear.
- The three bins are separate nodes, `_drawer_01..03`.

## Acquisition (root, server only)
Download each file from the URL in `assets[].files[]` into `target_dir` + `path`, then check its sha256. Example for one asset; the other three follow the same pattern from the JSON:
```sh
D=/workspace/sub01-home-private/reviewed-furniture/wooden_display_shelves_01; mkdir -p $D/textures
B=https://dl.polyhaven.org/file/ph-assets/Models
curl -fL -o $D/wooden_display_shelves_01_1k.gltf $B/gltf/1k/wooden_display_shelves_01/wooden_display_shelves_01_1k.gltf
curl -fL -o $D/wooden_display_shelves_01.bin     $B/gltf/8k/wooden_display_shelves_01/wooden_display_shelves_01.bin
for m in diff arm nor_gl; do curl -fL -o $D/textures/wooden_display_shelves_01_${m}_1k.jpg $B/jpg/1k/wooden_display_shelves_01/wooden_display_shelves_01_${m}_1k.jpg; done
( cd $D && sha256sum -c <<'S'
3784953c451b088d24ac1b0e6946c7f7bd589115f51e6549fdb8fe9f7c10600e  wooden_display_shelves_01_1k.gltf
e6c000a780626e618c1f1c0c1ec2ec29e1452e7824055ba53b40963d857edfbe  wooden_display_shelves_01.bin
cb57e90d9588ce81e58ff7300e89956a6a3c45119165b858d921a5a2439cbeaf  textures/wooden_display_shelves_01_diff_1k.jpg
33d6b769eafab3b1d8605b202cd41b0994b8c43df02dca5bdd86e942e390ff6a  textures/wooden_display_shelves_01_arm_1k.jpg
04191c25bfb8e76314863b624233807792df64fa1a638c75d20788becb4cbb8c  textures/wooden_display_shelves_01_nor_gl_1k.jpg
S
)
```
The `.bin` is served from the 8k/4k folder because Poly Haven shares one binary across resolutions. That is the URL the `/files` API returns.

## What gets replaced (hide via manifest; never destroy)
**Office shelves** are replaced. The targets:
- the `shelfFallback` boxes at home.js:855-861;
- the cube-built `house-office-shelves-*` nodes from `tools/build_home_office_shelves.py`, loaded at home.js:862-876 (oak boards, cleats, `Shelf_hardware`).

Shared-batch risk:
- Those nodes use `M.architectureOak`, the same material as the stair treads (home.js:502).
- If the UE source GLB merged any of them into a shared batch (`batchArchitecture`, home.js:2766), select **exact connected components** the way `tools/build_real_shelf_books.py` / `tools/build_real_lamps.py` do. Refuse on ambiguity, and never hide a node that also carries stair geometry.

**Kitchen** items are additive; no procedural object is replaced:
- Add colliders `obstacle(-2.90,-1.60,.80,.80)` and the two chair footprints from the JSON.

## Builder note
Follow `tools/build_real_lamps.py` (identify, place, then hide manifest plus `provenance.json`) and `tools/unreal_import_real_lamps.py`. For the shelf, that means:
- a `tools/build_real_furniture.py` that loads each reviewed glTF;
- refuse if the sha256 or the measured bounds differ by more than 1 mm from the JSON;
- place each asset per `placements[]`;
- emit `original-hide-manifest.json` for the shelf nodes and `provenance.json` (CC0, page URL, authors).

## Sequencing risks (read before importing)
1. **Desk clearance is only 6 mm.** It is measured against the current 2.4 × .8 desk. Re-check it against the measured LINEA 140 footprint. If that desk is narrower, place one unit beside it, using an x taken from the measured desk edge rather than a guess.
2. **Books.** `real-shelf-books.md` targets the old board tops at 2.0675 and 2.5175, which disappear in this swap. Re-target the books to the 1.165 cubby row and the 1.542 top before swapping.
3. **Hidden lower rows.** The rows at .038, .414 and .790 sit behind the desktop (.845).
4. **Chair tuck.** The .10 m tuck assumes knee room around the table pedestal. Verify it after import.

## Gaps (honest)
- **Kitchen cabinets, sink, tap.** Poly Haven has no CC0 base or wall cabinets, sink or tap (all 521 models were searched for kitchen, cabinet, cupboard, sink, faucet, tap, counter, hood, fridge and oven). The interactive lower cabinet (`lower_kitchen_cabinet.mjs`) and the Blender upper cabinet (home.js:675-705) therefore stay until a genuine CC0 source is found.
- **ambientCG.** Its API listed only materials and HDRIs, so it is not a source for these items.

## Rejected
| Asset | Reason |
|---|---|
| steel_frame_shelves_01 / 02 | .502 deep > .3775 |
| steel_frame_shelves_03 | .721 deep |
| drawer_cabinet | .488 deep |
| wooden_bookshelf_worn | .581 deep, worn |
| modern_wooden_cabinet | .52 deep, low sideboard |
| Shelf_01 | Fits, but weathered and distressed |
| painted_wooden_shelves | Fits, but worn farmhouse and too small |
| round_wooden_table_01 | 1.40 Ø, no chair room |
| wooden_table_02 | No end-chair room |
| coffee_table_round_01 | Coffee height |
| gallinera_table / chair | Antique carved |
| painted_wooden_chair_01 | Distressed |
| bar_chair_round_01, metal_stool_01 / 03 | No counter overhang; vintage or rusted |
| electric_stove | Worn vintage; would cut the 4-bay interactive run |
