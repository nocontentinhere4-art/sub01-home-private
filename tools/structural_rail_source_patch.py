"""Pure exact cylinder-component selection inside material-batched source meshes.

Returns triangle indices only; never changes source files. Connectivity welds
equal source positions so cylinder cap/UV seam duplicates remain one component.
"""
import math
import struct
from home_asset_audit import node_matrix,matmul,IDENTITY


def accessor(doc,binary,index):
    row=doc['accessors'][index]
    if row.get('sparse'):raise ValueError('Sparse source accessor not supported for exact geometry patch')
    view=doc['bufferViews'][row['bufferView']]
    formats={5121:'B',5123:'H',5125:'I',5126:'f'}
    sizes={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
    fmt='<'+formats[row['componentType']]*sizes[row['type']]
    step=view.get('byteStride',struct.calcsize(fmt));start=view.get('byteOffset',0)+row.get('byteOffset',0)
    return [struct.unpack_from(fmt,binary,start+i*step) for i in range(row['count'])]


def world_matrices(doc):
    parents={c:i for i,n in enumerate(doc['nodes']) for c in n.get('children',[])};cache={}
    def world(i):
        if i not in cache:cache[i]=matmul(world(parents[i]) if i in parents else IDENTITY,node_matrix(doc['nodes'][i]))
        return cache[i]
    return [world(i) for i in range(len(doc['nodes']))]


def transformed(matrix,p):
    return tuple(sum(matrix[r][c]*v for c,v in enumerate((*p,1))) for r in range(3))


def is_exact_cylinder(points,beam):
    a,b=beam['a'],beam['b'];delta=[y-x for x,y in zip(a,b)];length=math.sqrt(sum(v*v for v in delta));unit=[v/length for v in delta]
    lo,hi=math.inf,-math.inf;max_radius=0
    for point in points:
        relative=[x-y for x,y in zip(point,a)];t=sum(x*y for x,y in zip(relative,unit));radial=math.sqrt(sum((x-t*y)**2 for x,y in zip(relative,unit)))
        if t<-.001 or t>length+.001 or radial>beam['radius']+.0002:return False
        lo=min(lo,t);hi=max(hi,t);max_radius=max(max_radius,radial)
    return abs(lo)<.001 and abs(hi-length)<.001 and abs(max_radius-beam['radius'])<.0002


def select(doc,binary,expected):
    matrices=world_matrices(doc);matches=[[] for _ in expected]
    centres=[tuple((x+y)/2 for x,y in zip(b['a'],b['b'])) for b in expected]
    for node_index,node in enumerate(doc['nodes']):
        if 'mesh' not in node:continue
        matrix=matrices[node_index]
        for primitive_index,primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
            if primitive.get('mode',4)!=4:continue
            meta=doc['accessors'][primitive['attributes']['POSITION']]
            if 'min' not in meta or 'max' not in meta:continue
            corners=[transformed(matrix,(x,y,z)) for x in (meta['min'][0],meta['max'][0]) for y in (meta['min'][1],meta['max'][1]) for z in (meta['min'][2],meta['max'][2])]
            low=[min(p[i] for p in corners) for i in range(3)];high=[max(p[i] for p in corners) for i in range(3)]
            if not any(all(low[i]-.04<=c[i]<=high[i]+.04 for i in range(3)) for c in centres):continue
            positions=[transformed(matrix,p) for p in accessor(doc,binary,primitive['attributes']['POSITION'])]
            indices=[v[0] for v in accessor(doc,binary,primitive['indices'])] if 'indices' in primitive else list(range(len(positions)))
            if len(indices)%3:raise ValueError('Source triangle index stream incomplete')
            keys={};parent=[];vertex_roots=[]
            for p in positions:
                key=tuple(round(v*1000000) for v in p)
                if key not in keys:keys[key]=len(parent);parent.append(len(parent))
                vertex_roots.append(keys[key])
            def root(i):
                while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
                return i
            for j in range(0,len(indices),3):
                vertices=[root(vertex_roots[i]) for i in indices[j:j+3]]
                for v in vertices[1:]:parent[root(v)]=root(vertices[0])
            components={}
            for j in range(0,len(indices),3):components.setdefault(root(vertex_roots[indices[j]]),[]).append(j//3)
            for triangles in components.values():
                vertices=sorted({i for j in triangles for i in indices[j*3:j*3+3]});points=[positions[i] for i in vertices]
                centre=tuple((min(p[i] for p in points)+max(p[i] for p in points))/2 for i in range(3))
                for e,c in enumerate(centres):
                    if max(abs(x-y) for x,y in zip(centre,c))>.001:continue
                    if is_exact_cylinder(points,expected[e]):
                        matches[e].append({'source_node_index':node_index,'source_name':node.get('name'),'primitive_index':primitive_index,'triangle_indices':triangles,'material_index':primitive.get('material'),'source_primitive_triangle_count':len(indices)//3,'selected_triangle_count':len(triangles),'world_matrix':matrix})
    rows=[];errors=[]
    for beam,found in zip(expected,matches):
        if len(found)!=1:errors.append({'expected_beam':beam,'matches':len(found)});continue
        row=dict(found[0],expected_role=beam['name'],a=beam['a'],b=beam['b'],radius=beam['radius'],actor_object_name='full-home_node_'+str(found[0]['source_node_index']),component_name='StaticMeshComponent0')
        rows.append(row)
    return rows,errors
