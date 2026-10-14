import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_real_shelf_books as books
from real_furniture_base import BaseRefusedError, verify_base


def test_books_resolve_scoped_helpers_without_new_dressing_module_revision():
    assert callable(books.verify_base) and callable(books.sha256_file) and callable(books.glb_json)


def test_native_base_requires_matching_source_and_geometry_sidecar(tmp_path):
    blend = tmp_path / 'house.blend'
    blend.write_bytes(b'private source base')
    blend.with_suffix('.json').write_text(json.dumps({
        'schema': 'sub01.native-dressing-base.v1', 'source_sha256': 'actual-source',
        'mesh_objects': 10, 'vertices': 100,
    }))
    scene = {'sub01NativeSourceSha256': 'actual-source', 'privateOnly': True}
    assert verify_base(scene, str(blend), True, (10, 100), 'actual-source')['basis'] == 'native-dressing-base'
    with pytest.raises(BaseRefusedError, match='differ from the sidecar'):
        verify_base(scene, str(blend), True, (11, 100), 'actual-source')
    with pytest.raises(BaseRefusedError, match='mismatch'):
        verify_base(scene, str(blend), True, (10, 100), 'wrong-source')
