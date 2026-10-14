"""Pure geometry, image and grade model for the leveled Tokyo exterior backdrop.

No ``unreal`` import. Used by tools/unreal_exterior_backdrop_fix.py (editor
script), by tools/reference_home_lighting.py (preset switch) and by tests.

Projection (replaces the mesh-UV lookup of tools/unreal_home_exterior.py):
the owned material ignores the Engine sphere's UVs and the actor rotation and
computes equirectangular UVs from the per-pixel VIEW direction
(-CameraVectorWS). The photo is therefore treated as being at infinity around
the viewer: its horizon row (v = HorizonV, 0.5 for a level 2:1 capture) is
always the true horizontal through the camera, i.e. exactly at eye height
(165 cm, tools/unreal_setup_home.py ``eye_height_cm``), for every yaw and
wherever the visitor walks. A mesh rotation can no longer tilt it.

UE world frame: X forward, Y right, Z up (left-handed); azimuth 0 deg = +X,
+90 deg = +Y (turning right increases azimuth). Panorama convention (standard,
non-mirrored equirectangular, UE texture v = 0 at the top row):
  u = frac(0.5 + (azimuth - YawDegrees) / 360)     photo centre column faces YawDegrees
  v = HorizonV - elevation / 180                   zenith v = 0, horizon v = 0.5, nadir v = 1
Optional PhotoPitchFix / PhotoRollFix (deg) rotate the view direction before
the lookup, for a capture that is itself not level; both default to 0.
"""
import difflib
import math
import struct
from pathlib import Path

EYE_HEIGHT_CM = 165.0          # tools/unreal_setup_home.py:97, capsule 91 + camera 74
BACKDROP_CENTER_CM = (0.0, 0.0, EYE_HEIGHT_CM)  # tools/unreal_home_exterior.py:60
BACKDROP_RADIUS_CM = 200000.0  # tools/unreal_home_exterior.py:78 (kept)
COURTYARD_MARGIN_CM = 1000.0   # finite courtyard must stay this far inside the sphere
# Default yaw: photo centre column (the memorial plaza and street) faces UE +Y,
# the measured entry/courtyard side (tools/unreal_extend_private_entry.py: the
# courtyard extends the landing from y 580 to 870 cm). A tuning value only;
# root may change it on the material instance without recompiling.
DEFAULT_YAW_DEG = 90.0
HORIZON_V = 0.5
LUMA = (0.3, 0.59, 0.11)       # UE MaterialExpressionDesaturation default LuminanceFactors

# Display-referred grades (exposure-locked by EyeAdaptationInverse when the
# engine provides it): brightness 1 shows the photo at its sRGB value, like the
# web sphere (web/house/exterior_backdrops.mjs). Gamma > 1 darkens midtones
# more than highlights, so bright facades/sky stay readable as moonlit shapes.
GRADE_DAY = {'brightness': 1.0, 'tint': (1.0, 1.0, 1.0), 'desaturation': 0.0, 'gamma': 1.0}
GRADE_GOLDEN = {'brightness': 0.6, 'tint': (1.0, 0.82, 0.62), 'desaturation': 0.1, 'gamma': 1.1}
GRADE_NIGHT = {'brightness': 0.16, 'tint': (0.48, 0.58, 1.0), 'desaturation': 0.65, 'gamma': 1.8}
COLLECTION_PARAMETERS = ('Daylight', 'GoldenWeight')
PRESETS = ('auto', 'morning', 'day', 'afternoon', 'sunset', 'night')

OWNED_DIR = '/Game/Sub01Home/Environment/BackdropFix'
MATERIAL_NAME = 'M_Sub01TokyoBackdropLevel'
INSTANCE_NAME = 'MI_Sub01TokyoBackdropLevel'
COLLECTION_NAME = 'MPC_Sub01ExteriorTime'
INSTANCE_PATH = OWNED_DIR + '/' + INSTANCE_NAME
COLLECTION_PATH = OWNED_DIR + '/' + COLLECTION_NAME

# HLSL for the MaterialExpressionCustom node (inputs named exactly as below).
CUSTOM_INPUTS = ('CamVec', 'YawDeg', 'PitchFix', 'RollFix', 'HorizonV')
HLSL = '''float3 d = normalize(-CamVec);
float r = RollFix * 0.0174532925;
float p = PitchFix * 0.0174532925;
float3 a = float3(d.x, d.y * cos(r) - d.z * sin(r), d.y * sin(r) + d.z * cos(r));
float3 b = float3(a.x * cos(p) + a.z * sin(p), a.y, -a.x * sin(p) + a.z * cos(p));
float az = atan2(b.y, b.x);
float el = asin(clamp(b.z, -1.0, 1.0));
float u = frac(0.5 + (az - YawDeg * 0.0174532925) / 6.28318531);
float v = HorizonV - el / 3.14159265;
return float2(u, v);'''


