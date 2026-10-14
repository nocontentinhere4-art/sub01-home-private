"""Additive, calibrated reference dressing for the private assembled SUB-01 home.

Adds soft-furnishing and decor detail (throw pillows with piping, a folded throw,
a foot-of-bed blanket, a lumbar cushion, a coffee-table book stack, a ceramic
vase with dried stems, kitchen canisters) to the house assembled by
tools/assemble_home_blender.py, in the warm-cream, soft-daylight direction of
the owner's SimbasJungles reference. Every item comes from the calibrated spec
docs/design/reference-dressing/spec.json (real-world sizes with a source note).

Two validation layers:
  1. Planning (pure Python, `--dry-run`): checks the spec against the walk graph,
     door data, device screens and ESTIMATED furniture boxes transcribed from
     home.js. It is a pre-filter only and never places anything.
  2. Placement (inside Blender only): every rule is re-checked against the
     ACTUAL evaluated home (object.evaluated_get(depsgraph), modifiers applied,
     world matrices): triangle-level collision with every existing object, a
     downward ray onto a real support surface (no hit -> UnsupportedPlacementError
     for any resting item; wall/hanging mounts must hit their declared surface),
     and clearance zones derived from evaluated anchor bounds (desk/chair
     approach and keyboard strip from the desk, the sofa seat in use, the bed
     access side, the kitchen work zone found by ray at home_world LOOKS,
     cabinet door swings from carcass bounds) plus the 0.35 m walk-graph
     capsules, door swings and the PC monitor / phone / TV prisms and sightlines.
     Hand-typed estimates are never used for placement.

Additive only: new objects live in the "SUB01_ReferenceDressing" collection with
deterministic names. Before any change every pre-existing object is fingerprinted
(name, type, parent, world matrix, exact evaluated mesh bytes, material node
signatures); afterwards each must be byte-for-byte identical or the run aborts
before saving/exporting. No existing object is modified (no bevels, no deletes).
`--export-additive-glb` exports ONLY the new objects, so Unreal never reimports
the home (reimporting would change the material/contact hashes the seat and
keyboard audits depend on). See docs/design/reference-dressing/PREREQUISITES.md.

Pure mode (no Blender, no rendering):
    python3 tools/reference_home_dressing.py --dry-run
Server, read-only inspection of the real house.blend (never renders):
    blender --background <house.blend> --python tools/reference_home_dressing.py -- --list-identifiers
Server, placement + additive export (never renders, never saves over the input):
    blender --background <house.blend> --python tools/reference_home_dressing.py -- \
      --assets-root web/house/assets --output-dir out/reference-dressing --export-additive-glb
"""
import argparse
import ast
import hashlib
import json
import math
import sys
from pathlib import Path

try:  # Blender only; every planning function below is pure Python.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover - exercised outside Blender
    bpy = None

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'docs/design/reference-dressing/spec.json'
COLLECTION = 'SUB01_ReferenceDressing'
NAME_PREFIX = 'SUB01_RefDress_'
TAG = 'sub01ReferenceDressing'

EYE_HEIGHT_M = 1.65          # home_world NODES are walking-eye points
BODY_RADIUS_M = .35          # keep-out capsule radius around the walk graph
BODY_HEIGHT_M = 2.0
UPPER_FLOOR_M = 3.0
CONTACT_TOLERANCE_M = .005   # resting contact / touching neighbours is allowed
SNAP_LIMIT_M = .10           # a real support may differ from the spec height by at most this
FLAT_SUPPORT_M = .01         # rigid items: all support rays must agree within this


# ----------------------------------------------------------------------------
# Coordinates
# ----------------------------------------------------------------------------
def runtime_to_blender(point):
    """Browser/three.js metres (Y up) -> Blender world (Z up), as assemble_home_blender."""
    x, y, z = point
    return (x, -z, y)


def blender_to_runtime(point):
    x, y, z = point
    return (x, z, -y)


def ue_cm_to_runtime(point_cm):
    """Unreal cm -> runtime metres, from the documented 100 cm/m pivot
    (tools/unreal_home_state_bridge.py: source (2,1.16,-3.276) -> UE (200,-327.6,116))."""
    x, y, z = point_cm
    return (x / 100.0, z / 100.0, y / 100.0)


# ----------------------------------------------------------------------------
# Floor plan sources (parsed, never imported: home_world pulls in server modules)
# ----------------------------------------------------------------------------
def _literal_assignment(path, name):
    tree = ast.parse(Path(path).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                                for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f'{name} not found in {path}')


def load_graph(path=ROOT / 'home_world.py'):
    nodes = {k: tuple(float(v) for v in xyz) for k, xyz in _literal_assignment(path, 'NODES').items()}
    edges = [tuple(e) for e in _literal_assignment(path, 'EDGES')]
    for a, b in edges:
        if a not in nodes or b not in nodes:
            raise ValueError(f'edge {a}-{b} names an unknown node')
    return nodes, edges


def _literal_constants(path, names):
    """Module-level literal constants, including tuple unpacking (A, B = 1, 2)."""
    out = {}
    for node in ast.parse(Path(path).read_text()).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                out[target.id] = ast.literal_eval(node.value)
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for t, v in zip(target.elts, node.value.elts):
                    if isinstance(t, ast.Name) and t.id in names:
                        out[t.id] = ast.literal_eval(v)
    missing = set(names) - set(out)
    if missing:
        raise KeyError(f'{sorted(missing)} not found in {path}')
    return out


def load_looks(path=ROOT / 'home_world.py'):
    return {k: tuple(float(v) for v in xyz) for k, xyz in _literal_assignment(path, 'LOOKS').items()}


def load_doors(path=ROOT / 'home_interactions.py'):
    try:
        return _literal_assignment(path, 'DOORS')
    except (OSError, KeyError):
        return {}


# ----------------------------------------------------------------------------
# Geometry helpers (runtime metres: x, y up, z)
# ----------------------------------------------------------------------------
def _rot(yaw_deg, tilt_deg, point):
    """Blender Euler XYZ (tilt about X, then yaw about Z) applied to a Blender-local point."""
    t, w = math.radians(tilt_deg), math.radians(yaw_deg)
    x, y, z = point
    y, z = y * math.cos(t) - z * math.sin(t), y * math.sin(t) + z * math.cos(t)
    x, y = x * math.cos(w) - y * math.sin(w), x * math.sin(w) + y * math.cos(w)
    return (x, y, z)


def item_aabb(item):
    """Runtime AABB (low, high) of an item: local box (width X, depth Y, height Z)
    with its origin `origin_height_m` above the lowest point, rotated and placed
    at `position_runtime_m` (the origin)."""
    w, d, h = item['dims_m']
    below = item.get('origin_height_m', 0.0)
    origin = runtime_to_blender(item['position_runtime_m'])
    pts = []
    for sx in (-.5, .5):
        for sy in (-.5, .5):
            for z in (-below, h - below):
                p = _rot(item.get('yaw_deg', 0.0), item.get('tilt_deg', 0.0), (sx * w, sy * d, z))
                pts.append(blender_to_runtime(tuple(origin[i] + p[i] for i in range(3))))
    low = tuple(min(p[i] for p in pts) for i in range(3))
    high = tuple(max(p[i] for p in pts) for i in range(3))
    return low, high


def aabb_overlap(a, b, tolerance=CONTACT_TOLERANCE_M):
    return all(a[0][i] < b[1][i] - tolerance and b[0][i] < a[1][i] - tolerance for i in range(3))


def _rect_point_distance(low, high, px, pz):
    dx = max(low[0] - px, 0.0, px - high[0])
    dz = max(low[2] - pz, 0.0, pz - high[2])
    return math.hypot(dx, dz)


def segment_hits_aabb(p0, p1, box, pad=0.0):
    """Slab test: does the 3D segment p0->p1 pass through the (padded) AABB?"""
    t0, t1 = 0.0, 1.0
    for i in range(3):
        lo, hi = box[0][i] - pad, box[1][i] + pad
        d = p1[i] - p0[i]
        if abs(d) < 1e-12:
            if p0[i] < lo or p0[i] > hi:
                return False
            continue
        a, b = (lo - p0[i]) / d, (hi - p0[i]) / d
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


