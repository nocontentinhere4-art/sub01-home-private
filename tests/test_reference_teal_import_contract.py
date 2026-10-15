import hashlib,importlib.util,json
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('tealimport',Path(__file__).resolve().parents[1]/'tools/unreal_import_reference_teal_bathroom.py');M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

def test_unproved_source_never_reaches_native(tmp_path):
 p=tmp_path/'proof.json';p.write_text(json.dumps({'schema':'sub01.reference-teal-bathroom-independent-source.v1','source_ready':False}));(tmp_path/'source-report.json').write_text('{}')
 with pytest.raises(RuntimeError,match='Independent'):M.contract(tmp_path,p)

def packet(tmp_path,monkeypatch):
 original=tmp_path/'original.glb';original.write_bytes(b'exact original');monkeypatch.setattr(M,'ORIGINAL',original);monkeypatch.setattr(M,'BASE_SHA',M.digest(original));files={}
 for name in ['bath-style-fixtures.glb','bath-style-dressing.glb']:(tmp_path/name).write_bytes(name.encode());files[name]=M.digest(tmp_path/name)
 report={'source_sha256':M.BASE_SHA,'fixture_parts':90,'files':files};(tmp_path/'source-report.json').write_text(json.dumps(report))
 proof={'schema':'sub01.reference-teal-bathroom-independent-source.v1','source_ready':True,'native_imported':False,'native_visual_physical_accepted':False,'unresolved_positive_crossings':[],'wood_positive_triangles_with_collapsed_uvs':0,'fixture_corner_parity':{'ok':True,'matched_parts':90,'unmatched_styled_parts':0,'tolerance_cm':.0001,'rows':[{}]*90},'wood_uv':[{'all_positive_faces_have_uv_area':True}],'inputs':{str(tmp_path/name):sha for name,sha in files.items()}}
 path=tmp_path/'proof.json';path.write_text(json.dumps(proof));return path,proof

def test_bijective_corner_and_actual_file_receipts_required(tmp_path,monkeypatch):
 path,proof=packet(tmp_path,monkeypatch);M.contract(tmp_path,path)
 (tmp_path/'bath-style-fixtures.glb').write_bytes(b'changed after proof')
 with pytest.raises(RuntimeError,match='source changed'):M.contract(tmp_path,path)

@pytest.mark.parametrize('field,value',[('unresolved_positive_crossings',[{'part':'paint','obstacle':'metal'}]),('wood_positive_triangles_with_collapsed_uvs',1),('native_visual_physical_accepted',True)])
def test_no_ready_flag_can_override_real_geometry_or_uv_failures(tmp_path,monkeypatch,field,value):
 path,proof=packet(tmp_path,monkeypatch);proof[field]=value;path.write_text(json.dumps(proof))
 with pytest.raises(RuntimeError,match='Independent'):M.contract(tmp_path,path)
