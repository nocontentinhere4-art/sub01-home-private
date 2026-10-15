"""Match native kitchen surfaces; report only sub-float-precision discarded faces.

Unreal discarded twelve numerically collapsed CAD faces in the measured Mesh11.
This does not permit missing resolvable surfaces, extra native triangles, changed
placement or using zero-area padding as physical contact.
"""
import itertools
import math


def area(triangle):
    a, b = [[triangle[n][k]-triangle[0][k] for k in range(3)] for n in (1, 2)]
    return math.sqrt(sum(x*x for x in (a[1]*b[2]-a[2]*b[1],
                                     a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])))/2


def compare(source, actual, tolerance_cm=.0001):
    for group in (source, actual):
        if any(len(t) != 3 or any(len(p) != 3 or not all(map(math.isfinite, p)) for p in t) for t in group):
            raise ValueError('Nonfinite/incomplete kitchen surface')
    cell = .05
    def key(triangle):
        return tuple(math.floor(sum(p[k] for p in triangle)/3/cell) for k in range(3))
    buckets = {}
    for i, triangle in enumerate(actual):
        buckets.setdefault(key(triangle), set()).add(i)
    discarded, matched = [], 0
    # Consume resolvable surfaces first; coincident padding may not steal them.
    for i in sorted(range(len(source)), key=lambda i: area(source[i]), reverse=True):
        triangle, found, best = source[i], None, math.inf
        center = key(triangle)
        for offset in itertools.product((-1, 0, 1), repeat=3):
            bucket = buckets.get(tuple(a+b for a, b in zip(center, offset)), set())
            for j in bucket:
                for order in itertools.permutations(actual[j]):
                    distances = [math.dist(a, b) for a, b in zip(triangle, order)]
                    score = sum(x*x for x in distances)
                    if max(distances) <= tolerance_cm and score < best:
                        found, best = (bucket, j), score
        if found:
            found[0].remove(found[1])
            matched += 1
            continue
        longest = max(math.dist(a, b) for a, b in itertools.combinations(triangle, 2))
        height = 2*area(triangle)/longest if longest else 0.
        # Four float32 coordinate roundoffs, expressed in native centimetres.
        bound = 4*2**-23*max(1., *(abs(v) for p in triangle for v in p))
        if height > bound:
            raise ValueError('Native kitchen lost a resolvable source surface '+str(i))
        discarded.append({'source_triangle': i, 'area_cm2': area(triangle),
                          'minimum_height_cm': height, 'float32_roundoff_bound_cm': bound})
    if matched != len(actual):
        raise ValueError('Native kitchen contains extra/unmatched surface triangles')
    return {'source_triangles': len(source), 'native_triangles': len(actual),
            'all_native_triangles_matched': True, 'tolerance_cm': tolerance_cm,
            'discarded_subprecision_faces': discarded,
            'discarded_faces_are_contact_surfaces': False}


def native_triangles(u, component):
    mesh, world = component.get_editor_property('static_mesh'), component.get_world_transform()
    result = []
    for section in range(mesh.get_num_sections(0)):
        verts, ids, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
        if len(ids) % 3:
            raise ValueError('Partial native kitchen triangle')
        pts = [world.transform_location(p) for p in verts]
        points = [[float(p.x), float(p.y), float(p.z)] for p in pts]
        result.extend([[points[k] for k in ids[i:i+3]] for i in range(0, len(ids), 3)])
    return result