def walk_capsules(nodes, edges, radius=BODY_RADIUS_M):
    """One floor-interpolated capsule per edge plus a disc per node (floor = eye - 1.65)."""
    caps = []
    for a, b in edges:
        caps.append({'name': f'edge:{a}-{b}', 'a': nodes[a], 'b': nodes[b], 'radius': radius})
    for k in sorted(nodes):
        caps.append({'name': f'node:{k}', 'a': nodes[k], 'b': nodes[k], 'radius': radius})
    return caps


def capsule_hits(box, cap, step=.01):
    (ax, ay, az), (bx, by, bz) = cap['a'], cap['b']
    length = math.dist((ax, az), (bx, bz))
    steps = max(1, int(math.ceil(length / step)))
    for k in range(steps + 1):
        t = k / steps
        px, pz = ax + (bx - ax) * t, az + (bz - az) * t
        floor = (ay + (by - ay) * t) - EYE_HEIGHT_M
        if box[1][1] <= floor - .05 or box[0][1] >= floor + BODY_HEIGHT_M:
            continue
        if _rect_point_distance(box[0], box[1], px, pz) < cap['radius']:
            return True
    return False


def screen_from_spec(name, centre, u_axis, u_half, v_axis, v_half, normal, depth, viewers,
                     margin=.05):
    return {'name': name, 'centre': tuple(centre), 'u': tuple(u_axis), 'u_half': u_half,
            'v': tuple(v_axis), 'v_half': v_half, 'normal': tuple(normal), 'depth': depth,
            'viewers': [tuple(v) for v in viewers], 'margin': margin}


def _add(*vectors):
    return tuple(sum(v[i] for v in vectors) for i in range(3))


def _scale(v, s):
    return tuple(c * s for c in v)


def screen_prism(screen):
    """AABB of the screen rectangle (plus margin) extruded along its normal by
    `depth`, starting slightly behind the plane so overlapping it also counts."""
    c, m = screen['centre'], screen['margin']
    pts = []
    for su in (-1, 1):
        for sv in (-1, 1):
            corner = _add(c, _scale(screen['u'], su * (screen['u_half'] + m)),
                          _scale(screen['v'], sv * (screen['v_half'] + m)))
            for dn in (-.03, screen['depth']):
                pts.append(_add(corner, _scale(screen['normal'], dn)))
    return (tuple(min(p[i] for p in pts) for i in range(3)),
            tuple(max(p[i] for p in pts) for i in range(3)))


def screen_samples(screen, n=3):
    c = screen['centre']
    out = []
    for i in range(n):
        for j in range(n):
            a = -1 + 2 * i / (n - 1)
            b = -1 + 2 * j / (n - 1)
            out.append(_add(c, _scale(screen['u'], a * screen['u_half']),
                            _scale(screen['v'], b * screen['v_half'])))
    return out


def default_screens():
    monitor_centre = ue_cm_to_runtime((200.0, -327.6, 116.0))
    extent_x, _, extent_z = (34.0, 0.0, 20.0)   # UE half extents, cm
    return [
        screen_from_spec('pc_monitor', monitor_centre, (1, 0, 0), extent_x / 100, (0, 1, 0),
                         extent_z / 100, (0, 0, 1), 1.0,
                         viewers=[(2.0, 1.20, -2.15), (2.0, 1.65, -0.75)]),
        screen_from_spec('phone_display', (2.7, .866, -2.92), (1, 0, 0), .067 / 2, (0, 0, 1),
                         .137 / 2, (0, 1, 0), .45,
                         viewers=[(2.0, 1.20, -2.15), (2.6, 1.25, -2.55)]),
        screen_from_spec('tv', (-3.747, 1.65, -.05), (0, 0, 1), 1.66 / 2, (0, 1, 0), .95 / 2,
                         (1, 0, 0), 2.3, viewers=[(-1.85, 1.20, .1), (-2.55, 1.65, .1)]),
    ]


def _box(x0, x1, y0, y1, z0, z1):
    return ((x0, y0, z0), (x1, y1, z1))


def _cyl(x, y0, z, r, h):
    return _box(x - r, x + r, y0, y0 + h, z - r, z + r)


def default_door_zones(doors=None):
    """Door swing/slide volumes. Hinged doors use a 0.95 m disc (a 0.9 m leaf);
    the bathroom leaf slides along x=-0.85 from z 1.35 (closed) to 2.3 (open)."""
    doors = doors if doors is not None else load_doors()
    zones = []
    for name in sorted(doors):
        d = doors[name]
        if name == 'bathroom':
            continue
        floor = UPPER_FLOOR_M if d.get('upper') else 0.0
        zones.append({'name': f'door:{name}', 'disc': (d['centre'][0], d['centre'][1], .95),
                      'y': (floor, floor + 2.2)})
    zones.append(bathroom_slide_zone())
    return zones


BATH_DOOR_OPEN_Z = 2.3   # build_home_bath_door.py: "closed z 1.35 -> open z 2.3 along the x -0.85 wall"


def bathroom_slide_zone(path=ROOT / 'tools/build_home_bath_door.py'):
    """Swept volume of the sliding bathroom leaf, from the builder's own constants."""
    consts = _literal_constants(path, ('SLAB_CENTRE', 'THICKNESS', 'HEIGHT', 'WIDTH'))
    (cx, cy, cz), t, h, w = consts['SLAB_CENTRE'], consts['THICKNESS'], consts['HEIGHT'], consts['WIDTH']
    pad = .08
    return {'name': 'door:bathroom_slide',
            'box': _box(cx - t / 2 - pad, cx + t / 2 + pad, cy - h / 2, cy + h / 2,
                        cz - w / 2 - pad, BATH_DOOR_OPEN_Z + w / 2 + pad)}


def estimated_cabinet_door_zones():
    """Planning estimate only (home.js cabinet positions); placement derives these
    from the evaluated carcass bounds instead."""
    return [{'name': 'door:kitchen_upper_cabinets', 'box': _box(-3.78, -.62, 1.68, 2.42, -3.53, -3.0)},
            {'name': 'door:kitchen_lower_cabinets', 'box': _box(-3.78, -.62, 0.0, .86, -3.20, -2.62)}]


def default_clear_zones():
    return [
        {'name': 'clear:desk_chair_keyboard_mouse', 'box': _box(1.55, 2.55, 0.0, 1.45, -3.15, -1.30)},
        {'name': 'clear:sofa_seat_in_use', 'box': _box(-2.30, -1.30, .40, 1.60, -.20, .40)},
        {'name': 'clear:kitchen_prep_worktop', 'box': _box(-2.36, -1.42, .90, 1.70, -3.88, -3.18)},
        {'name': 'clear:kitchen_sink_and_tap', 'box': _box(-3.05, -2.35, .70, 1.25, -3.88, -3.18)},
    ]


def default_existing_solids():
    """Existing objects (runtime AABBs from home.js / prepared sidecars) dressing must not cut."""
    return [
        {'name': 'existing:porta_espresso', 'box': _box(-1.39, -1.09, .925, 1.275, -3.665, -3.255)},
        {'name': 'existing:espresso_cup', 'box': _cyl(-1.24, .94, -3.27, .06, .08)},
        {'name': 'existing:utensil_crock', 'box': _cyl(-3.40, .925, -3.45, .09, .29)},
        {'name': 'existing:kitchen_plant', 'box': _box(-.96, -.68, .94, 1.42, -3.69, -3.41)},
        {'name': 'existing:queen_bed_pillows', 'box': _box(-3.084, -1.716, 3.554, 3.768, -3.24, -2.80)},
        {'name': 'existing:bedside_lamp', 'box': _cyl(-3.55, 3.50, -3.10, .155, .40)},
        {'name': 'existing:desk_lamp', 'box': _box(2.50, 2.80, .85, 1.35, -3.32, -3.04)},
        {'name': 'existing:desk_plant', 'box': _box(2.87, 3.13, .855, 1.25, -3.38, -3.12)},
        {'name': 'existing:phone_body', 'box': _box(2.6625, 2.7375, .85, .867, -2.995, -2.845)},
        {'name': 'existing:monitor', 'box': _box(1.64, 2.36, .82, 1.38, -3.32, -3.28)},
        {'name': 'existing:tv_panel', 'box': _box(-3.85, -3.75, 1.14, 2.16, -.92, .82)},
    ]


