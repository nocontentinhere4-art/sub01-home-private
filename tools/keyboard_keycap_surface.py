"""CPU point queries against actual authored keyboard surface triangles.

Coordinates are UE centimetres. This is a point-vs-height surface query, NOT
full finger/triangle collision: a finger has volume and can hit cap side walls.
Default queries use the extracted top faces only. include_bevels=True evaluates
all cap triangles and returns their highest projected surface, including bevels.
"""
import json
from pathlib import Path


def projected_triangle_z(x, y, triangle, edge_tolerance_cm=1e-5):
    """Return interpolated Z inside triangle XY projection, or None.

    Edge tolerance is converted to a barycentric tolerance using the shortest
    projected altitude. Degenerate/vertical faces have no height-field interior.
    """
    a, b, c = triangle
    denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(denominator) < 1e-10:
        return None
    lengths = [((p[0]-q[0])**2+(p[1]-q[1])**2)**.5 for p, q in [(a,b),(b,c),(c,a)]]
    shortest_altitude = abs(denominator) / max(lengths)
    tolerance = edge_tolerance_cm / shortest_altitude
    wa = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
    wb = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
    wc = 1-wa-wb
    if min(wa, wb, wc) < -tolerance or max(wa, wb, wc) > 1+tolerance:
        return None
    return wa*a[2]+wb*b[2]+wc*c[2]


class KeyboardSurface:
    def __init__(self, path):
        self.source = json.loads(Path(path).read_text())
        self.vertices = self.source['verticesUECm']
        self.keycaps = self.source['keycaps']

    def height_at(self, x, y, include_bevels=False, edge_tolerance_cm=1e-5):
        highest = None
        for key in self.keycaps:
            lo, hi = key['minCm'], key['maxCm']
            if not (lo[0]-edge_tolerance_cm <= x <= hi[0]+edge_tolerance_cm and
                    lo[1]-edge_tolerance_cm <= y <= hi[1]+edge_tolerance_cm):
                continue
            triangles = ([[self.vertices[i] for i in tri] for tri in key['trianglesUEVertexIds']]
                         if include_bevels else key['topTrianglesUECm'])
            for triangle in triangles:
                z = projected_triangle_z(x, y, triangle, edge_tolerance_cm)
                if z is not None and (highest is None or z > highest['zCm']):
                    highest = {'keycapId': key['keycapId'], 'zCm': z,
                               'scope': 'cap-upper-envelope-including-bevel' if include_bevels else 'extracted-top-face'}
        return highest
