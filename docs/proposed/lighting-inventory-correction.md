# Proposed: inventory-guarded lighting correction (`inventory-corrected`)

Status: source only, for root to run. Nothing here has been run in Unreal or rendered, and
nothing here says the result matches the SimbasJungles reference.

- Script: `tools/reference_lighting_inventory_correction.py`
- Tests: `tests/test_reference_lighting_inventory_correction.py` (they parse the real inventory)
- Input: `docs/proposed/actual-home-material-bindings-20261014.json` (root's read-only editor
  inventory)

`tools/reference_home_lighting.py` was changed by root's staged commit 6194250 and by the
backdrop fix (cd41ac8), so it was left alone. This new file owns the correction.

## 1. Measured lights (inventory) and diagnosis

| actor | class | intensity | stored FColor | `use_temperature` | authored (linear) CCT | rendered CCT | target |
|---|---|---|---|---|---|---|---|
| SUN | Directional | 3.09 lux | #ffd2a1 (255,210,161) | false (6500 ignored) | ≈5050 K | **≈3930 K** | 5500 K |
| DeskLamp | Point | 0 cd (off) | (255,168,82) | false | ≈3880 K | ≈2590 K | 2900 K |
| BedLamp | Point | 0 cd (off) | (255,147,65) | false | ≈3520 K | **≈2160 K** | 2700 K |
| KitchenWork | Point | 0 cd (off) | (255,194,124) | false | ≈4520 K | ≈3300 K | 3000 K |
| LowerPendant | Spot | 0 cd (off) | (255,184,111) | false | ≈4310 K | ≈3020 K | 2800 K |
| UpperPendant | Point | 0 cd (off) | (255,184,111) | false | ≈4310 K | ≈3020 K | 2800 K |

CCTs are McCamy estimates from Rec.709 chromaticity. They are approximate below about 2500 K.

The inventory does not record mobility, volumetric scattering, IES profile or source radius.
The authoring code (`tools/unreal_home_lights.py`) sets the lights Movable, uses no IES profile,
and leaves volumetric scattering and source radius at the engine defaults. Those defaults were
not measured.

### #ffead0 vs #ffd2a1 (sun colour discrepancy)

These are the same value seen at two layers, not two competing live colours.

- The source authors #ffead0 and converts it to linear (1, 0.823, 0.631).
- It then calls `set_light_color(linear, False)`. That stores the linear values as bytes:
  (255, 210, 161), i.e. #ffd2a1, which is what the inventory measured.
- UE treats a light's FColor as sRGB when it renders. So it decodes again to
  (1, 0.644, 0.356): the warm tint is applied twice.

The tests check this byte for byte: every stored colour equals `round(srgb_hex_linear(hex) × 255)`
of its authored hex. The engine decode step comes from UE's documented
`FLinearColor(FColor)` behaviour, and root should confirm it. The Details panel should show
SUN = FFD2A1.

**How far #ffd2a1 is from daylight:** about 3930 K. That is 1570–2570 K below the 5500–6500 K
daylight band, a late-golden-hour colour, applied at the 11:00 preview and at every runtime hour.
The intended #ffead0 (≈5050 K) was itself warm but plausible. The lamps render 2160–3300 K, so
the BedLamp is deeper amber than any warm-white lamp. The materials agent's predictions under
#ffd2a1 agree with this: greige ivory, mustard headboard, and caramel for `bed-balanced`.

### Is 3.09 lux plausible?

Not physically. Real direct sun is about 100 klux, roughly 32,000 times more. The authored scale
is relative (sun 3.2 lux at the zenith, HDR sky 0.4225), and in this level that scale is fine
only because auto exposure renormalises it. No PostProcessVolume exists, so the project
default (histogram) auto exposure applies. Its range is the project default, which was not
measured: in UE5 the extended-range default is very wide.

Exposure estimates (Lambert wall with albedo 0.7, EV100 = log2(L·100/12.5)):

| case | lux | EV100 |
|---|---|---|
| sunlit cream wall (3.09 lux) | 3.09 | +2.5 |
| sky-lit wall (~1/10) | 0.31 | −0.9 |
| deep interior (~1/50) | 0.06 | −3.2 |
| night wall 2.5 m from a 10 cd pendant | 1.6 | +1.5 |
| night desk at 1 m from 12 cd | 12 | +4.4 |
| real 100 klux sun (reference) | 100000 | +17.4 |

### Lamp/sun balance

The balance is inverted. The lamps use physical candela, while the sun and sky are about
1/30,000 of physical. A lamp-lit night wall (+1.5 EV) is brighter than a sky-lit day wall
(−0.9 EV). In a real home, a lamp-lit night room is about 2–3 EV darker than a daylit room.

Auto exposure hides this in pure day and pure night. It shows in mixed scenes, such as golden
hour with lamps on or the hour slider's transitions.

The fix is a single daylight scale of about ×30 on both sun and sky (about 4.9 EV), or lamps ×1/30.
Either belongs in the native hour/lamp code (`tools/unreal_native_view_settings.py`), which
rewrites intensities at runtime. Doing it in the editor would be overwritten, so this proposal
deliberately leaves intensities alone. It is root's decision and needs a native rebuild.

