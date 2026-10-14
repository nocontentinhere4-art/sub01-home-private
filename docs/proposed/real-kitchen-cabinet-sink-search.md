# Real kitchen cabinet / sink / tap search: no genuine source found

> **Scope correction (2026-10-14).** This record's headline overstates its result. The search covered CC0 only, on a few sites, by API, on one day. It excluded CC-BY and royalty-free licences, which the owner accepts. CGTrader and TurboSquid were unchecked, and Smithsonian was not reached. The finding means only **"no free CC0 match found in this limited search"**. It does not mean that no genuine source exists. See `real-kitchen-local-source-gap.md` for the local-source record and the pending search plan.

**Outcome: (b) no genuine acquirable source.** I found no externally authored model that meets all four tests:

- CC0 (or an equally permissive licence),
- downloadable without a login or payment,
- realistic,
- fits the actual kitchen.

That applies to the lower cabinet run, the upper cabinet, the sink and the tap. Nothing is hidden or replaced. The procedural and Blender parts stay as they are. Machine-readable record: `real-kitchen-cabinet-sink-search.json`.

Web access: I used curl against public APIs only. No browser was used, personal or isolated, and nothing was installed or committed.

## Slots a replacement must fit (actual source)
| Slot | Exact geometry | Cite |
|---|---|---|
| Counter top | slab x -3.78..-0.62, z -3.88..-3.18, underside .8675, top **.9225** | home.js:663-673 |
| Sink opening | x -3.02..**-2.38**, z -3.70..-3.27; bowl .64 × .43 centred (-2.7, -3.485), floor .754, rim top ≈.936 | home.js:666-669, 722-729 |
| Tap | base (-2.7, .93, -3.79), top 1.24, spout end (-2.7, 1.16, -3.53) (reach .26); strip light bottom 1.6625 | home.js:730-739, 710-720 |
| Espresso edge | x -1.415 | packet:19 |
| Lower run | x -3.725..-0.675 (3.05 m), z -3.86..-3.1975, y 0..0.8675; fillers .10 L / .20 R; partitions x -2.95/-2.25/-1.55 | lower_kitchen_cabinet.mjs:31-48 |
| Lower doors | **4** leaves .65 × .76 × .035, centres x -3.3/-2.6/-1.9/-1.2, each **hinged on its left (-x) edge**, pivot (c-.325, .44, -3.192), open angle -0.49π | lower_kitchen_cabinet.mjs:2-6, 52-69 |
| Upper run | ours (Blender, `tools/build_home_upper_cabinet.py`), at (-2.2, 2.05, -3.71); fallback box 3.1 × .7 × .36; 4 doors via `cabinet_doors.mjs:31` | home.js:674-705 |

**Interaction constraint:**

- **Lower run.** A replacement must supply four separate door meshes, each .65 × .76 m and pivotable about its own left edge. Without that, `settings.lowerCabinets[4]` persistence, the door animation and the sweep-collision check all break.
- **Fused models.** A fused model, or one with doors merged into the carcass, cannot replace the interactive run. At most it could replace the static carcass behind the existing doors.
- **Upper run.** It must keep four door nodes for `attachUpperCabinetDoors` (`settings.cabinets[4]`).

Root's provenance inventory, `actual-source-prop-provenance-20261014.json` (origin/main c952a7f, added 25f5b4e), already marks both cabinet carcasses as `replacement_required`: the upper as `authored_by_us_Blender` and the lower as `authored_by_us_procedural`. It has no separate sink or tap entry. They sit with the `stone countertop` item ("sink_opening_and_device_support_preserved").