SUPPORTS = {
    # name: top y, runtime rect (x0, x1, z0, z1), floor
    'sofa_seat': {'top': .503, 'rect': (-2.2625, -1.3375, .1 - 1.1375, .1 + 1.1375), 'floor': 0},
    'sofa_arm_right': {'top': .71, 'rect': (-2.2625, -1.3375, 1.0, 1.2375), 'floor': 0},
    'coffee_table_top': {'top': .455, 'rect': (-3.55, -2.85, -.60, .80), 'floor': 0},
    'kitchen_counter': {'top': .9225, 'rect': (-3.78, -.62, -3.88, -3.18), 'floor': 0},
    'bed_top': {'top': 3.68, 'rect': (-3.25, -1.55, -3.4625, -1.2375), 'floor': 1},
}


def build_context(nodes=None, edges=None, doors=None):
    if nodes is None or edges is None:
        nodes, edges = load_graph()
    return {'capsules': walk_capsules(nodes, edges), 'screens': default_screens(),
            'doors': default_door_zones(doors) + estimated_cabinet_door_zones(),
            'clear': default_clear_zones(), 'solids': default_existing_solids(), 'supports': SUPPORTS,
            'basis': 'planning-estimate'}


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------
def _zone_hits(box, zone):
    if 'box' in zone:
        return aabb_overlap(box, zone['box'], 0.0)
    x, z, r = zone['disc']
    y0, y1 = zone['y']
    if box[1][1] <= y0 or box[0][1] >= y1:
        return False
    return _rect_point_distance(box[0], box[1], x, z) < r


def validate_item(item, context, placed=()):
    """All reasons this item may not be placed (empty list = valid)."""
    reasons = []
    box = item_aabb(item)
    for cap in context['capsules']:
        if capsule_hits(box, cap):
            reasons.append(f'walk_graph:{cap["name"]}')
    for zone in context['doors']:
        if _zone_hits(box, zone):
            reasons.append(zone['name'])
    for screen in context['screens']:
        if aabb_overlap(box, screen_prism(screen), 0.0):
            reasons.append(f'screen_prism:{screen["name"]}')
            continue
        if any(segment_hits_aabb(eye, s, box) for eye in screen['viewers']
               for s in screen_samples(screen)):
            reasons.append(f'screen_sightline:{screen["name"]}')
    for zone in context['clear']:
        if _zone_hits(box, zone):
            reasons.append(zone['name'])
    # A soft item may lean on named neighbours (layered pillows); nothing else.
    leans = set(item.get('leans_on', []))
    for solid in context.get('solids', ()):
        if solid['name'] not in leans and aabb_overlap(box, solid['box']):
            reasons.append(f'collides:{solid["name"]}')
    geometry = context.get('geometry')
    if geometry is not None:
        for ident, count in sorted(geometry.collisions(item).items()):
            reasons.append(f'collides:{ident} ({count} tris)')
    for other in placed:
        mutual = (f'dressing:{other["id"]}' in leans
                  or f'dressing:{item["id"]}' in other.get('leans_on', ()))
        if not mutual and aabb_overlap(box, other['aabb']):
            reasons.append(f'collides:dressing:{other["id"]}')
    if context.get('supports') is None:   # placement: support verified by resolve_support()
        return reasons
    support = context['supports'].get(item.get('support'))
    if support is None:
        reasons.append(f'support:unknown:{item.get("support")}')
    else:
        x0, x1, z0, z1 = support['rect']
        over = item.get('overhang_m', .02)
        px, py, pz = item['position_runtime_m']
        if not (x0 <= px <= x1 and z0 <= pz <= z1):
            reasons.append('support:origin_outside_surface')
        if box[0][0] < x0 - over or box[1][0] > x1 + over or box[0][2] < z0 - over or box[1][2] > z1 + over:
            reasons.append('support:footprint_overhangs_surface')
        if abs(py - support['top']) > item.get('rest_tolerance_m', .03):
            reasons.append(f'support:not_resting (y {py:.3f} vs surface {support["top"]:.3f})')
    return reasons


# ----------------------------------------------------------------------------
# Spec and plan
# ----------------------------------------------------------------------------
def load_spec(path=SPEC_PATH):
    spec = json.loads(Path(path).read_text())
    ids = [i['id'] for i in spec['items']]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate spec item ids')
    for item in spec['items']:
        dims = item['dims_m']
        if len(dims) != 3 or not all(isinstance(v, (int, float)) and v > 0 for v in dims):
            raise ValueError(f'{item["id"]}: dims_m must be three positive metres')
        if not item.get('source', '').strip() or not item.get('placement_rule', '').strip():
            raise ValueError(f'{item["id"]}: source note and placement rule are required')
    return spec


def object_name(item):
    return f'{NAME_PREFIX}{item["room"]}_{item["id"]}'


def plan_dressing(spec=None, context=None):
    """Deterministic plan: items in spec-id order, validated against all rules and
    against previously accepted items. Returns the JSON-serialisable report."""
    spec = spec if spec is not None else load_spec()
    context = context if context is not None else build_context()
    placed, rejected = [], []
    for item in sorted(spec['items'], key=lambda i: i['id']):
        reasons = validate_item(item, context, placed)
        low, high = item_aabb(item)
        entry = {'id': item['id'], 'name': object_name(item), 'room': item['room'],
                 'kind': item['kind'], 'aabb': [list(map(_r, low)), list(map(_r, high))]}
        if reasons:
            rejected.append({**entry, 'reasons': reasons})
        else:
            placed.append({**entry, 'aabb': (low, high), 'leans_on': list(item.get('leans_on', []))})
    for skip in sorted(spec.get('skipped_existing', []), key=lambda s: s['id']):
        rejected.append({'id': skip['id'], 'name': None, 'room': skip['room'], 'kind': 'skip',
                         'reasons': [f'duplicate:existing:{skip["evidence"]}']})
    return {
        'collection': COLLECTION,
        'spec_sha256': hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
        'keepout': {'body_radius_m': BODY_RADIUS_M, 'capsules': len(context['capsules']),
                    'screens': [s['name'] for s in context['screens']],
                    'doors': [d['name'] for d in context['doors']],
                    'clear_zones': [c['name'] for c in context['clear']]},
        'placed': [{**p, 'aabb': [list(map(_r, p['aabb'][0])), list(map(_r, p['aabb'][1]))]}
                   for p in placed],
        'rejected': rejected,
    }


def _r(v):
    return round(float(v), 4)


