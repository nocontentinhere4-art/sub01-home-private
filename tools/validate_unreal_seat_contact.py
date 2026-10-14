"""Gate and diagnose the measured seated contact of the actual posed skin (probe only).

docs/qa/contact.md, seated at the desk: buttocks and the back of each thigh touch the seat
cushion (-2.5 to +0.5 cm, the cushion's allowed compression to a touching gap) and each sole
its support (0 to +1 cm). Rule 4: each contact is a separate patch of downward-facing skin,
never one lowest vertex. EVERY patch is gated as a LOCAL SUPPORT PATCH: nothing deeper than the
band's lower edge (non-penetration / maximum compression), the lowest point within the band's
upper edge (touching), and at least MIN_SUPPORT_VERTICES patch vertices inside the band. A
whole-patch median or coverage gate is not used: buttocks and thighs are curved, and only the
part resting on the cushion is in contact (median/coverage are still reported). A genuine captured seated foot plants its toes with the heel raised
(measured: left sole median ~10.4 cm, right ~7.5 cm, plane normals tilted 32 deg and 55 deg), so a
whole-sole median or coverage gate would reject real motion; it is not used for soles.
Sole membership is the renderer's fixed bind-space plantar selection (slides material, rest
Y <= 0.004 m, bind normal Y < -0.7), not a per-pose minimum. Measures come from tools/unreal_audit_seat_contact.py.

This is a probe: nothing here changes a pose or may set NativeSeatVerified.
"""
import math

SEAT_BAND_CM = (-2.5, .5)
SOLE_BAND_CM = (0., 1.)
SEAT_REGIONS = ('buttocks', 'left_posterior_thigh', 'right_posterior_thigh')
SOLE_REGIONS = ('left_sole', 'right_sole')
REGIONS = SEAT_REGIONS + SOLE_REGIONS
# Provisional patch requirements (tune only from actual reports, and say so):
MIN_PATCH_VERTICES = 12      # downward-facing skin over the surface, per patch
MIN_BAND_COVERAGE = .5       # share of a SEAT patch within the contact band
MIN_SUPPORT_VERTICES = 12    # plantar vertices within 0..+1 cm of the support surface, per sole


def band(region):
    return SEAT_BAND_CM if region in SEAT_REGIONS else SOLE_BAND_CM


def cushion_triangles(chair_report):
    """World triangles of the actual cushion selection written by unreal_chair_surface_audit.py."""
    if chair_report.get('errors'):
        raise ValueError('Chair surface audit reported errors')
    triangles = []
    for section in chair_report['chair']['sections']:
        vertices = section['vertices_world_cm']
        for ids in section['cushion_surface']['triangle_indices']:
            if len(ids) != 3:
                raise ValueError('Malformed cushion triangle')
            triangles.extend(vertices[i] for i in ids)
    if not triangles or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in triangles):
        raise ValueError('No finite actual cushion triangles')
    return triangles


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Nonfinite measured seat metric')
    return value


def regions_by_sample(data):
    rows = data.get('samples', [])
    if len(rows) != 301:
        raise ValueError('Expected complete 60 Hz 3-8 second samples (301)')
    out = []
    for i, row in enumerate(rows):
        if abs(_finite(row['time']) - (3 + i / 60)) > 1e-6:
            raise ValueError('Incomplete/nonmonotonic time samples')
        if row['invalidInfluences'] != 0:
            raise ValueError('Invalid imported skin influences')
        regions = {r['region']: r for r in row['regions']}
        if set(regions) != set(REGIONS) or len(row['regions']) != len(REGIONS):
            raise ValueError('Expected buttocks, both posterior thighs and both soles')
        for r in regions.values():
            for key in ('selectedVertices', 'facingVertices', 'overSurfaceVertices', 'bandVertices',
                        'minGapCm', 'p10GapCm', 'p50GapCm', 'p90GapCm', 'maxGapCm'):
                _finite(r[key])
        out.append((row['time'], regions))
    return out


