import hashlib

import pytest

from tools.unreal_import_reference_dressing import validate_receipt


def test_rejects_changed_export_and_unowned_objects_before_import(tmp_path):
    source = tmp_path / 'reference-dressing.glb'
    source.write_bytes(b'actual-export-fixture')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {'mode': 'blender', 'basis': 'evaluated-geometry',
              'existing_objects_verified_unchanged': 279, 'built': [{'id': 'pillow'}],
              'additive_glb': {'objects': ['SUB01_RefDress_pillow'], 'sha256': digest}}
    assert validate_receipt(report, source) == digest
    source.write_bytes(b'changed-after-geometry-audit')
    with pytest.raises(ValueError, match='differs'):
        validate_receipt(report, source)
    source.write_bytes(b'actual-export-fixture')
    report['additive_glb']['objects'].append('OriginalOfficeDesk')
    with pytest.raises(ValueError, match='outside'):
        validate_receipt(report, source)


def test_refuses_planning_only_or_empty_actual_build(tmp_path):
    source = tmp_path / 'reference-dressing.glb'
    source.write_bytes(b'anything')
    with pytest.raises(ValueError, match='successful real'):
        validate_receipt({'mode': 'dry-run', 'built': []}, source)