# ----------------------------------------------------------------------------
# Pure mesh builders (Blender-local metres, Z up; origin as documented)
# ----------------------------------------------------------------------------
def box_mesh(w, d, h):
    """Box with origin at bottom centre. Returns (verts, faces, loop_uvs)."""
    vs = [(x * w / 2, y * d / 2, z * h) for z in (0, 1) for y in (-1, 1) for x in (-1, 1)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    return vs, faces, box_project_uvs(vs, faces)


def box_project_uvs(verts, faces):
    """Per-loop UVs in metres from the face's dominant axis (box projection)."""
    uvs = []
    for f in faces:
        n = _face_normal([verts[i] for i in f])
        axis = max(range(3), key=lambda i: abs(n[i]))
        a, b = [i for i in range(3) if i != axis]
        uvs.append([(verts[i][a], verts[i][b]) for i in f])
    return uvs


def _face_normal(points):
    n = [0.0, 0.0, 0.0]
    for k, p in enumerate(points):
        q = points[(k + 1) % len(points)]
        n[0] += (p[1] - q[1]) * (p[2] + q[2])
        n[1] += (p[2] - q[2]) * (p[0] + q[0])
        n[2] += (p[0] - q[0]) * (p[1] + q[1])
    length = math.sqrt(sum(c * c for c in n)) or 1.0
    return tuple(c / length for c in n)


def pillow_mesh(w, t, h, n=16, pinch=.07, sag=.012):
    """Closed throw-pillow: front (-Y) and back (+Y) panels sewn at a shared seam,
    edge midpoints pinched in (corner 'ears'), interior slightly sagged. Origin at
    the bottom centre of the seam. Returns (verts, faces, loop_uvs, seam_loop)."""
    index, verts = {}, []

    def vid(i, j, side):
        boundary = i in (0, n) or j in (0, n)
        key = (i, j, 0 if boundary else side)
        if key not in index:
            u, v = -1 + 2 * i / n, -1 + 2 * j / n
            x = u * w / 2 * (1 - pinch * (1 - v * v))
            z = v * h / 2 * (1 - pinch * (1 - u * u)) + h / 2
            fill = max(0.0, (1 - abs(u) ** 2.5) * (1 - abs(v) ** 2.5)) ** .5
            y = side * t / 2 * fill
            z -= sag * (1 - u * u) * (1 - v * v)
            index[key] = len(verts)
            verts.append((x, y, z))
        return index[key]

    faces, uvs = [], []
    for side in (-1, 1):
        for i in range(n):
            for j in range(n):
                quad = [vid(i, j, side), vid(i + 1, j, side), vid(i + 1, j + 1, side), vid(i, j + 1, side)]
                if side > 0:
                    quad.reverse()
                faces.append(tuple(quad))
                uvs.append([(verts[k][0] + (w if side > 0 else 0), verts[k][2]) for k in quad])
    seam = ([vid(i, 0, 0) for i in range(n)] + [vid(n, j, 0) for j in range(n)]
            + [vid(i, n, 0) for i in range(n, 0, -1)] + [vid(0, j, 0) for j in range(n, 0, -1)])
    return verts, faces, uvs, [verts[k] for k in seam]


def lathe_mesh(profile, segments=32):
    """Closed surface of revolution about Z. profile: [(radius, z)] bottom->top;
    radius 0 at the ends closes the caps. Returns (verts, faces, loop_uvs)."""
    verts, rings = [], []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([len(verts)] * segments)
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for s in range(segments):
                a = 2 * math.pi * s / segments
                ring.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)
    faces, uvs = [], []
    circumference = 2 * math.pi * max(r for r, _ in profile)
    for k in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            quad = [(rings[k][s], s), (rings[k][s2], s + 1), (rings[k + 1][s2], s + 1), (rings[k + 1][s], s)]
            face = []
            for v, col in quad:
                if v not in [f[0] for f in face]:
                    face.append((v, col))
            if len(face) >= 3:
                faces.append(tuple(v for v, _ in face))
                uvs.append([(col / segments * circumference, verts[v][2]) for v, col in face])
    return verts, faces, uvs


def draped_strip_mesh(length, top_width, drop, radius=.03, nx=24, n_arc=6, drop_steps=6, wave=.006):
    """Open fabric strip lying over a support: flat top of `top_width` at z=0
    (its underside rests on the support), rounded shoulders of `radius`, then
    dropping `drop` on both sides. Length runs along local X. Solidify adds
    thickness outward in Blender. Top-face normals point +Z."""
    prof = []
    if drop <= radius + 1e-9:                   # flat folded band: shoulders only
        drop, drop_steps = radius, 0
    for k in range(drop_steps, 0, -1):          # left drop, bottom -> shoulder
        prof.append((-top_width / 2 - radius, -radius - (drop - radius) * k / drop_steps))
    for k in range(n_arc + 1):                  # left shoulder arc
        a = math.pi - (math.pi / 2) * k / n_arc
        prof.append((-top_width / 2 + radius * math.cos(a), -radius + radius * math.sin(a)))
    for k in range(1, 4):
        prof.append((-top_width / 2 + top_width * k / 4, 0.0))
    for k in range(n_arc + 1):                  # right shoulder arc
        a = math.pi / 2 - (math.pi / 2) * k / n_arc
        prof.append((top_width / 2 + radius * math.cos(a), -radius + radius * math.sin(a)))
    for k in range(1, drop_steps + 1):
        prof.append((top_width / 2 + radius, -radius - (drop - radius) * k / drop_steps))
    verts = []
    for py, pz in prof:
        hang = max(0.0, -pz - radius) / max(drop - radius, 1e-6)
        for j in range(nx + 1):
            x = -length / 2 + length * j / nx
            verts.append((x, py + wave * hang * math.sin(x * 23.0) * (1 if py > 0 else -1), pz))
    cols = nx + 1
    faces, uvs = [], []
    for i in range(len(prof) - 1):
        for j in range(nx):
            quad = (i * cols + j, i * cols + j + 1, (i + 1) * cols + j + 1, (i + 1) * cols + j)
            faces.append(quad)
            uvs.append([(verts[v][0], i / (len(prof) - 1) * (top_width + 2 * drop)) for v in quad])
    return verts, faces, uvs


def mesh_is_closed(faces):
    """Every undirected edge shared by exactly two faces (watertight)."""
    count = {}
    for f in faces:
        for k in range(len(f)):
            e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
            count[e] = count.get(e, 0) + 1
    return all(c == 2 for c in count.values())


VASE_PROFILE = [(0, 0), (.045, 0), (.055, .01), (.06, .06), (.058, .12), (.045, .17), (.028, .2),
                (.03, .215), (.034, .22), (.03, .22), (.024, .205), (0, .205)]


CANISTER_LID_M = .032


def canister_profile(radius, body_height):
    """Glazed body, slightly eased base, open top closed flush (the oak lid sits on it)."""
    return [(0, 0), (radius - .004, 0), (radius, .004), (radius, body_height - .002),
            (radius - .002, body_height), (0, body_height)]


def canister_lid_profile(radius):
    """Oak lid with a small turned knob; total height CANISTER_LID_M."""
    return [(0, 0), (radius + .002, 0), (radius + .002, .012), (radius - .006, .018), (.012, .018),
            (.014, .026), (.010, CANISTER_LID_M), (0, CANISTER_LID_M)]




# ----------------------------------------------------------------------------
# Evaluated geometry (pure Python; filled from Blender or from test fakes)
# ----------------------------------------------------------------------------
class UnsupportedPlacementError(RuntimeError):
    """A resting item has no real support surface, or a mount has no verified surface."""


def _inv_rot(yaw_deg, tilt_deg, point):
    """Inverse of _rot: Blender world offset -> item-local frame."""
    t, w = math.radians(tilt_deg), math.radians(yaw_deg)
    x, y, z = point
    x, y = x * math.cos(w) + y * math.sin(w), -x * math.sin(w) + y * math.cos(w)
    y, z = y * math.cos(t) + z * math.sin(t), -y * math.sin(t) + z * math.cos(t)
    return (x, y, z)


def item_local_boxes(item):
    """Collision volumes in the item-local frame (Blender local: X width, Y depth, Z up).
    A draped throw is three slabs (top + two drops), not the box around its support."""
    w, d, h = item['dims_m']
    below = item.get('origin_height_m', 0.0)
    if item['kind'] == 'draped_throw':
        p = item['params']
        t_total = p.get('thickness', .012) * (1 + p.get('fold_layers', 0))
        half = p['top_width'] / 2 + p.get('radius', .03)
        boxes = [((-w / 2, -half - t_total, 0.0), (w / 2, half + t_total, t_total))]
        if p['drop'] > p.get('radius', .03) + 1e-9:
            for sign in (-1, 1):
                y0, y1 = sorted((sign * half, sign * (half + t_total)))
                boxes.append(((-w / 2, y0, -p['drop']), (w / 2, y1, -p.get('radius', .03))))
        return boxes
    return [((-w / 2, -d / 2, -below), (w / 2, d / 2, h - below))]


def world_to_local(item, point_runtime):
    o = runtime_to_blender(item['position_runtime_m'])
    b = runtime_to_blender(point_runtime)
    return _inv_rot(item.get('yaw_deg', 0.0), item.get('tilt_deg', 0.0), tuple(b[i] - o[i] for i in range(3)))


