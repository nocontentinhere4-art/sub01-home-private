"""Actual written FBX/UV contracts and refusal boundaries; no Unreal execution."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import unreal_import_fp_keyboard_review as review


def actual_reports():
    source=ROOT/'docs/proposed/upright-footrest-source'
    return [json.loads((source/name).read_text())for name in ('keyboard-review-fbx-roundtrip-r5.json','keyboard-review-fbx-uv-r1.json')]


def test_actual_written_fbx_and_bijective_uv_proof_pass_without_claiming_native_contact():
    report,uv=actual_reports()
    assert len(review.check_source(report,uv))==65
    assert report['fbx_sha256']==review.FBX_SHA
    assert report['keys']==409 and report['fps']==120
    assert uv['one_to_one_position_AND_UV_triangle_matches']==88592
    assert report['native_ready']is False and uv['native_ready']is False


@pytest.mark.parametrize(('field','value'),[
    ('fbx_sha256','other'),('arms_mesh_glb_sha256','other'),('derived_clip_sha256','other'),
    ('keys',408),('fps',30),('duration_s',3.3),('actual_roundtrip_curve_counts',[408,409]),
    ('actual_roundtrip_curves',658),('original_joints',64),('native_ready',True),
    ('all409_keys_all65_joint_heads_max_error_cm',float('nan')),
    ('original_source_material_slots',['tripo_material']),
])
def test_changed_source_contract_is_refused(field,value):
    report,uv=actual_reports();report[field]=value
    with pytest.raises(RuntimeError):review.check_source(report,uv)


def test_missing_joint_and_missing_triangle_probe_are_refused():
    report,uv=actual_reports();report['original_joint_names'][-1]=report['original_joint_names'][0]
    with pytest.raises(RuntimeError):review.check_source(report,uv)
    report,uv=actual_reports();report['FBX_roundtrip_skin_geometry'].pop()
    with pytest.raises(RuntimeError):review.check_source(report,uv)


@pytest.mark.parametrize(('field','value'),[
    ('fbx_sha256','other'),('one_to_one_position_AND_UV_triangle_matches',88591),
    ('all_source_and_target_triangles_used_once',False),('max_nearest_valid_uv_error',.01),
    ('max_nearest_valid_position_error_cm',float('nan')),('FBX_material_slots',['tripo_material']),
    ('native_ready',True),
])
def test_uv_or_material_substitution_is_refused(field,value):
    report,uv=actual_reports();uv[field]=value
    with pytest.raises(RuntimeError):review.check_source(report,uv)


class Slot:
    def __init__(self,name,material=None):self.fields={'material_slot_name':name,'material_interface':material}
    def get_editor_property(self,name):return self.fields[name]


def test_exact_original_material_slot_required_without_short_alias_or_ambiguity():
    slot=Slot(review.MATERIAL_SLOT)
    assert review.authentic_slot([slot])is slot
    for slots in [[],[Slot('tripo_material')],[slot,Slot(review.MATERIAL_SLOT)]]:
        with pytest.raises(RuntimeError):review.authentic_slot(slots)


def test_import_is_isolated_and_does_not_assign_runtime_or_save_original_assets():
    source=Path(review.__file__).read_text()
    assert "task.replace_existing=False;task.save=False"in source
    assert "('create_physics_asset',False)"in source
    assert "('import_materials',False)"in source
    assert "skin.set_editor_property('update_skeleton_reference_pose',False)"in source
    assert "skin.set_editor_property('use_t0_as_ref_pose',False)"in source
    assert "animation.set_editor_property('custom_sample_rate',120)"in source
    assert 'force_delete'not in source.lower().replace('force_delete_used','')
    assert 'save_directory'not in source and 'set_actor'not in source
    assert "for o in (mesh,clip):"in source
    assert "'native_triangle_count_verified':False"in source
    assert "'native_skin_and_UV_parity_accepted':False"in source
    assert "'native_ready':False"in source and "'activity_ready':False"in source


def test_empty_or_unfinished_actual_imported_skin_is_refused():
    for text in ['missing','editor-only','importedVertices=0 lods=1 softVertices=0 min=... max=...','importedVertices=8 lods=0 softVertices=8 min=... max=...']:
        with pytest.raises(RuntimeError):review.imported_geometry_counts(text)
    assert review.imported_geometry_counts('importedVertices=8 lods=1 softVertices=8 min=... max=...')=={'imported_vertices':8,'lods':1,'soft_vertices':8}