## Sources checked
| Source | Query / method | Licence | Result |
|---|---|---|---|
| **Poly Haven** | `api.polyhaven.com/assets?t=models` (521 models) and `/info/<id>`; matched name, tags and categories for kitchen, cabinet, cupboard, sink, tap, faucet, counter, basin and drawer | CC0 | No kitchen base or wall unit, sink or tap. **Confirms packet:82.** Cabinet hits are freestanding antique, vintage or rustic pieces (sizes in mm): GothicCabinet_01 1719×1129×2361, chinese_cabinet, chinese_commode, painted_wooden_cabinet(_02), vintage_cabinet_01 2022×670×2235, vintage_wooden_drawer_01, drawer_cabinet 1141×488×1881, modern_wooden_cabinet 2440×520×680 (a low sideboard, not four .65 doors). The "tap" tags are garden hose and plastic pipes. |
| **ambientCG** | `api/v2/full_json?type=3DModel&q=` sink, faucet, cabinet, kitchen | CC0 | 0 models. "kitchen" returns only tile and marble materials and food. |
| **Sketchfab** | `api/v3/search?licenses=cc0` with the queries kitchen sink, faucet, kitchen cabinet, base cabinet, kitchen tap, sink, cabinet, tap, kitchen, cupboard | CC0 filter (CC-BY excluded) | 0 CC0 sinks, faucets or kitchen cabinets. The CC0 "cabinet" hits are museum scans (a Smithsonian cabinet-door panel and the Augsburg table cabinet, c.1560). The CC0 "kitchen" hits are NewHorizonHomesInc whole-house photogrammetry (single fused meshes of 92k–493k faces), so they have no separable doors. Unfiltered kitchen-sink results are CC Attribution or Free Standard. All downloads need a login. |
| **Smithsonian Open Access** | `api.si.edu` with DEMO_KEY | CC0 | **Not reached** (OVER_RATE_LIMIT). The Sketchfab mirror shows only the cabinet-door panel. |
| **Kenney Furniture Kit** | kenney.nl/assets/furniture-kit | page says "Creative Commons CC0" | Rejected because it is stylised low-poly. The zip was not downloaded. |
| **Quaternius Ultimate House Interior** | quaternius.com/packs/ultimatehomeinterior.html | page says CC0: "…kitchen and bathroom furniture! … free to use in personal and commercial proj[ects]" | Rejected because it is stylised low-poly. |
| **BlenderKit** | `api/v1/search/?query=<q> asset_type:model license:cc_zero` with and without `is_free:true`; 12 queries (see JSON) | per-asset `cc_zero` in the API; downloads need an account, and `isFree=false` assets need a paid plan | **No free CC0 match.** The free-CC0 "sink" hit is a 3 × 3 × 1 m ground sinkhole. Paid CC0 **leads, not acquired**: *Kitchen Monobloc Mixer* by Strawberry (.291×.065×.425, 4189 faces, 10 objects, brushed steel; it would fit under the strip at 1.35 < 1.66); *Kitchen Basin Faucet* by Strawberry (vintage brass); *Chrome moen faucet* by Gabor BODOR (a brand replica); *Modern Flexible Faucet* (black and gold); *Cabinet set 005* by polimesh (5.56 m handleless composition, door separability unknown); *Kitchen unit* by Introspective Mnisi (3 m deep). |
| CGTrader / TurboSquid free | — | royalty-free EULAs, not CC0, login required | Not checked in time. |
| NASA / other government sources | — | — | Not checked; no plausible kitchen fixtures there. |

## Conclusion for root
- **Recording the gap.** Record the kitchen cabinets, sink and tap as having no genuine free CC0 source. The lower interactive run (`lower_kitchen_cabinet.mjs`), the Blender upper cabinet (home.js:674-705) and the procedural sink and tap (home.js:722-739) stay. Nothing should be hidden through the manifest.
- **What would close the gap.** The only realistic CC0-labelled candidates are paid BlenderKit taps; the Kitchen Monobloc Mixer fits best. Getting one needs a BlenderKit subscription and login, which is new spending outside the authorised compute budget and needs an explicit owner decision. Even then, the file would have to be downloaded, hashed (sha256), measured and checked for licence text before placement. None of that has been done here.
- **Placement convention**, if ever acquired: UE cm = (x, z, y) × 100 and UE yaw = −source yaw. The tap anchor would be source (-2.70, .9225, -3.79), which is UE (-270, -379, 92.25), with the spout aimed +z toward the bowl.
