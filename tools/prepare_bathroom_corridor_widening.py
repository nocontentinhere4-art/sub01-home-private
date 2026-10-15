"""Owned source-derived 15cm bathroom adjustment; never edits the saved home.

The five bathroom boxes share the source architecture mesh with the rest of
the building. Every unaffected architecture corner and all non-position corner
attributes are retained. Native activation must replace the nine exact source
nodes together and bind their existing materials, with a map backup.
"""
import copy
import hashlib
import json
import math
import struct
from pathlib import Path

from prepare_frame_backing_remainder import SOURCE_SHA, read, elements
from structural_rail_source_patch import world_matrices, transformed

SHIFT = -.15
NODES = (117, 118, 151, 152, 153, 154, 155, 156, 158)
MESHES = {117: 100, 118: 101, **{n: 116 for n in range(151, 157)}, 158: 117}
MATERIALS = {117: 60, 118: 5, **{n: 66 for n in range(151, 157)}, 158: 67}
WALL_BOXES = {
    420: ((-3.875, 3.035, .45), (-.775, 5.885, .55)),
    432: ((-3.875, 3.035, 2.65), (-.775, 5.885, 2.75)),
    444: ((-.9, 3.035, .5), (-.8, 5.885, .85)),
    456: ((-.9, 3.035, 1.8), (-.8, 5.885, 2.7)),
    468: ((-.9, 5., .9), (-.8, 5.9, 1.8)),
}


def bounds(points):
    return [[min(p[a] for p in points) for a in range(3)],
            [max(p[a] for p in points) for a in range(3)]]


def shorten_x(point, left, right):
    if not left < right or right + SHIFT <= left:
        raise ValueError('Invalid reviewed wall/floor interval')
    if not left - 1e-6 <= point[0] <= right + 1e-6:
        raise ValueError('Point escaped reviewed source interval')
    return (left + (point[0]-left)*(right+SHIFT-left)/(right-left), point[1], point[2])


def architecture_positions(points, ids):
    if len(ids) != 492*3:
        raise ValueError('Exact source 492-triangle architecture required')
    changed = list(points)
    changed_vertices = set()
    changed_triangles = set()
    for start, want in WALL_BOXES.items():
        selected = ids[start*3:(start+12)*3]
        vertices = set(selected)
        actual = bounds([points[i] for i in selected])
        if max(abs(a-b) for x,y in zip(actual,want) for a,b in zip(x,y)) > 1e-6:
            raise ValueError('Exact bathroom wall box differs: '+str(start))
        if len({tuple(round(v,6) for v in points[i]) for i in vertices}) != 8:
            raise ValueError('Reviewed wall must remain its actual eight-corner box')
        if vertices.intersection(ids[:start*3]+ids[(start+12)*3:]):
            raise ValueError('Bathroom wall shares vertices with protected architecture')
        for i in vertices:
            p = points[i]
            changed[i] = shorten_x(p, want[0][0], want[1][0]) if start in (420,432) else (p[0]+SHIFT,p[1],p[2])
        changed_vertices.update(vertices)
        changed_triangles.update(range(start,start+12))
    if len(changed_triangles) != 60:
        raise ValueError('Only exact five bathroom wall boxes may change')
    for i,p in enumerate(points):
        if i not in changed_vertices and changed[i] != p:
            raise ValueError('Protected architecture position changed')
    return changed, sorted(changed_triangles)


