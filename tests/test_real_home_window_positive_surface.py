import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_real_home_windows import positive_area_triangles


def test_only_exact_zero_surface_is_removed_and_indices_preserved():
    zero=[[1.,2.,3.],[1.,2.,3.],[4.,5.,6.]]
    collinear=[[0.,0.,0.],[1.,1.,1.],[2.,2.,2.]]
    positive=[[0.,0.,0.],[1.,0.,0.],[0.,1e-20,0.]]
    kept,removed=positive_area_triangles([zero,positive,collinear])
    assert removed==[0,2]
    assert kept==[positive]
    assert kept[0]is positive


def test_legal_names_preserve_complete_binary_and_non_name_fields(tmp_path):
    import json,struct
    from unreal_import_real_home_windows import prepare_legal_import_names
    from home_asset_audit import read_gltf
    source=tmp_path/'source.glb';target=tmp_path/'target.glb'
    doc={'asset':{'version':'2.0'},'nodes':[{'name':'Hinge_0.18','mesh':0,'translation':[1,2,3]}],'meshes':[{'name':'Hinge_0.18','primitives':[]}],'buffers':[{'byteLength':4}]}
    raw=json.dumps(doc).encode();raw+=b' '*(-len(raw)%4);binary=b'\x00\xff\x80\x7f'
    source.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+4)+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',4,0x004e4942)+binary)
    actual,blob,names=prepare_legal_import_names(source,target)
    assert names=={0:'Hinge_0.18'}
    assert actual['nodes'][0]['name']=='SUB01_RealWindow_Part_0'
    assert actual['nodes'][0]['translation']==[1,2,3]
    assert bytes(blob)==binary
    assert read_gltf(source)[0]==doc