def tri_box_overlap(centre, half, tri):
    """Akenine-Moller separating-axis test: triangle vs axis-aligned box."""
    v = [tuple(p[i] - centre[i] for i in range(3)) for p in tri]
    for i in range(3):
        if min(p[i] for p in v) > half[i] or max(p[i] for p in v) < -half[i]:
            return False
    e = [tuple(v[(k + 1) % 3][i] - v[k][i] for i in range(3)) for k in range(3)]
    for edge in e:
        for a in range(3):
            unit = [0.0, 0.0, 0.0]
            unit[a] = 1.0
            axis = (unit[1] * edge[2] - unit[2] * edge[1], unit[2] * edge[0] - unit[0] * edge[2],
                    unit[0] * edge[1] - unit[1] * edge[0])
            proj = [sum(p[i] * axis[i] for i in range(3)) for p in v]
            r = sum(half[i] * abs(axis[i]) for i in range(3))
            if min(proj) > r or max(proj) < -r:
                return False
    n = (e[0][1] * e[1][2] - e[0][2] * e[1][1], e[0][2] * e[1][0] - e[0][0] * e[1][2],
         e[0][0] * e[1][1] - e[0][1] * e[1][0])
    dist = sum(n[i] * v[0][i] for i in range(3))
    r = sum(half[i] * abs(n[i]) for i in range(3))
    return abs(dist) <= r


def _ray_triangle(origin, direction, tri, eps=1e-12):
    """Moller-Trumbore; distance along `direction` or None."""
    a, b, c = tri
    e1 = tuple(b[i] - a[i] for i in range(3))
    e2 = tuple(c[i] - a[i] for i in range(3))
    pv = (direction[1] * e2[2] - direction[2] * e2[1], direction[2] * e2[0] - direction[0] * e2[2],
          direction[0] * e2[1] - direction[1] * e2[0])
    det = sum(e1[i] * pv[i] for i in range(3))
    if abs(det) < eps:
        return None
    tv = tuple(origin[i] - a[i] for i in range(3))
    u = sum(tv[i] * pv[i] for i in range(3)) / det
    if u < 0 or u > 1:
        return None
    qv = (tv[1] * e1[2] - tv[2] * e1[1], tv[2] * e1[0] - tv[0] * e1[2], tv[0] * e1[1] - tv[1] * e1[0])
    v = sum(direction[i] * qv[i] for i in range(3)) / det
    if v < 0 or u + v > 1:
        return None
    t = sum(e2[i] * qv[i] for i in range(3)) / det
    return t if t >= 0 else None


class SceneGeometry:
    """Evaluated world triangles of the existing home, in runtime metres.
    records: [{'name', 'ident', 'aabb': (lo, hi), 'tris': [(a, b, c), ...]}]"""

    def __init__(self, records):
        self.records = list(records)

    def matching(self, prefixes):
        return [r for r in self.records
                if any(r['ident'].startswith(p) or r['name'].startswith(p) for p in prefixes)]

    @staticmethod
    def union(records):
        if not records:
            return None
        return (tuple(min(r['aabb'][0][i] for r in records) for i in range(3)),
                tuple(max(r['aabb'][1][i] for r in records) for i in range(3)))

    def ray(self, origin, direction, max_dist, records=None):
        """Nearest hit (distance, ident) along a unit direction, or None."""
        end = tuple(origin[i] + direction[i] * max_dist for i in range(3))
        best = None
        for rec in self.records if records is None else records:
            if not segment_hits_aabb(origin, end, rec['aabb'], pad=1e-6):
                continue
            for tri in rec['tris']:
                t = _ray_triangle(origin, direction, tri)
                if t is not None and t <= max_dist and (best is None or t < best[0]):
                    best = (t, rec['ident'])
        return best

    def surface_below(self, x, z, y_from, y_to, records=None):
        hit = self.ray((x, y_from, z), (0.0, -1.0, 0.0), y_from - y_to, records)
        return None if hit is None else (y_from - hit[0], hit[1])

    def collisions(self, item):
        """{ident: triangle count} of existing triangles inside the item's collision
        volumes, after shrinking each volume by the item's soft-contact allowance."""
        allowance = item.get('contact_allowance_m', CONTACT_TOLERANCE_M)
        boxes = []
        for lo, hi in item_local_boxes(item):
            half = tuple(max(0.0005, (hi[i] - lo[i]) / 2 - allowance) for i in range(3))
            boxes.append((tuple((lo[i] + hi[i]) / 2 for i in range(3)), half))
        world = item_aabb(item)
        hits = {}
        for rec in self.records:
            if not aabb_overlap(world, rec['aabb'], 0.0):
                continue
            for tri in rec['tris']:
                if any(min(p[i] for p in tri) > world[1][i] or max(p[i] for p in tri) < world[0][i]
                       for i in range(3)):
                    continue
                local = [world_to_local(item, p) for p in tri]
                if any(tri_box_overlap(c, h, local) for c, h in boxes):
                    hits[rec['ident']] = hits.get(rec['ident'], 0) + 1
        return hits


# Exact identifier prefixes (bakeId, else object name) of evaluated anchors. These
# come from the assembler and the GI-architecture proxy; root confirms them with
# --list-identifiers and can override with --anchors <json>.
DEFAULT_ANCHORS = {
    'sofa': ['house-sofa-'],
    'coffee_table': ['house-cc0-coffee-table'],
    'bed': ['house-cc0-queen-bed'],
    'desk': ['house-office-desk-'],
    'upper_cabinet': ['house-upper-cabinet-'],
    'lower_cabinet': ['house-lower-cabinet-'],
}
SUPPORT_ANCHOR = {'sofa_seat': 'sofa', 'sofa_arm_right': 'sofa', 'coffee_table_top': 'coffee_table',
                  'bed_top': 'bed', 'kitchen_counter': None}
ROOM_ANCHORS = {'lounge': ('sofa', 'coffee_table'), 'bedroom': ('bed',),
                'kitchen': ('upper_cabinet', 'lower_cabinet', 'kitchen_surface'), 'office': ('desk',)}


def derived_zones(geometry, anchors=None, nodes=None, looks=None):
    """Clearance and door-swing zones from evaluated anchor bounds.
    Returns (zones, missing_anchor_names)."""
    anchors = anchors or DEFAULT_ANCHORS
    if nodes is None:
        nodes, _ = load_graph()
    looks = looks if looks is not None else load_looks()
    zones, missing = [], set()
    bounds = {}
    for key, prefixes in anchors.items():
        bounds[key] = SceneGeometry.union(geometry.matching(prefixes))
        if bounds[key] is None:
            missing.add(key)
    monitor = next(s for s in default_screens() if s['name'] == 'pc_monitor')
    if bounds.get('desk'):
        lo, hi = bounds['desk']
        mx = monitor['centre'][0]
        zones.append({'name': 'clear:desk_chair_approach', 'box': _box(mx - .6, mx + .6, lo[1], lo[1] + 1.45,
                                                                       hi[2], hi[2] + 1.30)})
        zones.append({'name': 'clear:keyboard_mouse_strip', 'box': _box(mx - .55, mx + .55, hi[1] - .05,
                                                                        hi[1] + .25, hi[2] - .40, hi[2])})
    if bounds.get('sofa'):
        lo, hi = bounds['sofa']
        cz = (lo[2] + hi[2]) / 2
        zones.append({'name': 'clear:sofa_seat_in_use', 'box': _box(lo[0], hi[0], lo[1] + .40, hi[1] + .70,
                                                                    cz - .30, cz + .30)})
    if bounds.get('bed'):
        lo, hi = bounds['bed']
        bx = nodes['bed'][0]
        x0, x1 = (hi[0], hi[0] + .60) if bx > hi[0] else (lo[0] - .60, lo[0])
        zones.append({'name': 'clear:bed_access_side', 'box': _box(x0, x1, lo[1], lo[1] + 2.0, lo[2], hi[2])})
    kx, _, kz = looks['kitchen']
    hit = geometry.surface_below(kx, kz, 1.5, .5)
    if hit is None:
        missing.add('kitchen_surface')
    else:
        top = hit[0]
        zones.append({'name': 'clear:kitchen_work_zone', 'box': _box(kx - .50, kx + .50, top - .02, top + .70,
                                                                     kz - .40, kz + .40)})
    for key in ('upper_cabinet', 'lower_cabinet'):
        if bounds.get(key):
            lo, hi = bounds[key]
            leaf = (hi[0] - lo[0]) / 4          # four doors per run (build_home_upper_cabinet)
            zones.append({'name': f'door:kitchen_{key}_swing', 'box': _box(lo[0], hi[0], lo[1], hi[1],
                                                                          hi[2], hi[2] + leaf)})
    return zones, sorted(missing)