def validate(data):
    worst = {}
    for time, regions in regions_by_sample(data):
        for name in REGIONS:
            r, (low, high) = regions[name], band(name)
            if r['overSurfaceVertices'] < MIN_PATCH_VERTICES:
                raise ValueError(f'{name}: only {r["overSurfaceVertices"]} downward-facing vertices over the surface at {time:.4f} s')
            coverage = r['bandVertices'] / r['overSurfaceVertices']
            if r['minGapCm'] < low:
                raise ValueError(f'{name}: penetration {r["minGapCm"]:.3f} cm at {time:.4f} s below {low} cm')
            if r['minGapCm'] > high or r['bandVertices'] < MIN_SUPPORT_VERTICES:
                raise ValueError(f'{name}: no support patch, lowest {r["minGapCm"]:.3f} cm, {r["bandVertices"]} vertices '
                                 f'within {low}..{high} cm at {time:.4f} s')
            w = worst.setdefault(name, {'min_gap_cm': math.inf, 'max_median_gap_cm': -math.inf, 'min_coverage': 1.,
                                        'min_band_vertices': math.inf})
            w['min_band_vertices'] = min(w['min_band_vertices'], r['bandVertices'])
            w['min_gap_cm'] = min(w['min_gap_cm'], r['minGapCm'])
            w['max_median_gap_cm'] = max(w['max_median_gap_cm'], r['p50GapCm'])
            w['min_coverage'] = min(w['min_coverage'], coverage)
    return {'samples': 301, 'worst': worst, 'native_seat_verified': False,
            'acceptance': 'probe only: downward-facing buttocks/posterior-thigh/sole skin patches vs actual cushion '
                          'triangles/floor at 60 Hz for the diagnostic seat pose; not a physical sit transition, '
                          'backrest, thigh-under-desk or chair-frame clearance; never sets NativeSeatVerified'}


def propose_vertical_anchor(data):
    """Whole-body vertical anchor change (cm) that the measured gaps allow, or why none does.

    A translation by d moves every patch by d. A patch is satisfied when its deepest point stays
    within the band (min + d >= low) and its median touches (p50 + d <= high). Seat patches and
    soles move together, so a conflict means the leg pose (not the anchor) must change.
    """
    samples = regions_by_sample(data)

    def interval(names):
        lo, hi, binding = -math.inf, math.inf, {}
        for time, regions in samples:
            for name in names:
                r, (low, high) = regions[name], band(name)
                if r['overSurfaceVertices'] < MIN_PATCH_VERTICES:
                    binding[name] = 'patch not over its surface (needs horizontal/pose correction)'
                    continue
                if low - r['minGapCm'] > lo:
                    lo, binding['lower'] = low - r['minGapCm'], (name, time)
                # Every patch must touch at its local support patch (its lowest point).
                if high - r['minGapCm'] < hi:
                    hi, binding['upper'] = high - r['minGapCm'], (name, time)
        return lo, hi, binding

    seat_lo, seat_hi, seat_binding = interval(SEAT_REGIONS)
    sole_lo, sole_hi, sole_binding = interval(SOLE_REGIONS)
    lo, hi = max(seat_lo, sole_lo), min(seat_hi, sole_hi)
    off_surface = sorted(k for b in (seat_binding, sole_binding) for k, v in b.items() if isinstance(v, str))
    if off_surface:
        diagnosis, delta = 'some patches are not over their surface; fix horizontal anchor/pose first: ' + ', '.join(off_surface), None
    elif seat_lo > seat_hi:
        diagnosis, delta = 'seat patches disagree (one touches while another floats); needs pelvis/thigh pose, not a translation', None
    elif sole_lo > sole_hi:
        diagnosis, delta = 'feet disagree; needs leg pose, not a translation', None
    elif lo > hi:
        diagnosis, delta = 'seat and soles need different heights; needs knee/ankle pose (lower legs), not a translation', None
    else:
        delta = 0.0 if lo <= 0 <= hi else (lo if lo > 0 else hi)
        diagnosis = 'within bands as measured' if delta == 0 else f'translate the whole seated body by {delta:+.3f} cm vertically'
    return {'seat_delta_range_cm': (seat_lo, seat_hi), 'sole_delta_range_cm': (sole_lo, sole_hi),
            'common_delta_range_cm': (lo, hi), 'recommended_delta_cm': delta, 'diagnosis': diagnosis,
            'binding': {'seat': seat_binding, 'soles': sole_binding}, 'native_seat_verified': False}
