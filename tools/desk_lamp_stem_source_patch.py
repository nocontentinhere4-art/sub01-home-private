"""Pure exact legacy lamp-stem selection; share one remainder with rail edits.

No mesh is hidden or written here. The renderer must build the remainder once
from the union returned by this helper, preserving every other source triangle.
"""
from structural_rail_source_patch import accessor, select, transformed, world_matrices

SOURCE_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
STEM = {'name': 'legacy white desk lamp stem', 'a': [1.1, .85, -3.15],
        'b': [1.1, 1.3, -3.15], 'radius': .014}


def select_stem(doc, binary, source_sha):
    if source_sha != SOURCE_SHA:
        raise ValueError('Actual source identity differs; do not use stale geometry')
    rows, errors = select(doc, binary, [STEM])
    if errors or len(rows) != 1:
        raise ValueError('Lamp stem must match exactly one connected component: ' + str(errors))
    row = rows[0]
    if (row['source_node_index'], row['primitive_index'], row['material_index']) != (163, 0, 8):
        raise ValueError('Reviewed lamp component identity differs')
    primitive = doc['meshes'][doc['nodes'][163]['mesh']]['primitives'][0]
    positions = accessor(doc, binary, primitive['attributes']['POSITION'])
    indices = [v[0] for v in accessor(doc, binary, primitive['indices'])]
    vertices = sorted({i for t in row['triangle_indices'] for i in indices[3*t:3*t+3]})
    matrix = world_matrices(doc)[163]
    points = [transformed(matrix, positions[i]) for i in vertices]
    row['source_world_bounds_m'] = [[min(p[i] for p in points) for i in range(3)],
                                   [max(p[i] for p in points) for i in range(3)]]
    row['selected_vertex_count'] = len(vertices)
    return row


def union_remainder_selection(rail_rows, stem_row):
    """Return one triangle-set per source primitive, with explicit conservation.

    Pass all rail selections and the exact stem once. Never import a standalone
    old rail remainder alongside this union: that would restore the old stem.
    """
    groups = {}
    for row in [*rail_rows, stem_row]:
        key = (row['source_node_index'], row['primitive_index'])
        total = row['source_primitive_triangle_count']
        selected = set(row['triangle_indices'])
        if len(selected) != row['selected_triangle_count'] or any(t < 0 or t >= total for t in selected):
            raise ValueError('Invalid source triangle selection')
        group = groups.setdefault(key, {'source_node_index': key[0], 'primitive_index': key[1],
                                       'source_triangle_count': total, 'triangle_indices': set()})
        if group['source_triangle_count'] != total:
            raise ValueError('Source primitive counts differ')
        if group['triangle_indices'] & selected:
            raise ValueError('Selections overlap; reject duplicate component removal')
        group['triangle_indices'].update(selected)
    result = []
    for key in sorted(groups):
        row = groups[key]
        row['triangle_indices'] = sorted(row['triangle_indices'])
        row['removed_triangle_count'] = len(row['triangle_indices'])
        row['preserved_triangle_count'] = row['source_triangle_count'] - row['removed_triangle_count']
        result.append(row)
    return result