def evaluated_context(geometry, anchors=None, doors=None, nodes=None, edges=None, looks=None):
    if nodes is None or edges is None:
        nodes, edges = load_graph()
    zones, missing = derived_zones(geometry, anchors, nodes, looks)
    return {'capsules': walk_capsules(nodes, edges), 'screens': default_screens(),
            'doors': default_door_zones(doors) + [z for z in zones if z['name'].startswith('door:')],
            'clear': [z for z in zones if z['name'].startswith('clear:')],
            'geometry': geometry, 'supports': None, 'missing_anchors': missing,
            'basis': 'evaluated-geometry'}


def support_samples(item):
    px, _, pz = item['position_runtime_m']
    if item['kind'] == 'draped_throw':
        return [(px, pz)]
    if item.get('rigid'):
        lo, hi = item_aabb(item)
        hx, hz = (hi[0] - lo[0]) * .3, (hi[2] - lo[2]) * .3
        return [(px, pz), (px - hx, pz - hz), (px + hx, pz - hz), (px - hx, pz + hz), (px + hx, pz + hz)]
    # Soft/leaning: along the width only, so rays miss the backrest behind it.
    a = blender_to_runtime(_rot(item.get('yaw_deg', 0.0), 0.0, (item['dims_m'][0] * .3, 0, 0)))
    return [(px, pz), (px - a[0], pz - a[2]), (px + a[0], pz + a[2])]


def resolve_support(item, geometry, anchors=None):
    """Verify the item against REAL evaluated surfaces and return a placed copy.
    Resting items need a support hit under every sample (on the declared anchor
    when one is known), else UnsupportedPlacementError. Wall/hanging mounts must
    hit their declared attach surface within max_gap_m."""
    anchors = anchors or DEFAULT_ANCHORS
    item = json.loads(json.dumps(item))
    mount = item.get('mount', 'rest')
    if mount in ('wall', 'hanging'):
        attach = item.get('attach') or {}
        direction = attach.get('direction_runtime')
        if not attach.get('surface') or not direction:
            raise UnsupportedPlacementError(f'{item["id"]}: {mount} mount declares no attach surface/direction')
        length = math.sqrt(sum(c * c for c in direction))
        unit = tuple(c / length for c in direction)
        gap = attach.get('max_gap_m', .02)
        records = geometry.matching(attach['surface_prefixes']) if attach.get('surface_prefixes') else None
        hit = geometry.ray(tuple(item['position_runtime_m']), unit, gap, records)
        if hit is None:
            raise UnsupportedPlacementError(
                f'{item["id"]}: {mount} mount found no {attach["surface"]} within {gap} m')
        item['support_evidence'] = {'mount': mount, 'surface': hit[1], 'gap_m': _r(hit[0])}
        return item
    if mount != 'rest':
        raise ValueError(f'{item["id"]}: unknown mount {mount!r}')
    key = SUPPORT_ANCHOR.get(item.get('support'), 'unknown')
    if key == 'unknown':
        raise UnsupportedPlacementError(f'{item["id"]}: unknown support {item.get("support")!r}')
    records = None
    if key is not None:
        records = geometry.matching(anchors.get(key, []))
        if not records:
            raise UnsupportedPlacementError(f'{item["id"]}: support anchor {key} not found in the evaluated home')
    py = item['position_runtime_m'][1]
    hits = []
    for x, z in support_samples(item):
        hit = geometry.surface_below(x, z, py + SNAP_LIMIT_M, py - SNAP_LIMIT_M, records)
        if hit is None:
            raise UnsupportedPlacementError(
                f'{item["id"]}: no supporting surface under ({x:.3f}, {z:.3f}) within ±{SNAP_LIMIT_M} m')
        hits.append(hit)
    ys = sorted(h[0] for h in hits)
    if item.get('rigid') and ys[-1] - ys[0] > FLAT_SUPPORT_M:
        raise UnsupportedPlacementError(f'{item["id"]}: uneven/partial support ({ys[-1] - ys[0]:.3f} m)')
    surface = ys[-1] if item.get('rigid') else ys[len(ys) // 2]
    target = surface - item.get('sink_m', 0.0)
    item['support_evidence'] = {'mount': 'rest', 'surfaces': sorted({h[1] for h in hits}),
                                'surface_y': _r(surface), 'delta_m': _r(target - py)}
    item['position_runtime_m'][1] = target
    return item


def place_on_evaluated_home(spec, geometry, anchors=None, context=None):
    """Authoritative placement against the evaluated home. Returns (accepted items,
    rejected entries). Never consults hand-typed boxes."""
    context = context or evaluated_context(geometry, anchors)
    missing = set(context['missing_anchors'])
    accepted, rejected, placed = [], [], []
    for item in sorted(spec['items'], key=lambda i: i['id']):
        entry = {'id': item['id'], 'name': object_name(item), 'room': item['room'], 'kind': item['kind']}
        needed = sorted(missing & set(ROOM_ANCHORS.get(item['room'], ())))
        if needed:
            rejected.append({**entry, 'reasons': [f'clearance_unverified:{a}' for a in needed]})
            continue
        present = [r['ident'] for p in item.get('refuse_if_present', []) for r in geometry.matching([p])]
        if present:
            rejected.append({**entry, 'reasons': [f'duplicate:existing:{i}' for i in sorted(set(present))]})
            continue
        try:
            resolved = resolve_support(item, geometry, anchors)
        except UnsupportedPlacementError as error:
            rejected.append({**entry, 'reasons': [f'unsupported:{error}']})
            continue
        reasons = validate_item(resolved, context, placed)
        if reasons:
            rejected.append({**entry, 'reasons': reasons})
            continue
        placed.append({'id': item['id'], 'aabb': item_aabb(resolved),
                       'leans_on': list(item.get('leans_on', []))})
        accepted.append(resolved)
    return accepted, rejected


# ----------------------------------------------------------------------------
# Fingerprint of the existing home (works on bpy objects or duck-typed fakes)
# ----------------------------------------------------------------------------
GEOMETRY_TYPES = ('MESH', 'CURVE', 'SURFACE', 'META', 'FONT')


def _floats(values):
    return repr([float(v) for v in values]).encode()


def _material_signature(material):
    if material is None:
        return None
    sig = {'name': material.name, 'use_nodes': bool(getattr(material, 'use_nodes', False)),
           'diffuse': list(getattr(material, 'diffuse_color', ()) or ())}
    tree = getattr(material, 'node_tree', None)
    if tree is not None:
        nodes = []
        for node in sorted(tree.nodes, key=lambda n: n.name):
            inputs = []
            for sock in getattr(node, 'inputs', ()):
                value = getattr(sock, 'default_value', None)
                try:
                    value = [float(v) for v in value]
                except TypeError:
                    value = float(value) if isinstance(value, (int, float)) else repr(value)
                inputs.append((sock.name, value))
            image = getattr(node, 'image', None)
            nodes.append((node.name, getattr(node, 'bl_idname', ''), inputs,
                          getattr(image, 'filepath', None) if image else None))
        links = sorted((l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name)
                       for l in tree.links)
        sig.update(nodes=nodes, links=links)
    return hashlib.sha256(json.dumps(sig, sort_keys=True, default=repr).encode()).hexdigest()


def evaluate_object(obj, depsgraph):
    """(fingerprint row, geometry record or None) from the evaluated object."""
    row = {'name': obj.name, 'type': obj.type,
           'parent': obj.parent.name if getattr(obj, 'parent', None) else None,
           'matrix': [list(map(float, r)) for r in obj.matrix_world],
           'data': getattr(getattr(obj, 'data', None), 'name', None),
           'materials': [_material_signature(s.material) for s in getattr(obj, 'material_slots', ())]}
    record = None
    if obj.type in GEOMETRY_TYPES:
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        try:
            if mesh is not None:
                mesh.calc_loop_triangles()
                digest = hashlib.sha256()
                for v in mesh.vertices:
                    digest.update(_floats(v.co))
                tri_index = [tuple(t.vertices) for t in mesh.loop_triangles]
                digest.update(repr(tri_index).encode())
                digest.update(repr([getattr(t, 'material_index', 0) for t in mesh.loop_triangles]).encode())
                row['evaluated_mesh_sha256'] = digest.hexdigest()
                mw = ev.matrix_world
                world = [blender_to_runtime(tuple(mw @ v.co)) for v in mesh.vertices]
                tris = [tuple(world[i] for i in t) for t in tri_index]
                if world:
                    record = {'name': obj.name, 'ident': str(obj.get('bakeId', obj.name)), 'tris': tris,
                              'aabb': (tuple(min(p[i] for p in world) for i in range(3)),
                                       tuple(max(p[i] for p in world) for i in range(3)))}
        finally:
            ev.to_mesh_clear()
    return row, record


def fingerprint_and_geometry(objects, depsgraph):
    """Fingerprint every pre-existing object and collect its evaluated triangles."""
    rows, records = {}, []
    for obj in sorted(objects, key=lambda o: o.name):
        if obj.get(TAG):
            continue
        row, record = evaluate_object(obj, depsgraph)
        rows[obj.name] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        if record:
            records.append(record)
    return rows, SceneGeometry(records)


def fingerprint_changes(before, after):
    """Names whose fingerprint changed, disappeared, or appeared untagged."""
    changed = sorted(n for n in before if before[n] != after.get(n))
    added = sorted(n for n in after if n not in before)
    return {'changed_or_removed': changed, 'unexpected_new': added}


def additive_export_objects(objects):
    """Only objects we created: tagged AND linked to the dedicated collection."""
    return sorted((o for o in objects if o.get(TAG)
                   and COLLECTION in [c.name for c in getattr(o, 'users_collection', ())]),
                  key=lambda o: o.name)


# ----------------------------------------------------------------------------
# Blender build (runs only inside Blender)
# ----------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(description='SUB-01 additive reference dressing')
    p.add_argument('--spec', type=Path, default=SPEC_PATH)
    p.add_argument('--assets-root', type=Path, default=ROOT / 'web/house/assets')
    p.add_argument('--output-dir', type=Path, default=None)
    p.add_argument('--dry-run', action='store_true', help='planning estimate only, no placement')
    p.add_argument('--list-identifiers', action='store_true',
                   help='read-only: print evaluated object identifiers, bounds and anchor matches')
    p.add_argument('--anchors', type=Path, default=None, help='JSON {anchor: [identifier prefixes]}')
    p.add_argument('--export-additive-glb', action='store_true',
                   help='export ONLY the new dressing objects to reference-dressing.glb')
    p.add_argument('--save-blend-copy', action='store_true',
                   help='also save house-dressed.blend as a copy (the input file is never overwritten)')
    p.add_argument('--allow-unassembled', action='store_true',
                   help='skip the homeVersion==114 assembled-house guard')
    return p.parse_args(argv)


def _blender_argv():
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]


