"""Replace scanned pillow meshes without re-exporting or altering baked cloth."""
import copy
import json
import struct


def read_glb(path):
    data = path.read_bytes()
    assert data[:4] == b'glTF' and struct.unpack_from('<I',data,4)[0] == 2
    size = struct.unpack_from('<I',data,12)[0]
    doc = json.loads(data[20:20+size])
    offset = 20 + size
    binary_size = struct.unpack_from('<I',data,offset)[0]
    return doc, data[offset+8:offset+8+binary_size]


def replace_pillows(target, source):
    old, binary = read_glb(target)
    new, new_binary = read_glb(source)
    output = bytearray(binary)
    accessors, views = {}, {}
    def accessor(index):
        if index in accessors: return accessors[index]
        a = copy.deepcopy(new['accessors'][index])
        assert 'sparse' not in a
        view_index = a['bufferView']
        if view_index not in views:
            view = copy.deepcopy(new['bufferViews'][view_index])
            while len(output) % 4: output.append(0)
            start = view.get('byteOffset',0)
            chunk = new_binary[start:start+view['byteLength']]
            assert len(chunk) == view['byteLength']
            view['byteOffset'] = len(output); view['buffer'] = 0
            output.extend(chunk)
            views[view_index] = len(old['bufferViews'])
            old['bufferViews'].append(view)
        a['bufferView'] = views[view_index]
        accessors[index] = len(old['accessors'])
        old['accessors'].append(a)
        return accessors[index]
    replacements = {n['name']:n for n in new['nodes'] if n.get('name','').startswith('Pillow')}
    for node in old['nodes']:
        if node.get('name') not in replacements: continue
        n = replacements.pop(node['name'])
        mesh = copy.deepcopy(new['meshes'][n['mesh']])
        for primitive in mesh['primitives']:
            primitive['attributes'] = {k:accessor(v) for k,v in primitive['attributes'].items()}
            if 'indices' in primitive: primitive['indices'] = accessor(primitive['indices'])
            primitive.pop('material',None)
        old['meshes'][node['mesh']] = mesh
        for key in ['matrix','translation','rotation','scale']:
            node.pop(key,None)
            if key in n: node[key] = n[key]
    assert not replacements, 'Missing pillow nodes'
    while len(output) % 4: output.append(0)
    old['buffers'] = [{'byteLength':len(output)}]
    encoded = json.dumps(old,separators=(',',':')).encode()
    encoded += b' ' * (-len(encoded)%4)
    target.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(output))
        + struct.pack('<I4s',len(encoded),b'JSON') + encoded
        + struct.pack('<I4s',len(output),b'BIN\0') + output)
