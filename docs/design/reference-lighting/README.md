# Reference lighting pass for the actual house

Module: `tools/reference_home_lighting.py` · tests: `tests/test_reference_home_lighting.py`.
Private, server-side Unreal editor pass on `/Game/Sub01Home/ActualHome`. Nothing here deploys,
renders or touches the runtime generators.

## Reference access (honesty note)

- Primary reference `x.com/SimbasJungles/status/2109095401273938072`: the x.com page itself needs
  JavaScript/login. Its public syndication metadata, the 1918x1080 poster frame and the 39.75 s
  720p video *were* fetched and viewed as stills (a 16-frame contact sheet). Seen: warm cream walls,
  low golden sun with soft-edged plant shadows on the wall, bright sheer-curtained window, wood
  floor, subtle bloom/vignette, visible floating dust specks in the sunbeam, and an in-game HUD with
  four modes: *Manhã / Tarde / Pôr do sol / Noite* (morning, afternoon, sunset, night), per-lamp
  toggle (E) and all-lights (L).
- Process article `x.com/SimbasJungles/status/2109295930021208144` links to an X Article
  ("How I modeled my entire Airbnb with Opus 5.5"). Only its title, preview sentence and cover
  image were reachable to this author; the article body was **not** read here. The coordinator
  reports having viewed the full article, which describes fixing UE's far default fog start with a
  LOCAL near-camera fog; the local fog volume below follows that report. No numeric value is
  copied from the article.
- No render of the SUB-01 house with this pass has been made or viewed. It is not claimed to match
  the reference.

## Presets

`apply(preset, when=None)`; presets `auto` (exact instant, default now), `morning` 07:30,
`day` 12:00, `afternoon` 15:00, `sunset` (computed sunset − 25 min), `night` 21:30 — JST, on the
date of `when`. `day_night_preset(is_night)` gives `night` / `afternoon`.

| Phase | Sun | Sky (HDR SkyLight) | Lamps | Exposure (histogram, EV100) |
|---|---|---|---|---|
| day (el ≥ 10°) | on, lux and K by elevation | 0.4225 (authored) | off | −2…+2, bias +0.5 |
| golden (0–10°) | on, 3000–3900 K | fading | Desk, KitchenWork, LowerPendant | −2.5…+1.5, bias +0.3 |
| night (el < 0 or `night`) | off (intensity 0, hidden) | 0.02, blue tint | all on | −3…+1, bias 0 |

Manual exposure alternative: `--exposure manual` (bias 2.0 / 2.0 / 2.3, physical camera exposure
off) — unverified guess.

## Values and sources

- **Solar position**: NOAA solar calculator equations (Meeus, *Astronomical Algorithms*), NOAA
  refraction approximation; sunrise/sunset at geometric −0.833°. Tokyo 35.68 N 139.69 E, JST.
  Checks: 2026-03-20 05:45/17:52, 2026-06-21 04:25/19:00, 2026-12-21 06:46/16:31 (published
  Tokyo times 05:45/17:53, 04:25/19:00, 06:47/16:32); equinox noon elevation 54.1° = 90 − 35.68 + δ.
- **Sun lux**: repository authored scale (tools/unreal_home_lights.py, web/house/lighting.mjs),
  3.2 lux at zenith, no Cycles 683 factor, shaped by Meinel clear-sky DNI with Kasten–Young air
  mass (≈2.6 lux at 30°, 0.7 lux at 4°). Keeps the authored balance with the 0.4225 HDR sky and
  candela lamps. A physical 100 klux sun would need re-scaling the HDR and lamps together.
- **Sun colour temperature**: 3000 K at horizon → 3900 K at 10° → 5100 K at 30° → 5700 K at 50°
  → 6000 K at 90° (monotonic table; sunlight CCT literature range). Colour set to white so the
  temperature is not doubled by the authored sRGB tint.
- **Sun softness**: source angle 0.8° (disc is 0.53°; extra softness for sheer curtains), contact
  shadows 0.05 screen, volumetric scattering 0.6 (modest, so shafts stay subtle) with volumetric
  shadow.