def _srgb(hex_color):
    vals = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in vals) + (1.0,)


def _material(name, finish, assets_root, missing):
    mat = bpy.data.materials.new(NAME_PREFIX + name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    tint = _srgb(finish['tint'])
    shader.inputs['Base Color'].default_value = tint
    shader.inputs['Roughness'].default_value = finish.get('roughness', .8)
    if 'Sheen Weight' in shader.inputs and finish.get('sheen'):
        shader.inputs['Sheen Weight'].default_value = finish['sheen']
    for socket in ('Coat Weight', 'Clearcoat'):
        if finish.get('coat') and socket in shader.inputs:
            shader.inputs[socket].default_value = finish['coat']
    mat.diffuse_color = tint
    folder = finish.get('texture')
    if folder:
        base = assets_root / folder
        coords = nodes.new('ShaderNodeTexCoord')
        mapping = nodes.new('ShaderNodeMapping')
        repeat = finish.get('repeat_per_m', 1.0)
        mapping.inputs['Scale'].default_value = (repeat, repeat, 1)
        links.new(coords.outputs['UV'], mapping.inputs['Vector'])

        def image(file, colorspace):
            path = base / file
            if not path.is_file():
                missing.append(str(path))
                return None
            node = nodes.new('ShaderNodeTexImage')
            # Load a NEW datablock (never reuse an existing image the home uses).
            node.image = bpy.data.images.load(str(path.resolve()), check_existing=False)
            node.image.name = NAME_PREFIX + folder + '_' + file
            node.image.colorspace_settings.name = colorspace
            links.new(mapping.outputs['Vector'], node.inputs['Vector'])
            return node
        diff = image('diff.jpg', 'sRGB')
        if diff:
            mul = nodes.new('ShaderNodeMixRGB')
            mul.blend_type = 'MULTIPLY'
            mul.inputs[0].default_value = 1
            mul.inputs[2].default_value = tint
            links.new(diff.outputs['Color'], mul.inputs[1])
            links.new(mul.outputs['Color'], shader.inputs['Base Color'])
        nor = image('normal.jpg', 'Non-Color')
        if nor:
            nmap = nodes.new('ShaderNodeNormalMap')
            nmap.inputs['Strength'].default_value = finish.get('normal_strength', .35)
            links.new(nor.outputs['Color'], nmap.inputs['Color'])
            links.new(nmap.outputs['Normal'], shader.inputs['Normal'])
    mat[TAG] = True
    return mat


def _mesh_object(name, verts, faces, uvs, material, collection):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    layer = mesh.uv_layers.new(name='UVMap')
    for poly, face_uvs in zip(mesh.polygons, uvs):
        for k in range(poly.loop_total):
            layer.data[poly.loop_start + k].uv = face_uvs[k]
    mesh.validate()
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    collection.objects.link(obj)
    return obj


def _soft(obj, displace_texture, strength=.003, levels=1):
    sub = obj.modifiers.new('Soft subdivision', 'SUBSURF')
    sub.levels = sub.render_levels = levels
    disp = obj.modifiers.new('Fabric relief', 'DISPLACE')
    disp.texture = displace_texture
    disp.texture_coords = 'LOCAL'
    disp.strength = strength
    disp.mid_level = .5


def _bevel(obj, width, segments=3):
    mod = obj.modifiers.new('Edge bevel', 'BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    return mod


def _piping(name, loop, material, collection, radius=.0035):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new('POLY')
    spline.points.add(len(loop) - 1)
    for p, co in zip(spline.points, loop):
        p.co = (co[0], co[1], co[2], 1)
    spline.use_cyclic_u = True
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(material)
    collection.objects.link(obj)
    return obj


def build_item(item, mats, tex, collection):
    """Create the item's parts as children of one empty named object_name(item)."""
    name = object_name(item)
    root = bpy.data.objects.new(name, None)
    collection.objects.link(root)
    w, d, h = item['dims_m']
    p = item.get('params', {})
    parts = []
    kind = item['kind']
    mat = mats[item['material']]
    if kind == 'throw_pillow':
        v, f, uv, seam = pillow_mesh(w, d, h, pinch=p.get('pinch', .07), sag=p.get('sag', .012))
        parts.append(_mesh_object(name + '_cover', v, f, uv, mat, collection))
        _soft(parts[-1], tex, strength=.0025)
        piping = mats.get(item.get('piping_material', item['material']), mat)
        parts.append(_piping(name + '_piping', seam, piping, collection))
    elif kind == 'draped_throw':
        t = p.get('thickness', .012)
        layers = [(w, p['top_width'], p['drop'], p.get('radius', .03), 0.0)]
        for k in range(p.get('fold_layers', 0)):    # stacked fold edge of a folded throw
            layers.append((w * (1 - .04 * (k + 1)), p['top_width'] + 2 * t * (k + 1),
                           max(p['drop'] * (.55 - .1 * k), p.get('radius', .03) + t * (k + 1)),
                           p.get('radius', .03) + t * (k + 1), t * (k + 1)))
        for k, (lw, tw, drop, radius, lift) in enumerate(layers):
            v, f, uv = draped_strip_mesh(lw, tw, drop, radius)
            obj = _mesh_object(f'{name}_fabric{k}', [(x, y, z + lift) for x, y, z in v], f, uv, mat, collection)
            sol = obj.modifiers.new('Fabric thickness', 'SOLIDIFY')
            sol.thickness, sol.offset, sol.use_rim = t, 1.0, True
            _soft(obj, tex, strength=.004)
            parts.append(obj)
    elif kind == 'book_stack':
        z = 0.0
        for k, book in enumerate(p['books']):
            bw, bd, bh = book['dims_m']
            off = book.get('offset', [0, 0])
            cover = _mesh_object(f'{name}_book{k + 1}_cover', *box_mesh(bw, bd, bh), mats[book['material']],
                                 collection)
            _bevel(cover, .0015, 2)
            pages = _mesh_object(f'{name}_book{k + 1}_pages', *box_mesh(bw - .006, bd - .004, bh - .004),
                                 mats['paper'], collection)
            cover.location = (off[0], off[1], z)
            pages.location = (off[0] + .003, off[1], z + .002)
            for o in (cover, pages):
                o.rotation_euler[2] = math.radians(book.get('yaw_deg', 0))
            parts += [cover, pages]
            z += bh
    elif kind == 'vase_with_stems':
        vase = _mesh_object(name + '_vase', *lathe_mesh(VASE_PROFILE), mat, collection)
        sub = vase.modifiers.new('Ceramic smooth', 'SUBSURF')
        sub.levels = sub.render_levels = 1
        parts.append(vase)
        for k, (lean, turn, length) in enumerate(p.get('stems', [])):
            curve = bpy.data.curves.new(f'{name}_stem{k + 1}', 'CURVE')
            curve.dimensions, curve.bevel_depth = '3D', .0016
            spline = curve.splines.new('POLY')
            spline.points.add(5)
            for s, pt in enumerate(spline.points):
                u = s / 5
                r = math.sin(math.radians(lean)) * length * u * u
                pt.co = (r * math.cos(math.radians(turn)), r * math.sin(math.radians(turn)),
                         .20 + length * u * math.cos(math.radians(lean) * u), 1)
            stem = bpy.data.objects.new(f'{name}_stem{k + 1}', curve)
            stem.data.materials.append(mats['dried_stem'])
            collection.objects.link(stem)
            parts.append(stem)
    elif kind == 'canister':
        body_h = h - CANISTER_LID_M
        body = _mesh_object(name + '_body', *lathe_mesh(canister_profile(w / 2 - .002, body_h)), mat, collection)
        sub = body.modifiers.new('Ceramic smooth', 'SUBSURF')
        sub.levels = sub.render_levels = 1
        lid = _mesh_object(name + '_lid', *lathe_mesh(canister_lid_profile(w / 2 - .002)), mats['oak'],
                           collection)
        lid.location.z = body_h
        parts += [body, lid]
    else:
        raise ValueError(f'unknown kind {kind}')
    for part in parts:
        part.parent = root
    root.location = runtime_to_blender(item['position_runtime_m'])
    root.rotation_euler = (math.radians(item.get('tilt_deg', 0)), 0.0, math.radians(item.get('yaw_deg', 0)))
    for obj in [root] + parts:
        obj[TAG] = True
        obj['dressingSpecId'] = item['id']
        obj['bakeId'] = 'house-refdress-' + obj.name[len(NAME_PREFIX):]
    return root, parts


def _load_anchors(path):
    if not path:
        return dict(DEFAULT_ANCHORS)
    data = json.loads(Path(path).read_text())
    if not all(isinstance(v, list) and all(isinstance(s, str) and s for s in v) for v in data.values()):
        raise ValueError('anchors file must map anchor names to lists of identifier prefixes')
    return {**DEFAULT_ANCHORS, **data}


def run(argv=None):
    args = parse_args(_blender_argv() if argv is None else argv)
    spec = load_spec(args.spec)
    if args.dry_run or bpy is None:
        report = plan_dressing(spec)
        report['mode'] = 'dry-run (planning estimate; nothing placed)' if args.dry_run else \
            'pure-python (bpy unavailable; planning estimate only)'
        _emit(report, args.output_dir)
        return report

    scene = bpy.context.scene
    anchors = _load_anchors(args.anchors)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    existing = [o for o in scene.objects if not o.get(TAG)]
    before, geometry = fingerprint_and_geometry(existing, depsgraph)

    if args.list_identifiers:
        report = {'mode': 'list-identifiers (read-only)', 'objects': [
            {'name': r['name'], 'ident': r['ident'], 'triangles': len(r['tris']),
             'aabb_runtime': [list(map(_r, r['aabb'][0])), list(map(_r, r['aabb'][1]))]}
            for r in geometry.records],
            'anchors': {k: sorted(r['ident'] for r in geometry.matching(v)) for k, v in anchors.items()},
            'collections': sorted(c.name for c in bpy.data.collections),
            'materials': sorted(m.name for m in bpy.data.materials),
            'home_version': scene.get('homeVersion'), 'existing_objects': len(before)}
        _emit(report, args.output_dir, 'reference-dressing-identifiers.json')
        return report

    if scene.get('homeVersion') != 114 and not args.allow_unassembled:
        raise RuntimeError('Open the assembled house.blend (homeVersion 114) or pass --allow-unassembled')
    if bpy.data.collections.get(COLLECTION):
        raise RuntimeError(f'{COLLECTION} already exists; start from the untouched assembled house.blend')

    context = evaluated_context(geometry, anchors)
    accepted, rejected = place_on_evaluated_home(spec, geometry, anchors, context)
    for skip in sorted(spec.get('skipped_existing', []), key=lambda s: s['id']):
        rejected.append({'id': skip['id'], 'name': None, 'room': skip['room'], 'kind': 'skip',
                         'reasons': [f'duplicate:existing:{skip["evidence"]}']})

    collection = bpy.data.collections.new(COLLECTION)
    scene.collection.children.link(collection)
    missing = []
    mats = {k: _material(k, v, args.assets_root, missing) for k, v in sorted(spec['materials'].items())}
    tex = bpy.data.textures.new(NAME_PREFIX + 'FabricRelief', 'CLOUDS')
    tex.noise_scale = .045
    built = []
    for item in accepted:
        root, parts = build_item(item, mats, tex, collection)
        built.append({'id': item['id'], 'name': root.name, 'parts': sorted(p.name for p in parts),
                      'position_runtime_m': [_r(v) for v in item['position_runtime_m']],
                      'support': item.get('support_evidence')})

    bpy.context.view_layer.update()
    after, _ = fingerprint_and_geometry([o for o in scene.objects if not o.get(TAG)],
                                        bpy.context.evaluated_depsgraph_get())
    diff = fingerprint_changes(before, after)
    if diff['changed_or_removed'] or diff['unexpected_new']:
        raise RuntimeError('Existing home changed during dressing; nothing saved/exported: ' + json.dumps(diff))
    report = {'mode': 'blender', 'collection': COLLECTION, 'basis': 'evaluated-geometry',
              'built': built, 'rejected': rejected, 'missing_anchors': context['missing_anchors'],
              'missing_textures': sorted(set(missing)), 'existing_objects_verified_unchanged': len(before),
              'existing_fingerprint_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
              'rendered': False, 'private_only': True}
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.export_additive_glb:
            ours = additive_export_objects(scene.objects)
            selected = {o.name for o in scene.objects if o.select_get()}
            active = bpy.context.view_layer.objects.active
            for obj in scene.objects:
                obj.select_set(obj in ours)
            glb = args.output_dir / 'reference-dressing.glb'
            bpy.ops.export_scene.gltf(filepath=str(glb.resolve()), export_format='GLB', use_selection=True,
                                      export_yup=True, export_extras=True, export_apply=True,
                                      export_lights=False, export_cameras=False)
            for obj in scene.objects:          # restore the user's selection exactly
                obj.select_set(obj.name in selected)
            bpy.context.view_layer.objects.active = active
            report['additive_glb'] = {'path': str(glb), 'objects': [o.name for o in ours],
                                      'sha256': hashlib.sha256(glb.read_bytes()).hexdigest()}
        if args.save_blend_copy:
            blend = args.output_dir / 'house-dressed.blend'
            bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()), copy=True)
            report['blend_copy'] = str(blend)
        final, _ = fingerprint_and_geometry([o for o in scene.objects if not o.get(TAG)],
                                            bpy.context.evaluated_depsgraph_get())
        if fingerprint_changes(before, final) != {'changed_or_removed': [], 'unexpected_new': []}:
            raise RuntimeError('Existing home changed during export')
    _emit(report, args.output_dir)
    return report


def _emit(report, output_dir, filename='reference-dressing.json'):
    text = json.dumps(report, indent=2, sort_keys=False)
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / filename).write_text(text + '\n')
    print('SUB01_REFERENCE_DRESSING', json.dumps(report), flush=True)


if __name__ == '__main__':
    run()
