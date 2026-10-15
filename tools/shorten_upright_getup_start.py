"""Explicit short-start derivative; never call the breathing prefix duplicate poses."""
import copy
import hashlib
import json
import math
import struct
from pathlib import Path

SOURCE_SHA = '7b0ac721bc84cffcd9f3a1cadffa4cd7ab7e021e371d8fb40c77e02968dfd799'


def slerp(a, b, u):
    if u == 0: return a
    if u == 1: return b
    a = [x / math.sqrt(sum(y*y for y in a)) for x in a]
    b = [x / math.sqrt(sum(y*y for y in b)) for x in b]
    dot = sum(x*y for x,y in zip(a,b))
    if dot < 0: b = [-x for x in b]; dot = -dot
    if dot > .9995:
        q = [(1-u)*x+u*y for x,y in zip(a,b)]
        return [x/math.sqrt(sum(y*y for y in q)) for x in q]
    angle = math.acos(min(1.,dot))
    return [(math.sin((1-u)*angle)*x+math.sin(u*angle)*y)/math.sin(angle) for x,y in zip(a,b)]


def derive(doc, binary, join_key=27, bridge_intervals=6, bridge_seconds=.20):
    """Retain exact endpoints and active rows; replace only the Idle-motion prefix."""
    out = copy.deepcopy(doc); data = bytearray(binary); animation = out['animations'][0]
    def read(ai):
        a=doc['accessors'][ai]; v=doc['bufferViews'][a['bufferView']]
        assert a['componentType']==5126 and not a.get('normalized') and 'sparse' not in a
        size={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']]
        offset=v.get('byteOffset',0)+a.get('byteOffset',0); stride=v.get('byteStride',size*4)
        return [struct.unpack_from('<'+'f'*size,binary,offset+i*stride) for i in range(a['count'])]
    def append(rows, kind):
        while len(data)%4:data.append(0)
        offset=len(data)
        for row in rows:data.extend(struct.pack('<'+'f'*len(row),*row))
        out['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data)-offset})
        accessor={'bufferView':len(out['bufferViews'])-1,'componentType':5126,'count':len(rows),'type':kind}
        if kind=='SCALAR':accessor.update(min=[rows[0][0]],max=[rows[-1][0]])
        out['accessors'].append(accessor);return len(out['accessors'])-1
    time_rows=read(animation['samplers'][0]['input']); old_times=[r[0] for r in time_rows]
    assert len(old_times)==68 and 0<join_key<len(old_times)-1
    times=[bridge_seconds*i/bridge_intervals for i in range(bridge_intervals+1)]
    times += [bridge_seconds+t-old_times[join_key] for t in old_times[join_key+1:]]
    input_ai=append([(t,)for t in times],'SCALAR'); mapped={}; tracks=[]
    for channel in animation['channels']:
        si=channel['sampler']; sampler=animation['samplers'][si]; assert sampler.get('interpolation','LINEAR')=='LINEAR'
        if si in mapped:continue
        rows=read(sampler['output']); kind=doc['accessors'][sampler['output']]['type']; path=channel['target']['path']
        assert len(rows)==68 and path in ('rotation','translation','scale')
        bridge=[]
        for i in range(bridge_intervals+1):
            u=i/bridge_intervals; u=u*u*u*(u*(u*6-15)+10)
            bridge.append(slerp(rows[0],rows[join_key],u) if path=='rotation' else [(1-u)*a+u*b for a,b in zip(rows[0],rows[join_key])])
        fresh=bridge+rows[join_key+1:]
        assert tuple(fresh[0])==rows[0] and tuple(fresh[-1])==rows[-1] and tuple(fresh[bridge_intervals])==rows[join_key]
        sampler['input']=input_ai;sampler['output']=append(fresh,kind);mapped[si]=True
        tracks.append({'node':channel['target']['node'],'name':doc['nodes'][channel['target']['node']].get('name'),'path':path})
    out['buffers'][0]['byteLength']=len(data)
    animation['name']='SUB01_GetUp_upright_footrest_ShortStart'
    animation['extras']={'derived':True,'source_sha256':SOURCE_SHA,'short_start_bridge_seconds':bridge_seconds,'native_ready':False}
    report={'schema':'sub01.short-start-upright-getup.v1','source_sha256':SOURCE_SHA,'frames':len(times),'duration_s':times[-1],
            'removed_original_prefix_keys':list(range(1,join_key)), 'bridge_original_key_endpoints':[0,join_key],
            'bridge_seconds':bridge_seconds,'bridge_intervals':bridge_intervals,'bridge_tracks':tracks,
            'reason':'Original prefix is authentic nonstationary Idle/finger motion, not identical poses; replace with explicit shortest-quaternion endpoint bridge',
            'retained_active_key_mapping':[{'new_key':bridge_intervals+1+i,'original_key':j,'original_time_s':old_times[j],'new_time_s':times[bridge_intervals+1+i]}for i,j in enumerate(range(join_key+1,68))],
            'first_and_last_rows_exact':True,'nonanimation_nodes_unchanged':out['nodes']==doc['nodes'],'original_binary_prefix_unchanged':bytes(data[:len(binary)])==binary,
            'source_ready':False,'native_imported':False,'runtime_ready':False,'geometry_and_main_support_pass':False}
    return out,bytes(data),report
