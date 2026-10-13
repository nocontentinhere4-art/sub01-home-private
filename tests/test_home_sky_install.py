import json
import pytest
from tools.install_home_indirect import digest, validate_combined_day, local_file

@pytest.fixture
def bundle(tmp_path):
    base=dict(finished=True,mode='day',source_sha256='geometry',atlas_sha256='atlas',samples=512,
              threads=4,seed=0,adaptive_sampling=False,denoising=False,receivers=103,width=1378,height=1379,
              direct=False,indirect=True,surface_albedo=False)
    parts=[]
    for role in ('indirect','sky-direct'):
        folder=tmp_path/'components'/role;folder.mkdir(parents=True)
        raw=folder/'indirect.exr';raw.write_bytes(role.encode())
        record=dict(base,output_sha256=digest(raw))
        if role=='sky-direct':record.update(direct=True,indirect=False,world_only=True,
                                            emissive_materials_disabled=True,world_rgb=[.76,.84,1.],world_strength=.12)
        path=folder/'bake.json';path.write_text(json.dumps(record))
        parts.append(dict(role=role,manifest_file=str(path.relative_to(tmp_path)),raw_file=str(raw.relative_to(tmp_path)),
                          manifest_sha256=digest(path),raw_sha256=digest(raw)))
    return tmp_path,dict(base,direct=True,combined_world_sky=True,sum_verified=True,components=parts)

def test_finished_component_bundle_is_matched(bundle):
    folder,record=bundle
    assert len(validate_combined_day(folder,record))==2

@pytest.mark.parametrize('kind',['manifest','raw'])
def test_component_file_tampering_rejected_before_install(bundle,kind):
    folder,record=bundle
    path=folder/record['components'][1][kind+'_file']
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):validate_combined_day(folder,record)

def test_updated_hash_cannot_hide_duplicate_indirect_or_geometry_change(bundle):
    folder,record=bundle;component=record['components'][1];path=folder/component['manifest_file']
    source=json.loads(path.read_text());source['indirect']=True;path.write_text(json.dumps(source));component['manifest_sha256']=digest(path)
    with pytest.raises(ValueError,match='duplicated'):validate_combined_day(folder,record)
    source['indirect']=False;source['atlas_sha256']='other';path.write_text(json.dumps(source));component['manifest_sha256']=digest(path)
    with pytest.raises(ValueError,match='atlas'):validate_combined_day(folder,record)

def test_component_path_cannot_escape_or_duplicate_roles(bundle):
    folder,record=bundle
    with pytest.raises(ValueError,match='escapes'):local_file(folder,'../external.exr')
    record['components'][1]['role']='indirect'
    with pytest.raises(ValueError,match='exactly'):validate_combined_day(folder,record)