# --------------------------------------------------------------------------
# Projection (Python twin of HLSL)
# --------------------------------------------------------------------------
def _normalize(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        raise ValueError('zero direction')
    return tuple(c / n for c in v)


def equirect_uv(direction, yaw_deg=DEFAULT_YAW_DEG, pitch_fix_deg=0.0, roll_fix_deg=0.0,
                horizon_v=HORIZON_V):
    """UE view direction -> (u, v). Exact Python twin of ``HLSL``."""
    d = _normalize(direction)
    r, p = math.radians(roll_fix_deg), math.radians(pitch_fix_deg)
    a = (d[0], d[1] * math.cos(r) - d[2] * math.sin(r), d[1] * math.sin(r) + d[2] * math.cos(r))
    b = (a[0] * math.cos(p) + a[2] * math.sin(p), a[1], -a[0] * math.sin(p) + a[2] * math.cos(p))
    az = math.atan2(b[1], b[0])
    el = math.asin(max(-1.0, min(1.0, b[2])))
    u = (0.5 + (az - math.radians(yaw_deg)) / (2 * math.pi)) % 1.0
    return u, horizon_v - el / math.pi


def direction_for_uv(u, v, yaw_deg=DEFAULT_YAW_DEG, horizon_v=HORIZON_V):
    """Inverse for zero photo correction: (u, v) -> unit UE direction."""
    az = math.radians(yaw_deg) + (u - 0.5) * 2 * math.pi
    el = (horizon_v - v) * math.pi
    return (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))


def uv_of_world_point(point_cm, eye_cm, **kw):
    return equirect_uv(tuple(point_cm[i] - eye_cm[i] for i in range(3)), **kw)


def rotator_matrix(pitch, yaw, roll):
    """UE FRotationMatrix (degrees) as rows = local X, Y, Z axes in world space."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    return ((cp * cy, cp * sy, sp),
            (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp),
            (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp))


def rotate_local(point, rot):
    m = rotator_matrix(rot['pitch'], rot['yaw'], rot['roll'])
    return tuple(sum(point[i] * m[i][j] for i in range(3)) for j in range(3))


def python_rotator_positional(*args):
    """UE Python ``unreal.Rotator(roll, pitch, yaw)`` positional order (NOT C++ FRotator(P, Y, R))."""
    names = ('roll', 'pitch', 'yaw')
    out = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0}
    out.update({names[i]: float(v) for i, v in enumerate(args)})
    return out


def leveled_rotation():
    """The backdrop actor is levelled: zero pitch and roll; yaw is a material parameter."""
    return {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}


def equator_tilt_deg(rot):
    """Max angle of the mesh's local equator ring above the world horizontal."""
    worst = 0.0
    for i in range(72):
        t = math.radians(i * 5)
        w = rotate_local((math.cos(t), math.sin(t), 0.0), rot)
        worst = max(worst, abs(math.degrees(math.asin(max(-1.0, min(1.0, w[2]))))))
    return worst


