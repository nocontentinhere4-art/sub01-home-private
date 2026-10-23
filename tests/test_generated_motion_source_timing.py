"""Source timing and exact-key cropping cannot silently double walking cadence."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path
import pytest
from tools.extract_generated_soma_contacts import extract
from tools.crop_generated_owner_motion import crop


def contact_archive(path, frames=4, values=None):
    header=repr({'descr':'|b1','fortran_order':False,'shape':(frames,6)}).encode()+b'\n'
    npy=bytes([147])+b'NUMPY'+bytes([1,0])+struct.pack('<H',len(header))+header+bytes(values if values is not None else [1,0,1,0,1,0]*frames)
    with zipfile.ZipFile(path,'w')as archive:archive.writestr('foot_contacts.npy',npy)


def test_actual_bvh_clock_wins_over_requested_duration(tmp_path):
    source=tmp_path/'motion.npz';bvh=tmp_path/'motion.bvh';contact_archive(source)
    bvh.write_text('Frames: 4\nFrame Time: 0.03333333333333333\n')
    result=extract(source,bvh)
    assert result['fps']==30 and result['duration_samples_s']==pytest.approx(4/30)
    assert result['last_sample_time_s']==pytest.approx(.1)
    assert result['contacts'][0]==[True,False,True,False,True,False]


def test_frame_count_and_nonboolean_contact_corruption_refuse(tmp_path):
    source=tmp_path/'motion.npz';bvh=tmp_path/'motion.bvh';contact_archive(source)
    bvh.write_text('Frames: 8\nFrame Time: 0.016666666666666666\n')
    with pytest.raises(AssertionError):extract(source,bvh)
    bvh.write_text('Frames: 4\nFrame Time: 0.03333333333333333\n');contact_archive(source,values=[2]*24)
    with pytest.raises(AssertionError):extract(source,bvh)


def make_owner_clip(path):
    times=struct.pack('<4f',0,1/30,2/30,3/30);keys=struct.pack('<12f',*range(12));geometry=struct.pack('<9f',0,0,0,1,0,0,0,1,0);binary=times+keys+geometry
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':16},{'buffer':0,'byteOffset':16,'byteLength':48},{'buffer':0,'byteOffset':64,'byteLength':36}],'accessors':[{'bufferView':0,'componentType':5126,'count':4,'type':'SCALAR'},{'bufferView':1,'componentType':5126,'count':4,'type':'VEC3'},{'bufferView':2,'componentType':5126,'count':3,'type':'VEC3'}],'nodes':[{'name':'Hips','mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':2}}]}],'animations':[{'samplers':[{'input':0,'output':1,'interpolation':'LINEAR'}],'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}}]}]}
    text=json.dumps(doc).encode();text+=b' '*(-len(text)%4);path.write_bytes(struct.pack('<IIIII',0x46546c67,2,28+len(text)+len(binary),len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary)
    return doc,binary


def read(path):
    data=path.read_bytes();n=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+n]);return doc,data[28+n:]


def test_body_crop_preserves_mesh_and_key_values_with_original_clock(tmp_path):
    source=tmp_path/'owner.glb';output=tmp_path/'crop.glb';original,binary=make_owner_clip(source)
    report=crop(source,output,1,3,30,hashlib.sha256(source.read_bytes()).hexdigest());doc,actual=read(output)
    assert doc['meshes']==original['meshes'] and doc['nodes']==original['nodes']
    assert actual[:len(binary)]==binary
    sampler=doc['animations'][0]['samplers'][0];a=doc['accessors'][sampler['output']];v=doc['bufferViews'][a['bufferView']]
    assert actual[v['byteOffset']:v['byteOffset']+v['byteLength']]==binary[28:64]
    assert report['duration_s']==pytest.approx(2/30) and report['frames']==3
    with pytest.raises(AssertionError):crop(source,output,1,3,60,hashlib.sha256(source.read_bytes()).hexdigest())


# ---------- the walk's reference foot speed, cycle time and stride (room_build/kimodo_g12/walk_metrics.py)
import importlib.util
import math

WALK_MODULE = Path(__file__).resolve().parent.parent / "room_build" / "kimodo_g12" / "walk_metrics.py"
_spec = importlib.util.spec_from_file_location("walk_metrics", WALK_MODULE)
walk_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(walk_metrics)


def walk_glb(path, speed=0.6, cycle=1.2, fps=30, seam_jump=0.0):
    """An in-place walk on boy.glb's joint names: each foot is planted for 60% of the cycle, moving backward at `speed`
    in the clip's frame, and swings forward in the other 40%. The feet are half a cycle apart. seam_jump (m) moves the
    left ankle of the last frame: a loop seam that does not close."""
    n = int(round(cycle * fps)) + 1               # the last frame repeats the first: the loop closes (span = cycle)
    amp = speed * 0.6 * cycle / 2                 # the stance travel is 2 * amp, at `speed`
    times = [i / fps for i in range(n)]

    def foot(phase, lateral, seam=False):
        out = []
        for i in range(n):
            u = ((i / (n - 1)) - phase) % 1.0
            if u < 0.6:                            # planted: from +amp to -amp, on the floor
                z = amp - 2 * amp * (u / 0.6); y = 0.0
            else:                                  # swinging: from -amp to +amp, lifted
                s = (u - 0.6) / 0.4
                z = -amp + 2 * amp * s; y = 0.08 * math.sin(math.pi * s)
            out.append((lateral, 0.12 + y, z))
        if seam and seam_jump:
            x, y, z = out[-1]
            out[-1] = (x, y, z + seam_jump)
        return [v for xyz in out for v in xyz]

    channels = [("LeftFoot", foot(0.0, 0.1, seam=True)), ("LeftToeBase", foot(0.0, 0.1)),
                ("RightFoot", foot(0.5, -0.1)), ("RightToeBase", foot(0.5, -0.1))]
    binary = struct.pack(f"<{n}f", *times)
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": 4 * n}]
    accessors = [{"bufferView": 0, "componentType": 5126, "count": n, "type": "SCALAR"}]
    samplers, chans = [], []
    names = ["Hips", "LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
    nodes = [{"name": "Hips", "children": [1, 2, 3, 4]}]
    for nm in names[1:]:
        nodes.append({"name": nm, "translation": [0.1 if "Left" in nm else -0.1, 0.12, 0.0]})
    for nm, vals in channels:
        data = struct.pack(f"<{3 * n}f", *vals)
        off = len(binary); binary += data
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data)})
        accessors.append({"bufferView": len(views) - 1, "componentType": 5126, "count": n, "type": "VEC3"})
        samplers.append({"input": 0, "output": len(accessors) - 1, "interpolation": "LINEAR"})
        chans.append({"sampler": len(samplers) - 1, "target": {"node": names.index(nm), "path": "translation"}})
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
           "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors,
           "animations": [{"name": "walk", "samplers": samplers, "channels": chans}]}
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    path.write_bytes(struct.pack("<IIIII", 0x46546C67, 2, 28 + len(text) + len(binary), len(text), 0x4E4F534A)
                     + text + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return path


def test_walk_speed_cycle_and_stride_are_measured_from_the_feet(tmp_path):
    clip = walk_glb(tmp_path / "walk.glb", speed=0.6, cycle=1.2)
    t, joints, hips = walk_metrics.read_glb(clip, "boy", "walk")
    m = walk_metrics.measure_walk(t, joints, hips)
    assert m["refFootSpeed"] == pytest.approx(0.6, rel=0.02)
    assert m["cycleTime"] == pytest.approx(1.2, rel=0.01)
    assert m["strideLength"] == pytest.approx(0.6 * 1.2, rel=0.02)
    assert m["touchdowns"] == {"L": 1, "R": 1} and m["inPlace"] and m["slideM"] < walk_metrics.SLIDE_MAX_M
    assert m["seamFeetM"] < walk_metrics.SEAM_POP_MAX_M


def test_sidecar_speed_more_than_five_percent_off_the_clip_is_flagged(tmp_path):
    clip = walk_glb(tmp_path / "walk.glb", speed=0.6, cycle=1.2)
    t, joints, hips = walk_metrics.read_glb(clip, "boy", "walk")
    m = walk_metrics.measure_walk(t, joints, hips)
    good = {"refFootSpeed": m["refFootSpeed"] * 1.03, "cycleTime": m["cycleTime"], "strideLength": m["strideLength"] * 1.03}
    assert walk_metrics.compare_meta(m, good) == []
    old = {"refFootSpeed": 0.65, "cycleTime": m["cycleTime"], "strideLength": m["strideLength"]}   # ~8% off the clip
    assert [s.split(":")[0] for s in walk_metrics.compare_meta(m, old)] == ["refFootSpeed"]
    assert walk_metrics.compare_meta(m, {"refFootSpeed": m["refFootSpeed"]}) == [
        "cycleTime: missing from the sidecar", "strideLength: missing from the sidecar"]


def test_contact_hovering_at_the_threshold_is_one_contact():
    h = [0.005, 0.015, 0.005, 0.015, 0.005, 0.015, 0.03, 0.04, 0.03, 0.04, 0.03, 0.04]   # 1.5 cm is inside the release band
    mask = walk_metrics.planted_mask(h, [True] * len(h))
    runs = walk_metrics._runs(mask)
    assert len(runs) == 1 and len(runs[0]) == 6


def test_a_clip_whose_last_pose_is_its_first_has_no_seam_pop(tmp_path):
    clip = walk_glb(tmp_path / "closed.glb", speed=0.6, cycle=1.2)
    t, joints, hips = walk_metrics.read_glb(clip, "boy", "walk")
    m = walk_metrics.measure_walk(t, joints, hips)
    assert m["seamFeetM"] < 1e-4 and m["loopS"] == pytest.approx(1.2, abs=1e-3)
    assert m["cycleTime"] == pytest.approx(1.2, rel=0.01)


def test_a_swinging_foot_passing_the_stance_height_is_not_planted():
    h = [0.0] * 10
    back = [True, True, False, False, False, False, True, True, True, True]   # four frames moving forward: a swing
    mask = walk_metrics.planted_mask(h, back)
    assert mask[0] and mask[1] and mask[6] and not any(mask[2:6])


def test_a_loop_seam_that_does_not_close_is_reported_as_the_seam_pop(tmp_path):
    clip = walk_glb(tmp_path / "popped.glb", speed=0.6, cycle=1.2, seam_jump=0.015)
    t, joints, hips = walk_metrics.read_glb(clip, "boy", "walk")
    m = walk_metrics.measure_walk(t, joints, hips)
    assert m["seamFeetM"] == pytest.approx(0.015, abs=0.002)
    assert m["seamFeetM"] > walk_metrics.SEAM_POP_MAX_M
    assert m["slideM"] < walk_metrics.SLIDE_MAX_M     # the seam is not counted again as slide inside the contact
