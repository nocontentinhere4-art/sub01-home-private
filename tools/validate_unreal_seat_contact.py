"""Gate the measured seated contact of the actual posed skin (both signs, every sample).

docs/qa/contact.md, seated at the desk: buttocks and back of thighs touch the seat cushion
(-2.5 to +0.5 cm), both soles touch the floor (0 to +1 cm). A gap fails like a penetration.
Measures from tools/unreal_audit_seat_contact.py; this module itself never changes a pose.
"""
import math

SEAT_BAND_CM = (-2.5, .5)
SOLE_BAND_CM = (0., 1.)
REGIONS = ('seat', 'left_sole', 'right_sole')


def cushion_triangles(chair_report):
    """World triangles of the actual cushion selection written by unreal_chair_surface_audit.py."""
    if chair_report.get('errors'):
        raise ValueError('Chair surface audit reported errors')
    sections = chair_report['chair']['sections']
    triangles = []
    for section in sections:
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


def validate(data):
    rows = data.get('samples', [])
    if len(rows) != 301:
        raise ValueError('Expected complete 60 Hz 3-8 second samples (301)')
    worst = {name: [math.inf, -math.inf] for name in REGIONS}
    for i, row in enumerate(rows):
        if abs(_finite(row['time']) - (3 + i / 60)) > 1e-6:
            raise ValueError('Incomplete/nonmonotonic time samples')
        if row['invalidInfluences'] != 0:
            raise ValueError('Invalid imported skin influences')
        regions = {r['region']: r for r in row['regions']}
        if set(regions) != set(REGIONS) or len(row['regions']) != 3:
            raise ValueError('Expected seat and both soles')
        for name, (low, high) in (('seat', SEAT_BAND_CM), ('left_sole', SOLE_BAND_CM), ('right_sole', SOLE_BAND_CM)):
            r = regions[name]
            if _finite(r['selectedVertices']) <= 0 or _finite(r['overSurfaceVertices']) <= 0:
                raise ValueError(f'{name}: no skin over the surface it must touch')
            gap = _finite(r['minGapCm'])
            if _finite(r['bandVertices']) <= 0 or gap < low or gap > high:
                kind = 'gap' if gap > high else 'penetration'
                raise ValueError(f'{name}: {kind} {gap:.3f} cm at {row["time"]:.4f} s outside {low}..{high} cm')
            worst[name][0] = min(worst[name][0], gap)
            worst[name][1] = max(worst[name][1], gap)
    return {'samples': len(rows), 'min_gap_range_cm': {k: tuple(v) for k, v in worst.items()},
            'acceptance': 'lowest weighted seat/sole skin vs actual cushion triangles/floor at 60 Hz for the diagnostic seat pose only; '
                          'not a physical sit transition, backrest, thigh-under-desk or chair-frame clearance'}
