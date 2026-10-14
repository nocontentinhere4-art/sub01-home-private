# Proposed: level the native Tokyo backdrop and give it a night grade

Status: proposed patch for root to run. Nothing here has been run in Unreal, and
nothing here says how the result looks. The SimbasJungles reference
(https://x.com/SimbasJungles/status/2109095401273938072) was not viewed while
writing this. Root does the visual acceptance on the server (see "What root
checks").

Files (all new except one small change to our lighting module):

- `tools/exterior_backdrop_geometry.py`: pure Python. Holds the projection
  math with its HLSL twin, the PNG/WebP header reader and 2:1 check, the
  courtyard clearance check, the grade model, the preset and native-hour
  factors, and the proposed native hook diff.
- `tools/unreal_exterior_backdrop_fix.py`: the editor script. It validates
  first, then builds its owned assets, then makes one actor change. It is
  idempotent and has a `--restore` mode.
- `tests/test_exterior_backdrop_fix.py`: 57 tests that use a fake `unreal`.
- `tools/reference_home_lighting.py`: the day/sunset/night presets now write
  the time-of-day collection when the backdrop already uses the leveled
  instance. Without this change, a later lighting preset would put back the
  mesh-UV material. Its 24 tests still pass.

## Root cause (evidence at 85e2dd1)

### 1. Tilt

- `tools/unreal_home_exterior.py:80` contains
  `actor.set_actor_rotation(u.Rotator(0, -90, 0), False)`. In UE Python the
  positional order of `unreal.Rotator` is **(roll, pitch, yaw)**. This call is
  therefore **pitch −90°**, not the C++ `FRotator(0,-90,0)` yaw −90° it looks
  like. Everywhere else the repo uses keywords for this
  (`tools/reference_home_lighting.py`: `u.Rotator(roll=…, pitch=…, yaw=…)`;
  `tools/unreal_audit_seat_contact.py:39`: `u.Rotator(yaw=…)`). The test
  `test_root_cause_python_rotator_positional_is_pitch_and_tilts_the_sphere`
  shows that this rotator tips the sphere's local equator 90° off the
  horizontal. A yaw-only rotator leaves it at 0° for every yaw.
- `tools/unreal_home_exterior.py:43-50` (and the graded copy in
  `tools/reference_home_lighting.py:881`) samples the texture with the
  **mesh UVs** of `/Engine/BasicShapes/Sphere` (line 57). That mesh's UV
  layout was never measured as an equirectangular lat-long with its poles on
  +Z. Even with zero rotation, the photo's horizon is only level if those UVs
  happen to be lat-long with v = 0.5 at the equator.
- The image is not the problem. `web/house/assets/tokyo-residential/residential-4096.webp`
  has a VP8 header of **4096 × 2048 (2:1)**. The 2048 file is 2048 × 1024. Its
  manifest gives sha256 `4b9280a5…`. The capture is a true 360 × 180
  equirectangular panorama of "Memorial for Tokiwa-so apartment house"
  (Masato OHTA, CC BY 2.0): the downscaled image shows the full surround,
  stretched nadir and zenith, and a horizon around mid-height.
  `SourceAssets/TokyoResidential.png` is a lossless conversion of it and
  exists only on the server. The script checks that file's PNG header against
  the imported texture size.
- The sphere's position is already correct. Its centre is (0, 0, 165) cm
  (`unreal_home_exterior.py:60`), which is the eye height:
  `tools/unreal_setup_home.py:97` gives `eye_height_cm: 165`, and
  `tools/stage_unreal_home_runtime.py` puts the capsule half-height at 91 with
  the camera at +74. The radius is 2 km (line 78).

### 2. Bright at night

- **The native hour switch never touches the backdrop.** In
  `tools/unreal_native_view_settings.py:111-114`, `ApplyPrivateViewSettings`
  changes only the sun and the sky light. The backdrop is an unlit emissive
  photo, so at runtime it keeps the brightness it was saved with.
- **Auto-exposure lifts a dark unlit photo.** Our own night grade
  (`tools/reference_home_lighting.py:155`, brightness 0.05) is scene-referred.
  The night exposure clamp at line 123 (`min_ev100 -3`, `manual_bias 2.3`)
  lets the eye adapt to the dim lamp-lit room, which lifts the emissive
  backdrop back toward daytime brightness.
- **The grade depends on run order.** Re-running `unreal_home_exterior.py`
  respawns the actor with the ungraded `M_Sub01ActualTokyoBackground`, which
  is a constant-brightness photo.

## Chosen fix and why

**(a) Projection: a view-direction equirectangular lookup on a levelled sphere.**
The capture is a real 2:1 360° panorama, so a sphere is the right projection.
A cylindrical card or a window-view card would discard the real surround.

The owned material `M_Sub01TokyoBackdropLevel` ignores mesh UVs. A Custom
node computes UVs from `-CameraVectorWS`, the per-pixel view direction:

```
u = frac(0.5 + (atan2(d.y, d.x) - YawDegrees) / 360°)
v = HorizonV - asin(d.z) / 180°
```

- With `HorizonV = 0.5`, every horizontal view direction maps to the photo's
  horizon row, so the horizon is at eye height for every yaw. This does not
  depend on mesh UVs, actor rotation or where the visitor stands, because the
  photo is treated as being at infinity, as a distant backdrop should be.
- The actor is also levelled to (pitch 0, yaw 0, roll 0).
- `YawDegrees` defaults to 90°: the photo's centre column faces UE +Y, which
  is the measured entry/courtyard side. This is a tuning choice and can be
  changed on the material instance without recompiling.
- `PhotoPitchFix` and `PhotoRollFix` default to 0. They exist only in case
  root sees that the capture itself is not level.
- The texture is sampled at mip 0, so there is no derivative seam at the
  atan2 wrap. The 4096 capture has 11.4 texels/degree, which is magnified at
  the native 50–110° FOV.

**(b) Night.** Each of brightness, tint, desaturation and gamma is blended in
the material as `lerp(lerp(Night, Day, Daylight), Golden, GoldenWeight)`.
`Daylight` and `GoldenWeight` are scalars in the owned
`MPC_Sub01ExteriorTime`. The curve is the same as
`reference_home_lighting.exterior_grade`.

| Grade | Brightness | Tint | Desaturation | Gamma |
|---|---|---|---|---|
| Day | 1 | 1, 1, 1 | 0 | 1 |
| Golden | 0.6 | 1, .82, .62 | 0.1 | 1.1 |
| Night | 0.16 | .48, .58, 1 | 0.65 | 1.8 |

At night the photo is darkened (gamma crushes midtones before
highlights), desaturated and shifted blue.

When the engine has `MaterialExpressionEyeAdaptationInverse`, the result is
multiplied by it, so the grade is display-referred and night auto-exposure
cannot lift it. `--exposure-lock off` disables this.

There are no emissive window lights: the capture has no real emissive mask,
and invented city lights were ruled out.

The grade is tied to the existing switches in two places:

- The editor presets (`--preset day|morning|afternoon|sunset|night|auto`, the
  same names and solar model as `reference_home_lighting.py`) write the MPC
  defaults. `reference_home_lighting.py --apply --preset …` also writes only
  the MPC once the leveled instance is in place.
- For the runtime hour slider, root applies the proposed native hook
  described below.

**(c) Courtyard and sky compatibility.**

- The script reads every `SUB01_PrivateEntry_*` component's world bounds and
  refuses unless every corner is at least 10 m inside the measured sphere
  radius. Root's courtyard (`tools/unreal_extend_private_entry.py`) reaches
  about 9 m from the centre against a 2 km radius.
- It does not touch the actor's location, scale or collision (NoCollision is
  required, as `unreal_extend_private_entry.py` also requires), and it does
  not touch any SkyLight. `SUB01_ActualHDR_Sky` is only counted in the report,
  so it works before or after `unreal_remove_duplicate_private_sky.py`.
- The courtyard tool's own precondition (exactly one
  `SUB01_ActualHistoricalTokyoBackground` with NoCollision) still holds after
  this fix.

