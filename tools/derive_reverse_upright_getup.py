"""Explicit derived reversal of a physically proved SitDown, never raw GetUp."""
import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

SIT_SHA='3da7b1f46a7e503f1bea8c3f33a07cdbcf8d931924dbe3a39c1be5123d9700ea'


def reverse_rows(binary, offset, stride, count, size):
    original=bytes(binary);out=bytearray(original)
    for i in range(count):out[offset+i*stride:offset+i*stride+size]=original[offset+(count-1-i)*stride:offset+(count-1-i)*stride+size]
    return bytes(out)


def run():
    import numpy as np
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import export_seat_fit_source as E
    import solve_seat_pose_anatomical as A
    import life_gltf as G
    source=Path('/workspace/sub01-home-private/upright-transition-sit-r12/SUB01_SitDown_upright_footrest.glb');g=G.Gltf(source);assert g.sha256==SIT_SHA
    passed=json.loads(source.with_name('transition-report.json').read_text());assert passed['geometry_and_main_support_pass']is True and passed['anatomical_excess_max_deg']==0 and passed['source_ready']is False
    out=Path('/workspace/sub01-home-private/upright-transition-getup-derived-reverse-r2');out.mkdir(exist_ok=False)
    doc=copy.deepcopy(g.doc);binary=bytes(g.buffers[0]);animation=doc['animations'][0];written=set();inputs=set();F=passed['frames']
    for sampler in animation['samplers']:
        assert sampler['interpolation']=='LINEAR';inputs.add(sampler['input']);ai=sampler['output']
        if ai in written:continue
        written.add(ai);a=doc['accessors'][ai];v=doc['bufferViews'][a['bufferView']];assert a['count']==F and a['componentType']==5126 and a['type']in('VEC3','VEC4')and not a.get('normalized')and 'sparse'not in a
        size=4*{'VEC3':3,'VEC4':4}[a['type']];binary=reverse_rows(binary,v.get('byteOffset',0)+a.get('byteOffset',0),v.get('byteStride',size),F,size)
    for ai in inputs:
        a=doc['accessors'][ai];v=doc['bufferViews'][a['bufferView']];assert a['type']=='SCALAR'and a['componentType']==5126 and a['count']==F
        offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',4);times=[struct.unpack_from('<f',binary,offset+i*stride)[0]for i in range(F)];duration=times[-1];new=[duration-t for t in reversed(times)];buffer=bytearray(binary)
        for i,t in enumerate(new):struct.pack_into('<f',buffer,offset+i*stride,t)
        binary=bytes(buffer)
    animation['name']='SUB01_GetUp_upright_footrest_DerivedReverse';animation['extras']={'derived_reverse_of_sitdown_sha256':SIT_SHA,'not_original_GetUp_capture':True,'native_ready':False};doc['asset']['extras']={'derived':True,'reverse_source_sha256':SIT_SHA,'native_ready':False}
    path=out/'SUB01_GetUp_upright_footrest_DerivedReverse.glb';G.write_glb(path,doc,binary);written_clip=G.Gltf(path);base=E.Source.load(root/'private-audit/seat-fit-source.npz');t0=np.asarray(g.animation().key_times());t1=np.asarray(written_clip.animation().key_times());W0,_=E.joint_worlds(g,base.names,t0);W1,_=E.joint_worlds(written_clip,base.names,t1);difference=float(np.max(np.abs(W1-W0[::-1])));assert difference<1e-12
    B=np.linalg.inv(base.ibm);angles=A.joint_angles(W1,B,base.names);raw=G.Gltf(root/'web/room/mh_mx/room_mx_stand_to_sit.glb');raw_world,_=E.joint_worlds(raw,base.names,np.arange(F)/30);excess=A.limit_excess(angles,A.joint_angles(raw_world[::-1],B,base.names));assert excess.max()==0
    idle=G.Gltf(next(Path('/workspace/sub01-home-private/upright-footrest-fit-r8').rglob('SUB01_SeatedIdle_upright_footrest.glb')));dt=t1[1]-t1[0];idle_world,_=E.joint_worlds(idle,base.names,[0.,dt]);seam_velocity=float(np.linalg.norm(((W1[1,:,:3,3]-W1[0,:,:3,3])-(idle_world[1,:,:3,3]-idle_world[0,:,:3,3]))*100/dt,axis=1).max())
    report={'schema':'sub01.derived-reverse-upright-getup.v1','source_sitdown_sha256':SIT_SHA,'written_glb':str(path),'written_glb_sha256':written_clip.sha256,'frames':F,'duration_s':float(t1[-1]),'initial_Idle_joint_head_velocity_discontinuity_max_cm_s':seam_velocity,'original_GetUp_unchanged':True,'not_original_GetUp_capture':True,'all65_written_world_matrix_max_difference_from_reversed_passed_pose':difference,'all_original_node_rest_transforms_unchanged':g.doc['nodes']==written_clip.doc['nodes'],'bone_length_error_cm':A.bone_length_error_cm(__import__('fit_seat_pose_trial').Skeleton(base),W0[::-1],W1),'anatomical_excess_max_deg':float(excess.max()),'initial_Idle_endpoint_matrix_max_error':float(np.max(np.abs(W1[0]-W0[-1]))),'final_standing_endpoint_matrix_max_error':float(np.max(np.abs(W1[-1]-W0[0]))),'physical_predicates':'Transferred by all-frame exact written world-matrix equality, same owner831790, same source chair/desk/footrest; not a new surface collision measurement','passed_source_physical_margins':passed['collision'],'actual_floor_min_z_cm':passed['actual_floor_min_z_cm'],'strong_seated_mask_frames':[F-1-f for f in reversed(passed['strong_seated_mask_frames'])],'strong_seated_all_pass':True,'geometry_and_main_support_pass':True,'source_ready':False,'native_imported':False,'runtime_ready':False,'pending':['Visual naturalness and original walking/standing seam','Explicit handshape/selfcontact','Coherent typing chain and native verification']};(out/'reverse-source-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':run()
