"""An original Nanite fallback cannot certify full source geometry or be edited."""
import sys,types
from pathlib import Path
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_reference_bedding import audit_original_full_source

@pytest.fixture
def scene(monkeypatch):
 original=Mock();original.get_name.return_value='CC0_queen_3';original.get_path_name.return_value='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/CC0_queen_3.CC0_queen_3'
 clone=Mock();clone.get_path_name.return_value='/Game/Sub01Home/ReferenceBedding/OriginalSourceAudit/owned/CC0_queen_3.CC0_queen_3'
 settings=Mock();settings.get_editor_property.side_effect=lambda key:True if key=='enabled'else 1.
 sub=Mock();sub.get_nanite_settings.return_value=settings
 component=Mock();component.get_editor_property.return_value=original
 temporary_component=Mock();actor=Mock();actor.get_component_by_class.return_value=temporary_component
 eas=Mock();eas.spawn_actor_from_class.return_value=actor;eas.destroy_actor.return_value=True
 u=Mock();u.get_editor_subsystem.return_value=sub;u.EditorAssetLibrary.duplicate_asset.return_value=clone;u.Sub01HomeHandsInstance.finish_pending_static_compilation.return_value=0
 triangles=Mock(side_effect=lambda _u,c:['coarse']if c is component else ['full'])
 same=Mock(side_effect=lambda a,b,tolerance:a==b)
 rebuild=Mock()
 monkeypatch.setitem(sys.modules,'unreal_remove_frame_backings',types.SimpleNamespace(native_triangles=triangles,same_triangles=same))
 monkeypatch.setitem(sys.modules,'unreal_import_real_wc',types.SimpleNamespace(owned_geometry=rebuild))
 return types.SimpleNamespace(u=u,eas=eas,component=component,original=original,clone=clone,actor=actor,triangles=triangles,rebuild=rebuild)

def test_clone_audits_full_surface_without_changing_original_binding(scene):
 s=scene;r=audit_original_full_source(s.u,s.eas,s.component,['full'],263,True)
 assert r['original_nanite_settings_unchanged'] and r['full_source_clone_triangles']==1
 assert s.rebuild.call_args.args[1]is s.clone
 s.component.set_static_mesh.assert_not_called();s.eas.destroy_actor.assert_called_once_with(s.actor)

def test_mismatching_full_clone_refuses_and_removes_temporary_actor(scene):
 s=scene
 with pytest.raises(RuntimeError,match='Full-source clone geometry differs'):
  audit_original_full_source(s.u,s.eas,s.component,['not-the-source'],263,True)
 s.eas.destroy_actor.assert_called_once_with(s.actor);s.component.set_static_mesh.assert_not_called()

def test_read_only_preflight_never_duplicates_or_rebuilds_assets(scene):
 s=scene
 with pytest.raises(RuntimeError,match='owned full-source clone audit'):
  audit_original_full_source(s.u,s.eas,s.component,['full'],263,False)
 s.u.EditorAssetLibrary.duplicate_asset.assert_not_called();s.rebuild.assert_not_called()

def test_wrong_original_asset_namespace_is_refused_before_clone(scene):
 s=scene;s.original.get_path_name.return_value='/Game/Unrelated/CC0_queen_3.CC0_queen_3'
 with pytest.raises(RuntimeError,match='Exact original textile asset binding'):
  audit_original_full_source(s.u,s.eas,s.component,['full'],263,True)
 s.u.EditorAssetLibrary.duplicate_asset.assert_not_called()