## Root commands

Run these on the private server with gameplay stopped, in the sole editor.
First a dry run, which works anywhere:

```
python3 tools/unreal_exterior_backdrop_fix.py --preset night
```

Apply, then quit:

```
UnrealEditor-Cmd <project>/Sub01HomeLab.uproject /Game/Sub01Home/ActualHome -ExecutePythonScript="<repo>/tools/unreal_exterior_backdrop_fix.py --apply --preset night --quit" -unattended -nosplash
```

From the already-open editor's Python console, the same apply is
`py "<repo>/tools/unreal_exterior_backdrop_fix.py" --apply --preset night`.

- Use `--preset afternoon` (or `day`, `sunset`) for the day capture. A preset
  re-run changes only the MPC.
- Use `--yaw <deg>` to rotate the photo.

Optional runtime hour hook. This is a diff to root's generator. It is
idempotent and anchored to exactly one line:

```
python3 tools/exterior_backdrop_geometry.py --native-hook-diff . | git apply
```

The hook adds two includes (`Kismet/KismetMaterialLibrary.h`,
`Materials/MaterialParameterCollection.h`). Inside `if(HasHour){…}` it sets
`Daylight` and `GoldenWeight` on `MPC_Sub01ExteriorTime` from the same hour
model. Applying it requires root's normal native rebuild.

## What root checks

Take screenshots at eye height (165 cm) in the native view at 90° FOV:

1. A day screenshot (`--preset afternoon`) facing the entry (+Y), plus two
   more at yaw +90° and +180° from it. In each, the photo's horizon (the base
   of the distant buildings and the street vanishing line) must be a straight
   horizontal line through the image's vertical centre at pitch 0. Utility
   poles and building edges must be vertical.
2. A night screenshot (`--preset night`, or hour 21 with the hook applied)
   from the same positions. Check that the backdrop is darker and bluer than
   the lamp-lit room and that it is not lifted to daytime brightness.
3. Turn through a full 360°. There should be no visible seam or a single-pixel
   line where the panorama wraps.
4. Stand in the courtyard at (200, 725). Its walls must occlude the photo's
   nadir, with no clipping.

If the panorama's horizon reads slightly tilted, that is the capture itself.
Set `PhotoRollFix` or `PhotoPitchFix` on `MI_Sub01TokyoBackdropLevel` in
degrees. Do not touch the actor's rotation.

`exterior-backdrop-fix.json` in the project directory records the prior
rotation and material, the image size, the courtyard clearance, the backup
path and `visual_match_claimed: false`.

## Rollback

1. Restore the pre-fix state:
   `-ExecutePythonScript="<repo>/tools/unreal_exterior_backdrop_fix.py --restore --quit"`.
   This puts back the rotation and material recorded in the report.
2. Alternatively, copy the map from
   `Saved/PrivateMapBackups/<ns>-backdrop-fix/` back to
   `Content/Sub01Home/ActualHome.umap`, including `__ExternalActors__` and
   `__ExternalObjects__` if they are present.
3. The owned assets under `/Game/Sub01Home/Environment/BackdropFix/` can stay;
   nothing references them after the restore. If the hook was applied,
   reverse it with `git apply -R` on the same diff.
