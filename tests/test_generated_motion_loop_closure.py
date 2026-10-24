"""A bounded source seam cannot stretch limbs or modify geometry."""
import hashlib,json,math,struct
from pathlib import Path
import pytest
from tools.close_generated_owner_motion_loop import close


def fixture(path, degrees=7, nonhip_motion=False):
    n=33;times=struct.pack('<33f',*[i/30 for i in range(n)])
    quats=[]
    for i in range(n):
        a=math.radians(degrees*i/(n-1))/2;quats.extend([0,math.sin(a),0,math.cos(a)])
    rotation=struct.pack('<132f',*quats);translation=struct.pack('<99f',*[v for i in range(n)for v in (0, i*.001 if nonhip_motion else 0,0)])
    geom=struct.pack('<9f',0,0,0,1,0,0,0,1,0);binary=times+rotation+translation+geom
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(times)},{'buffer':0,'byteOffset':len(times),'byteLength':len(rotation)},{'buffer':0,'byteOffset':len(times)+len(rotation),'byteLength':len(translation)},{'buffer':0,'byteOffset':len(times)+len(rotation)+len(translation),'byteLength':len(geom)}],'accessors':[{'bufferView':0,'componentType':5126,'count':n,'type':'SCALAR'},{'bufferView':1,'componentType':5126,'count':n,'type':'VEC4'},{'bufferView':2,'componentType':5126,'count':n,'type':'VEC3'},{'bufferView':3,'componentType':5126,'count':3,'type':'VEC3'}],'nodes':[{'name':'mixamorig:LeftUpLeg','mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':3}}]}],'animations':[{'samplers':[{'input':0,'output':1},{'input':0,'output':2}],'channels':[{'sampler':0,'target':{'node':0,'path':'rotation'}},{'sampler':1,'target':{'node':0,'path':'translation'}}]}]}
    text=json.dumps(doc).encode();text+=b' '*(-len(text)%4);path.write_bytes(struct.pack('<IIIII',0x46546c67,2,28+len(text)+len(binary),len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary)
    return binary,hashlib.sha256(path.read_bytes()).hexdigest()


def test_seam_midpoint_and_interior_keys_keep_actual_nonanimation_bytes(tmp_path):
    source=tmp_path/'source.glb';out=tmp_path/'closed.glb';binary,sha=fixture(source)
    result=close(source,out,sha);raw=out.read_bytes();j=struct.unpack_from('<I',raw,12)[0];actual=raw[28+j:]
    assert actual[:132]==binary[:132] and actual[132+528:]==binary[132+528:]
    first=actual[132:148];last=actual[132+32*16:132+33*16];assert first==last
    q=struct.unpack('<4f',first);assert math.degrees(2*math.atan2(q[1],q[3]))==pytest.approx(3.5,abs=1e-5)
    assert actual[132+8*16:132+25*16]==binary[132+8*16:132+25*16]
    assert result['rotation_changes'][0]['max_endpoint_correction_deg']==pytest.approx(3.5,abs=1e-5)
    assert not result['native_changed'] and not result['world_horizontal_contact_accepted']


def test_excessive_rotation_or_nonhips_translation_refuses(tmp_path):
    s=tmp_path/'s.glb';o=tmp_path/'o.glb';_,sha=fixture(s,degrees=11)
    with pytest.raises(AssertionError):close(s,o,sha)
    _,sha=fixture(s,nonhip_motion=True)
    with pytest.raises(AssertionError,match='Non-Hips'):close(s,o,sha)
    assert not o.exists()


# ---------- the loop seam and the QA thresholds (room_build/kimodo_g12/walk_metrics.py and qa.py)
import importlib.util

import numpy as np

ROOM_QA = Path(__file__).resolve().parent.parent / "room_build" / "kimodo_g12"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


walk_metrics = _load("walk_metrics", ROOM_QA / "walk_metrics.py")
qa = _load("kimodo_qa", ROOM_QA / "qa.py")


def test_the_qa_thresholds_are_the_explicit_one_centimetre_constants():
    assert qa.CONTACT_TOL_M == 0.01 and qa.SLIDE_MAX_M == 0.01 and qa.SEAM_POP_MAX_M == 0.01
    assert walk_metrics.CONTACT_ON_M == 0.01 and walk_metrics.REF_TOL == 0.05


def test_a_loop_seam_pop_over_one_centimetre_is_flagged():
    first = np.zeros((4, 3))
    last = first.copy()
    last[2] = [0.012, 0.0, 0.0]                              # one joint 1.2 cm away from where the loop started
    pop = walk_metrics.seam_pop(first, last, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert pop == pytest.approx(0.012, abs=1e-6)
    assert qa.flag_list({"seam_pop": pop}, {"seam_pop": qa.SEAM_POP_MAX_M}) == [("seam_pop", f"{pop:.4f} > 0.0100")]


def test_a_loop_seam_under_one_centimetre_passes():
    first = np.zeros((4, 3))
    last = first.copy()
    last[1] = [0.004, -0.003, 0.0]                           # 5 mm: inside the tolerance
    pop = walk_metrics.seam_pop(first, last, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert qa.flag_list({"seam_pop": pop}, {"seam_pop": qa.SEAM_POP_MAX_M}) == []


def test_the_hips_travel_is_taken_out_of_the_seam_pop():
    first = np.zeros((4, 3))
    last = first + np.array([0.3, 0.0, 0.0])                 # the whole body travelled 30 cm: a walk, not a pop
    assert walk_metrics.seam_pop(first, last, [0.0, 0.0, 0.0], [0.3, 0.0, 0.0]) == pytest.approx(0.0, abs=1e-9)
