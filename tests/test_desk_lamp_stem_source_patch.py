import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from desk_lamp_stem_source_patch import select_stem, union_remainder_selection


def row(triangles, total=1840):
    return {'source_node_index': 163, 'primitive_index': 0,
            'source_primitive_triangle_count': total,
            'triangle_indices': triangles, 'selected_triangle_count': len(triangles)}


def test_union_preserves_actual_nonrail_fixture_range_without_duplicate_remainder():
    rails = [row(list(range(1640)))]
    stem = row(list(range(1800, 1840)))
    result = union_remainder_selection(rails, stem)
    assert len(result) == 1
    assert result[0]['removed_triangle_count'] == 1680
    assert result[0]['preserved_triangle_count'] == 160
    assert set(range(1840)) - set(result[0]['triangle_indices']) == set(range(1640, 1800))


def test_overlapping_component_selection_is_rejected():
    with pytest.raises(ValueError, match='overlap'):
        union_remainder_selection([row([1800])], row([1800, 1801]))


def test_mismatched_or_out_of_bounds_source_triangle_stream_is_rejected():
    with pytest.raises(ValueError, match='counts differ'):
        union_remainder_selection([row([0], 1840)], row([1], 1841))
    with pytest.raises(ValueError, match='Invalid'):
        union_remainder_selection([], row([1840]))


def test_stale_source_refused_before_reading_mesh():
    with pytest.raises(ValueError, match='identity differs'):
        select_stem({}, b'', '912662-stale-local-source')