## 2. What `inventory-corrected` changes

**Lights: colour only.** `light_color` becomes white (255,255,255) and `use_temperature`
becomes true, at the target Kelvin in the table above. Intensity, units, mobility, transforms,
shadows and volumetric settings are not changed. The runtime switch never writes colour, so the
fix persists in play.

**`SUB01_ReferencePost`: owned, unbound, priority 0, weight 1.**

| setting | value | why |
|---|---|---|
| auto exposure method | histogram | engine default, set explicitly so the bounds apply |
| min / max EV100 | −3 / +3 | covers the computed interior range (−3.2 deep shade to +2.5 sun patch; night walls +1.5), so adaptation is stable when turning toward a window or into a dark corner |
| white_temp | **5500 K = sun key** | the sun key renders neutral, so a neutral ivory under the key reads neutral, as the materials agent recommends; warmth then comes only from the 2700–3000 K lamps and the golden presets |
| white_tint | 0 | no green/magenta shift |
| exposure bias | not overridden | keeps the current baseline brightness |
| speeds | not overridden | engine defaults |
| tone curve | not overridden | engine filmic defaults; changing the curve would move every material judgement |
| bloom, vignette, local exposure, Lumen | not overridden | Lumen GI and reflections are already set in `DefaultEngine.ini` |

Coordination with the backdrop fix: the backdrop is exposure-locked (`EyeAdaptationInverse`) when
the engine has that node. Whether exposure compensation is folded into that inverse was not
verified, so this preset sets no bias and cannot conflict either way. The EV100 bounds do not
change the backdrop's displayed level. With `--exposure-lock off`, the bounds would.

**Guards.**
- The level's light components must match the inventory exactly: the same six labels and
  classes, nothing extra, nothing missing, no duplicates.
- No PostProcessVolume other than `SUB01_ReferencePost` may exist, including the volume from
  `reference_home_lighting.py`, so the two presets cannot stack.
- Each light's current colour state must be the inventory state or the corrected state.
  `--allow-drift` overrides this after root has checked.
- The auto-exposure range must be in EV100 mode.
- Everything is checked before the first change.
- The map is backed up to `Saved/PrivateMapBackups/<ns>-lighting-inventory-correction/`.
- The original colours are kept across idempotent re-runs.
- `--restore` puts the exact bytes back and removes the volume if this script spawned it.

## 3. Order of operations

1. `tools/unreal_exterior_backdrop_fix.py --apply`
2. `tools/unreal_home_materials_fix.py --apply`
3. `tools/reference_lighting_inventory_correction.py --apply --preset inventory-corrected`

Judge the bed and sofa only after step 3, under the 5500 K key with 5500 K white balance.

## 4. Root commands

```
# dry run / diagnosis (anywhere)
python3 tools/reference_lighting_inventory_correction.py
python3 tools/reference_lighting_inventory_correction.py --shots
# apply (sole editor, gameplay stopped)
UnrealEditor-Cmd <project>/Sub01HomeLab.uproject /Game/Sub01Home/ActualHome \
  -ExecutePythonScript="<repo>/tools/reference_lighting_inventory_correction.py --apply --preset inventory-corrected --quit" -unattended -nosplash
# open editor console alternative
py "<repo>/tools/reference_lighting_inventory_correction.py" --apply --preset inventory-corrected
# rollback
UnrealEditor-Cmd <project>/Sub01HomeLab.uproject /Game/Sub01Home/ActualHome \
  -ExecutePythonScript="<repo>/tools/reference_lighting_inventory_correction.py --restore --quit" -unattended -nosplash
```

The report goes to `<project>/reference-lighting-inventory-correction.json`.

## 5. Before/after frames

Use the materials doc positions (`--shots` prints the rotations). Take each frame at the same
hour (the 11:00 authored preview) and the same FOV, with the lamps in the same state.

| shot | camera UE cm | rotation (pitch, yaw) | look for |
|---|---|---|---|
| bed close-up | (−100, −100, 420) | (−17.0, −131.2) | duvet ivory reads neutral or slightly warm, not greige or caramel; headboard distinct from the duvet |
| sofa | (−160, 10, 140) | (−21.8, 180) | upholstery hue vs the floor; no orange cast on the cream |
| desk + wood floor | (200, −75, 165) | (−21.8, −90) | sun patch on the oak: warm-white, not orange; oak keeps its brown |
| kitchen | (−180, −180, 165) | (−14.4, −103.2) | white cabinets near neutral; stainless steel not tinted |

Also take a night frame (lamps on via the runtime switch) at the bed and desk positions.

- Lamp pools should be amber-white (2700–3000 K), not deep orange.
- Exposure should stay steady while turning from the lamp to a dark corner.

Pass criteria: the mean hue of a neutral or ivory crop moves toward 40–60° with low saturation,
from the current strong orange shift. No visual-match claim is made without root's GPU frames.