- **Lamps** (kept Movable, authored candela from `authored_lights`): Desk 12 cd 2900 K r 4 cm;
  Bed 3.5 cd 2700 K r 6 cm; KitchenWork 2.4 cd 3000 K r 3 cm; LowerPendant (spot) 10 cd 2800 K
  r 8 cm; UpperPendant 10 cd 2800 K r 10 cm. Contact shadows 0.03, volumetric scattering 0.2,
  no volumetric shadow (cost). `set_lamps({...})` toggles individually.
- **Post process** (owned unbound volume `SUB01_ReferenceLighting_PostProcess`, priority 10):
  Lumen GI + Lumen reflections, final gather quality 1.5, reflection quality 1.0 (default, not
  raised), surface-cache ray lighting, max roughness to trace 0.4, no front-layer translucency
  reflections, skylight leaking 0, max trace 20 m, white balance 6500 K, bloom 0.4,
  vignette 0.3, local exposure contrast 0.85/0.95 by day. Software Lumen with screen traces is
  assumed from engine defaults (`r.Lumen.HardwareRayTracing 0`); the project ini already sets
  Lumen GI/reflections and VSM.
- **Ground-floor footprint** (source metres, from the `web/house/home.js` shell): 8 x 8 m house,
  outer walls at ±4 m, 0.18 m thick → interior x, z ∈ [−3.91, 3.91]; air y ∈ [0, 2.85] below the
  upper floor (~3.05). First-person camera (2, 1.65, 3.1). Room diagonal ≈ 11.4 m.
- **Global height fog**, kept subtle (reuses the single existing fog, else spawns
  `SUB01_ReferenceLighting_HeightFog` at the source origin): density 0.005, falloff 0.2, analytic
  start 6 m, max opacity 0.15. Volumetric fog on, starting at 0 cm with a 14 m view distance
  (just covers the house, keeps froxels dense), extinction scale 0.4, scattering distribution 0.6,
  albedo (240, 232, 218).
- **Local near-camera fog** (`SUB01_ReferenceLighting_LocalFog`, UE LocalFogVolume): ellipsoid
  centred at source (2.0, 1.45, 1.0) with semi-axes (1.7, 1.35, 2.6) m → bounds x 0.3–3.7,
  y 0.1–2.8, z −1.6–3.6, inside the footprint and containing the first-person camera. Radial
  extinction 0.03 /m (peak optical depth ≈ 0.16), height extinction 0, phase g 0.6, albedo
  (0.96, 0.93, 0.87), no emissive. The engine's unit sphere radius is measured from the actor's
  bounds at apply time (fallback 500 cm, unverified) before scaling.
- **Tokyo exterior at night**: the authored backdrop `SUB01_ActualHistoricalTokyoBackground`
  (unlit emissive photo from `tools/unreal_home_exterior.py`) gets an owned material
  `M_Sub01ReferenceTokyoBackgroundGraded` / `MI_..` (same texture → desaturate → × tint ×
  brightness → emissive). Day: brightness 1, neutral. Golden: ≈0.6, warm (1, 0.82, 0.62). Night:
  0.05, blue (0.45, 0.55, 1.0), 60 % desaturated. The original material is not edited; its path
  is recorded in the report so it can be restored.
- **Dust**: no Unreal particle/Niagara dust asset exists in this repository (the three.js
  `web/house/sun_dust.mjs` is not a UE asset), so no dust is added. The server project's Content
  was not inspected.

## Orientation assumption

No consistent geographic north exists in the repo: `web/house/lighting.mjs` rises the sun at
source −X and sets it at +X with noon at +Z (mirror-handed), while `web/house/home.js` calls
(−12, 10, 14) its afternoon sun. The module takes `north_source_xz` (glTF x, z), default (0, −1):
north −Z, east +X, south +Z. Directions are mapped to UE with the verified import transform in
`<project>/unreal-home-setup.json`. If the real plan's north differs, pass `--north x,z`.

## Safety

`apply()` first validates: each of the six `SUB01_AuthoredLight_*` labels exactly once with the
right component class, at most one sky/owned PPV/height fog, every property name present, the
coordinates file, and that auto-exposure is in EV100 mode. Any problem raises
`LightingValidationError` before a single mutation. Lights are never deleted or spawned.
Re-running `unreal_setup_home.py` re-creates the authored lights and discards this pass; re-apply
afterwards. The report goes to `<project>/reference-home-lighting.json` (runtime data, not Git).
