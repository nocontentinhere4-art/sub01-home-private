"""Restore exact unmodified captured rotation rows in an owned animation derivative."""
import struct


def rows(doc,binary,index):
    a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
    if a['componentType']!=5126 or a.get('normalized') or 'sparse'in a:raise ValueError('Exact float32 non-sparse capture required')
    width={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']]*4;start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',width)
    return [bytes(binary[start+i*stride:start+i*stride+width])for i in range(a['count'])]


def restore_unchanged_rotations(source_doc,source_binary,target_doc,target_binary,changed_names):
    """Copy captured float32 rows, including signs, rather than recomputing finger quaternions.

    The derivative must have exactly the same written key times. Only rotation
    tracks outside the explicit changed arm-bone set are restored. Source bytes
    and the owned target's geometry, skin and hierarchy are never modified.
    """
    source=[a for a in source_doc['animations']if a['name']=='typing']
    if len(source)!=1 or len(target_doc['animations'])!=1:raise ValueError('Unique typing capture and derivative required')
    source=source[0];target=target_doc['animations'][0];lookup={}
    for channel in source['channels']:
        name=source_doc['nodes'][channel['target']['node']]['name'];lookup[(name,channel['target']['path'])]=source['samplers'][channel['sampler']]
    data=bytearray(target_binary);restored=[]
    for channel in target['channels']:
        if channel['target']['path']!='rotation':continue
        name=target_doc['nodes'][channel['target']['node']]['name'];short=name.split(':')[-1]
        if short in changed_names:continue
        original=lookup[(name,'rotation')];written=target['samplers'][channel['sampler']]
        if rows(source_doc,source_binary,original['input'])!=rows(target_doc,data,written['input']):raise ValueError('Captured and written times differ')
        values=rows(source_doc,source_binary,original['output']);a=target_doc['accessors'][written['output']];v=target_doc['bufferViews'][a['bufferView']]
        if a['type']!='VEC4' or a['count']!=len(values):raise ValueError('Captured rotation shape differs')
        start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',16)
        for i,value in enumerate(values):data[start+i*stride:start+i*stride+16]=value
        if rows(target_doc,data,written['output'])!=values:raise ValueError('Captured rows not restored exactly')
        restored.append(short)
    return bytes(data),restored
