import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from unreal_import_reference_footrest import validate_source, expected_by_material, verify_native_geometry

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'docs/proposed/upright-footrest-source/footrest-one-component.glb'


def test_frozen_real_source_is_complete_and_physically_placed():
    proof, doc, blob = validate_source(SOURCE)
    rows = expected_by_material(doc, blob)
    points = [p for triangles in rows.values() for t in triangles for p in t]
    assert len(rows) == len(doc['materials'])
    assert len(doc['meshes'][0]['primitives']) == 20
    assert min(p[2] for p in points) == pytest.approx(2.5, abs=.0001)
    assert max(p[2] for p in points) >= 14.7-.0001
    assert proof['native_imported'] is False


def test_forged_or_incomplete_source_proof_is_refused(tmp_path):
    target = tmp_path/SOURCE.name
    target.write_bytes(SOURCE.read_bytes())
    proof = json.loads(SOURCE.with_suffix('.json').read_text())
    proof['original_parts'] = 18
    target.with_suffix('.json').write_text(json.dumps(proof))
    with pytest.raises(RuntimeError, match='complete one-component'):
        validate_source(target)


def test_actual_section_slot_lookup_preserves_material_assignment():
    # Native sections are deliberately reversed relative to material slots.
    # A sections==slots assumption would pass global geometry while swapping PBR.
    triangles = {'Wood': [[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]],
                 'Rubber': [[[0.,0.,2.],[1.,0.,2.],[0.,1.,2.]]]}
    asvec = lambda p: NS(x=p[0], y=p[1], z=p[2])
    mesh = NS(get_num_sections=lambda lod: 2)
    materials = [NS(get_name=lambda: 'Wood'), NS(get_name=lambda: 'Rubber')]
    transform = NS(transform_location=lambda v: v)
    component = NS(get_editor_property=lambda key: mesh, get_material=lambda slot: materials[slot],
                   get_world_transform=lambda: transform)
    section_slots = [1,0]
    editor = NS(get_lod_material_slot=lambda m,l,s: section_slots[s])
    def section(m,l,s):
        name = ['Rubber', 'Wood'][s]
        return [asvec(p) for p in triangles[name][0]], [0,1,2]
    u = NS(StaticMeshEditorSubsystem=object(), get_editor_subsystem=lambda t: editor,
           ProceduralMeshLibrary=NS(get_section_from_static_mesh=section))
    assert verify_native_geometry(u, component, triangles) == {'Wood':1,'Rubber':1}
    section_slots[:] = [0,1]
    with pytest.raises(RuntimeError, match='per-material'):
        verify_native_geometry(u, component, triangles)