def prepare(source, output):
    raw = Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('Exact licensed source955 required')
    doc, blob = read(raw)
    matrices = world_matrices(doc)
    result = {'asset': {'version':'2.0','generator':'SUB01 exact source bathroom corridor adjustment'},
              'scene':0,'scenes':[{'nodes':[]}], 'nodes':[], 'meshes':[],
              'materials':[], 'accessors':[], 'bufferViews':[], 'buffers':[]}
    binary = bytearray()
    materials = {}
    reports = []

    def append(data, meta, target):
        binary.extend(b'\0'*(-len(binary)%4))
        view = len(result['bufferViews'])
        result['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(data),'target':target})
        binary.extend(data)
        a = {k:copy.deepcopy(v) for k,v in meta.items() if k not in ('bufferView','byteOffset','sparse')}
        a['bufferView'] = view
        result['accessors'].append(a)
        return len(result['accessors'])-1

    for ni in NODES:
        node = doc['nodes'][ni]
        if node.get('mesh') != MESHES[ni]:
            raise ValueError('Exact source node/mesh differs '+str(ni))
        primitives = doc['meshes'][node['mesh']]['primitives']
        if len(primitives) != 1 or primitives[0].get('material') != MATERIALS[ni]:
            raise ValueError('Exact source material primitive differs '+str(ni))
        primitive = primitives[0]
        raw_pos, fmt = elements(doc,blob,primitive['attributes']['POSITION'])
        local = [struct.unpack(fmt,p) for p in raw_pos]
        points = [tuple(transformed(matrices[ni],p)) for p in local]
        raw_ids, id_fmt = elements(doc,blob,primitive['indices'])
        ids = [struct.unpack(id_fmt,i)[0] for i in raw_ids]
        source_bounds = bounds(points)
        changed_triangles = list(range(len(ids)//3))
        if ni == 158:
            points,changed_triangles = architecture_positions(points,ids)
        elif ni in (117,151,152):
            # Keep the west endpoint and trim only the bathroom's east edge.
            points = [shorten_x(p,source_bounds[0][0],source_bounds[1][0]) for p in points]
        else:
            points = [(p[0]+SHIFT,p[1],p[2]) for p in points]
        if not all(math.isfinite(v) for p in points for v in p):
            raise ValueError('Nonfinite derived source geometry')
        role = 'SUB01_BathCorridor_SourceNode_'+str(ni)
        attrs = {}
        preserved_hashes = {}
        for name,index in primitive['attributes'].items():
            values,attribute_fmt = elements(doc,blob,index)
            meta = copy.deepcopy(doc['accessors'][index])
            if name == 'POSITION':
                if attribute_fmt != '<fff':
                    raise ValueError('Exact float32 positions required')
                values = [struct.pack('<fff',*p) for p in points]
                meta['min'],meta['max'] = bounds(points)
            elif name in ('NORMAL','TANGENT'):
                # These nodes have only translation or positive axis scales;
                # scaled source boxes have axis-aligned normals/tangents.
                scale = node.get('scale',[1,1,1])
                if any(abs(x-1)>1e-7 for x in scale):
                    decoded = [struct.unpack(attribute_fmt,v) for v in values]
                    if any(sum(abs(x)>1e-6 for x in v[:3]) != 1 for v in decoded):
                        raise ValueError('Non-axis source basis needs explicit normal bake')
            if name != 'POSITION':
                preserved_hashes[name] = hashlib.sha256(b''.join(values)).hexdigest()
            attrs[name] = append(b''.join(values),meta,34962)
        index = append(b''.join(raw_ids),doc['accessors'][primitive['indices']],34963)
        material = MATERIALS[ni]
        if material not in materials:
            materials[material] = len(result['materials'])
            result['materials'].append({'name':'SUB01_RequireExistingMaterial_'+str(material),
                                        'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1]}})
        mesh = len(result['meshes'])
        result['meshes'].append({'name':role,'primitives':[{'attributes':attrs,'indices':index,'material':materials[material],'mode':4}]})
        result['nodes'].append({'name':role,'mesh':mesh})
        result['scenes'][0]['nodes'].append(mesh)
        reports.append({'source_node':ni,'source_mesh':MESHES[ni],'source_material':material,
                        'mesh_name':role,'triangles':len(ids)//3,'source_bounds_gltf_m':source_bounds,
                        'new_bounds_gltf_m':bounds(points),'changed_triangle_indices':changed_triangles,
                        'exact_non_position_attribute_sha256':preserved_hashes,
                        'native_material_rebind_required':'/Game/Sub01Home/ImportedScene/full-home/Materials/Material_'+str(material)+'.Material_'+str(material)})
    result['buffers'] = [{'byteLength':len(binary)}]
    text = json.dumps(result,separators=(',',':')).encode();text += b' '*(-len(text)%4)
    binary.extend(b'\0'*(-len(binary)%4))
    encoded = struct.pack('<III',0x46546c67,2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary
    rd,rb = read(encoded)
    for part,report in zip(rd['meshes'],reports):
        rp = part['primitives'][0]
        for name,want in report['exact_non_position_attribute_sha256'].items():
            actual,_ = elements(rd,rb,rp['attributes'][name])
            if hashlib.sha256(b''.join(actual)).hexdigest() != want:
                raise ValueError('Derived corner attribute parity failed')
    output = Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'bath-corridor.glb').write_bytes(encoded)
    proof = {'schema':'sub01.bathroom-corridor-source-adjustment.v1','source_sha256':SOURCE_SHA,
             'export_sha256':hashlib.sha256(encoded).hexdigest(),'shift_ue_cm':[-15,0,0],
             'parts':reports,'source_node_count':9,'source_triangle_count':876,
             'architecture_changed_triangles':60,'architecture_protected_triangles':432,
             'protected_rail_source_node':162,'global_ceiling_unchanged':True,
             'ceiling_reason':'Existing global roof remains over the resized room; exact roof triangles in node158 are protected.',
             'UV_normals_colors_skin_material_attributes_preserved':True,
             'material_policy':'Placeholder import materials MUST be replaced with exact existing original source Material5/60/66/67 before activation.',
             'native_door_binding':{'source_node':118,'new_source_center_ue_cm':[-100,135,405],
                                    'preserved_existing_relative_fit_cm':[11.2,0,0],
                                    'expected_native_closed_center_ue_cm':[-88.8,135,405],
                                    'extent_ue_cm':[3.25,44.5,100],'slide_ue_cm':[0,95]},
             'runtime_updates_required':{'bathroom_privacy_right_X_cm':-100,'bath_aisle_X_cm':-60,
                                          'bath_door_outside_X_cm':-56.7,'exact_source_bounds_and_native_receipt_required':True},
             'full_house_collision_proof':False,'native_imported':False,'physical_route_accepted':False}
    (output/'bath-corridor.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
