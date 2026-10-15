"""Portable GLB hierarchy authentication, independent of repository ROOT assets."""
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import verified_owner_skeleton as owner
import unreal_import_gaming_grip as grip


def fixture(project, monkeypatch, mutate=None):
    nodes = [{'name': 'mixamorig:Hips', 'children': [1]}]
    nodes += [{'name': f'mixamorig:Bone{i}', **({'children': [i + 1]} if i < 64 else {})} for i in range(1, 65)]
    doc = {'asset': {'version': '2.0'}, 'nodes': nodes, 'skins': [{'joints': list(range(65))}]}
    if mutate:
        mutate(doc)
    encoded = json.dumps(doc).encode()
    encoded += b' ' * (-len(encoded) % 4)
    blob = struct.pack('<4sIIII', b'glTF', 2, 20 + len(encoded), len(encoded), 0x4E4F534A) + encoded
    p = project / owner.PORTABLE_OWNER
    p.parent.mkdir(parents=True)
    p.write_bytes(blob)
    monkeypatch.setattr(owner, 'PORTABLE_OWNER_SHA256', hashlib.sha256(blob).hexdigest())
    return p


def test_portable_authentic_tree_used_without_root_asset(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    parents = grip.owner_parents_default(tmp_path)
    assert len(parents) == 65 and sum(p is not None for p in parents.values()) == 64
    assert parents['mixamorig:Hips'] is None and parents['mixamorig:Bone64'] == 'mixamorig:Bone63'


def test_changed_actual_bytes_refused(tmp_path, monkeypatch):
    p = fixture(tmp_path, monkeypatch)
    p.write_bytes(p.read_bytes() + b'bad')
    with pytest.raises(RuntimeError, match='differs'):
        owner.read_project_owner_parents(tmp_path)


@pytest.mark.parametrize('mutate', [
    lambda d: d['skins'][0]['joints'].pop(),
    lambda d: d['nodes'][64].update(children=[0]),
    lambda d: d['nodes'][0].update(children=[1, 2]),
    lambda d: d['nodes'][10].update(name='wrong-owner'),
])
def test_incomplete_cyclic_reparented_or_wrong_name_refused(tmp_path, monkeypatch, mutate):
    fixture(tmp_path, monkeypatch, mutate)
    with pytest.raises(RuntimeError):
        owner.read_project_owner_parents(tmp_path)