# --------------------------------------------------------------------------
# Image header and 2:1 check
# --------------------------------------------------------------------------
def image_size(path):
    """(width, height) from a PNG or WebP header, without decoding."""
    data = Path(path).read_bytes()[:64]
    if data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR':
        return struct.unpack('>II', data[16:24])
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        chunk = data[12:16]
        if chunk == b'VP8 ':
            w, h = struct.unpack('<HH', data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b'VP8L':
            bits = int.from_bytes(data[21:25], 'little')
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b'VP8X':
            return int.from_bytes(data[24:27], 'little') + 1, int.from_bytes(data[27:30], 'little') + 1
    raise ValueError('Not a PNG or WebP image: %s' % path)


def require_equirect(width, height, minimum_height=512):
    """Sphere mode needs a full 360x180 equirectangular capture: exactly 2:1."""
    if width <= 0 or height <= 0 or width != 2 * height:
        raise ValueError('Sphere projection refused: %dx%d is not 2:1 equirectangular' % (width, height))
    if height < minimum_height:
        raise ValueError('Sphere projection refused: %dx%d is too small' % (width, height))
    return {'width': width, 'height': height, 'aspect': width / height,
            'texels_per_degree': width / 360.0}


# --------------------------------------------------------------------------
# Courtyard clearance
# --------------------------------------------------------------------------
def courtyard_clear(bounds, center=BACKDROP_CENTER_CM, radius=BACKDROP_RADIUS_CM,
                    margin=COURTYARD_MARGIN_CM):
    """Every courtyard bounds corner must lie well inside the backdrop sphere."""
    worst = 0.0
    for b in bounds:
        for x in (b['min'][0], b['max'][0]):
            for y in (b['min'][1], b['max'][1]):
                for z in (b['min'][2], b['max'][2]):
                    worst = max(worst, math.dist((x, y, z), center))
    return worst <= radius - margin, worst


# --------------------------------------------------------------------------
# Grade model (Python twin of the material)
# --------------------------------------------------------------------------
def _mix(a, b, t):
    return a + (b - a) * t


def blended_grade(daylight, golden_weight):
    """Parameter blend done in the material: lerp(lerp(Night, Day, D), Golden, G)."""
    out = {}
    for key in ('brightness', 'desaturation', 'gamma'):
        out[key] = _mix(_mix(GRADE_NIGHT[key], GRADE_DAY[key], daylight), GRADE_GOLDEN[key], golden_weight)
    out['tint'] = tuple(_mix(_mix(GRADE_NIGHT['tint'][i], GRADE_DAY['tint'][i], daylight),
                             GRADE_GOLDEN['tint'][i], golden_weight) for i in range(3))
    return out


def grade_rgb(rgb, grade):
    """photo^gamma -> UE Desaturation -> * tint * brightness (linear 0..1 values)."""
    shaped = [max(c, 0.0) ** grade['gamma'] for c in rgb]
    luma = sum(shaped[i] * LUMA[i] for i in range(3))
    return tuple(_mix(shaped[i], luma, grade['desaturation']) * grade['tint'][i] * grade['brightness']
                 for i in range(3))


def _smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def factors_for_elevation(elevation_deg, night=False):
    """Same curve as reference_home_lighting.exterior_grade: (Daylight, GoldenWeight)."""
    if night:
        return 0.0, 0.0
    day = _smoothstep(-12.0, 8.0, elevation_deg)
    golden = max(0.0, 1.0 - abs(elevation_deg - 3.0) / 9.0)
    return day, golden * day


def preset_factors(preset, when=None):
    """Editor presets (day/sunset/night...) via the lighting module's solar model."""
    import reference_home_lighting as rhl
    if preset not in PRESETS:
        raise ValueError('Unknown preset %r' % preset)
    instant = rhl.resolve_time(preset, when)
    elevation = rhl.solar_position(instant)['elevation_deg']
    daylight, golden = factors_for_elevation(elevation, preset == 'night')
    return {'preset': preset, 'elevation_deg': elevation, 'Daylight': daylight, 'GoldenWeight': golden}


def native_hour_factors(hour):
    """Native runtime hour (unreal_native_view_settings.py model) -> factors."""
    s = math.sin((hour - 6.0) / 12.0 * math.pi)
    return factors_for_elevation(math.degrees(math.asin(max(-1.0, min(1.0, s)))))


# --------------------------------------------------------------------------
# Proposed native runtime hook (root applies; this module never writes it)
# --------------------------------------------------------------------------
NATIVE_FILE = 'tools/unreal_native_view_settings.py'
NATIVE_MARKER = 'SUB01_EXTERIOR_TIME_HOOK'
NATIVE_INCLUDE_ANCHOR = '#include "Components/SkyLightComponent.h"\n'
NATIVE_INCLUDES = ('#include "Kismet/KismetMaterialLibrary.h"\n'
                   '#include "Materials/MaterialParameterCollection.h"\n')
NATIVE_HOUR_ANCHOR = '  Sun->SetIntensity(3.2f*Elevation);Sky->SetIntensity(.4225f*FMath::Max(.08f,Elevation));\n'
NATIVE_HOOK = (
    '  {// %s: same curve as tools/exterior_backdrop_geometry.factors_for_elevation\n'
    '   const float ExteriorElevationDeg=FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(FMath::Sin(Angle),-1.f,1.f)));\n'
    '   const float ExteriorDaylight=FMath::SmoothStep(-12.f,8.f,ExteriorElevationDeg);\n'
    '   const float ExteriorGolden=ExteriorDaylight*FMath::Max(0.f,1.f-FMath::Abs(ExteriorElevationDeg-3.f)/9.f);\n'
    '   if(UMaterialParameterCollection* ExteriorTime=LoadObject<UMaterialParameterCollection>(nullptr,TEXT("%s.%s"))){\n'
    '    UKismetMaterialLibrary::SetScalarParameterValue(this,ExteriorTime,FName(TEXT("Daylight")),ExteriorDaylight);\n'
    '    UKismetMaterialLibrary::SetScalarParameterValue(this,ExteriorTime,FName(TEXT("GoldenWeight")),ExteriorGolden);}}\n'
) % (NATIVE_MARKER, COLLECTION_PATH, COLLECTION_NAME)


def patch_native_view_settings(text):
    """Insert the exterior time hook into root's generator source text (idempotent)."""
    if NATIVE_MARKER in text:
        return text
    for anchor in (NATIVE_INCLUDE_ANCHOR, NATIVE_HOUR_ANCHOR):
        if text.count(anchor) != 1:
            raise ValueError('Native anchor missing or ambiguous: ' + anchor.strip()[:60])
    text = text.replace(NATIVE_INCLUDE_ANCHOR, NATIVE_INCLUDE_ANCHOR + NATIVE_INCLUDES, 1)
    return text.replace(NATIVE_HOUR_ANCHOR, NATIVE_HOUR_ANCHOR + NATIVE_HOOK, 1)


def native_patch_diff(repo_root):
    path = Path(repo_root) / NATIVE_FILE
    old = path.read_text()
    new = patch_native_view_settings(old)
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        'a/' + NATIVE_FILE, 'b/' + NATIVE_FILE))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--native-hook-diff':
        sys.stdout.write(native_patch_diff(sys.argv[2]))
    else:
        sys.exit('usage: exterior_backdrop_geometry.py --native-hook-diff <repo-root>')
