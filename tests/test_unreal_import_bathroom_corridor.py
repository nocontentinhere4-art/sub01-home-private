import shutil
from pathlib import Path
import pytest
import unreal_import_bathroom_corridor as importer

SOURCE=Path(__file__).resolve().parents[1]/'docs/proposed/bathroom-corridor-source'


def test_actual_frozen_contract_and_all_nine_world_sources():
    contract,proof=importer.load_contract(SOURCE)
    triangles=importer.source_triangles((SOURCE/'bath-corridor.glb').read_bytes())
    assert list(triangles)==list(importer.NODES)
    assert sum(map(len,triangles.values()))==876
    assert contract['owned_geometry_triangles']==proof['source_triangle_count']==876
    lo,hi=importer.bounds(triangles[118])
    assert lo==pytest.approx([-103.25,90.5,305],abs=.0001)
    assert hi==pytest.approx([-96.75,179.5,505],abs=.0001)
    lo,hi=importer.bounds(triangles[117])
    assert lo[0]==pytest.approx(-385,abs=.0001)
    assert hi[0]==pytest.approx(-95,abs=.0001)


def test_tampered_geometry_is_refused_before_editor_calls(tmp_path):
    for p in SOURCE.iterdir():shutil.copy2(p,tmp_path/p.name)
    p=tmp_path/'bath-corridor.glb';p.write_bytes(p.read_bytes()+b'bad')
    with pytest.raises(RuntimeError,match='artifact changed'):importer.load_contract(tmp_path)


def test_tampered_acceptance_contract_is_refused(tmp_path):
    for p in SOURCE.iterdir():shutil.copy2(p,tmp_path/p.name)
    p=tmp_path/'accepted-source-contract.json';p.write_text(p.read_text().replace('"native_imported": false','"native_imported": true'))
    with pytest.raises(RuntimeError,match='accepted corridor source contract'):importer.load_contract(tmp_path)


def test_native_surface_check_rejects_lost_wall_face_and_real_displacement():
    triangles=importer.source_triangles((SOURCE/'bath-corridor.glb').read_bytes())[158]
    assert not importer.same_triangles(triangles,triangles[:-1],.001)
    displaced=[[list(p)for p in t]for t in triangles]
    displaced[0][0][0]+=.02
    assert not importer.same_triangles(triangles,displaced,.001)
