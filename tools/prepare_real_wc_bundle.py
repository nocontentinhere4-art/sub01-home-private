"""Server-only real CC0 WC placement and exact old-WC shared-mesh remainders.

No house modelling or native mutation. The source model's complete binary/PBR
is retained; one rigid parent places it. Blender is used only for actual BVH
clearance/support proof and an editable packed .blend of the genuine model.
"""
import argparse
import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
from prepare_frame_backing_remainder import read,elements

HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
WC_SHA='3dd8c8d52d77f16966c22eac82742658945cd9652fde3241b43babddaa158e3a'
REMOVALS={166:set(range(300,900)),168:set(range(300))}


def glb(doc,binary):
    encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4)
    binary=bytes(binary)+b'\0'*(-len(binary)%4)
    return struct.pack('<III',0x46546c67,2,28+len(encoded)+len(binary))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(binary),0x004e4942)+binary


def node_geometry(doc,binary,node,matrices):
    rows=[]
    for pi,p in enumerate(doc['meshes'][doc['nodes'][node]['mesh']]['primitives']):
        points=[transformed(matrices[node],v)for v in accessor(doc,binary,p['attributes']['POSITION'])]
        ids=[v[0]for v in accessor(doc,binary,p['indices'])]if 'indices'in p else list(range(len(points)))
        rows.append({'node':node,'primitive':pi,'material':p.get('material'),'points':points,'faces':[ids[i:i+3]for i in range(0,len(ids),3)]})
    return rows


def remainder(doc,binary,node,output):
    original=doc['nodes'][node]
    if original.get('mesh')!={166:125,168:127}[node] or any(k in original for k in ('matrix','translation','rotation','scale'))or any(node in n.get('children',[])for n in doc['nodes']):raise ValueError('Exact root bathroom batch required')
    ps=doc['meshes'][original['mesh']]['primitives']
    if len(ps)!=1 or ps[0].get('material')!={166:68,168:69}[node]:raise ValueError('Exact bathroom source material required')
    p=ps[0];raw_ids,fmt=elements(doc,binary,p['indices']);ids=[struct.unpack(fmt,v)[0]for v in raw_ids]
    if len(ids)!=2700:raise ValueError('Exact900 triangle bathroom batch required')
    keep=[i for i in range(900)if i not in REMOVALS[node]];surviving=[v for i in keep for v in ids[3*i:3*i+3]]
    vertices=sorted(set(surviving));mapping={v:i for i,v in enumerate(vertices)};blob=bytearray();out={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':f'SUB01_WCRemainder_{node}','mesh':0}],'meshes':[{'primitives':[]}],'materials':[{'name':f'REQUIRE_ORIGINAL_Material_{p["material"]}'}],'bufferViews':[],'accessors':[],'buffers':[]}
    def append(data,meta,target):
        blob.extend(b'\0'*(-len(blob)%4));offset=len(blob);blob.extend(data);vi=len(out['bufferViews']);out['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data),'target':target})
        m={k:copy.deepcopy(v)for k,v in meta.items()if k not in ('bufferView','byteOffset','sparse')};m['bufferView']=vi;out['accessors'].append(m);return len(out['accessors'])-1
    attrs={};hashes={}
    for role,ai in p['attributes'].items():
        values,fmt=elements(doc,binary,ai);data=b''.join(values[i]for i in vertices);meta=copy.deepcopy(doc['accessors'][ai]);meta['count']=len(vertices)
        if 'min'in meta or 'max'in meta:
            decoded=[struct.unpack(fmt,values[i])for i in vertices];meta['min']=[min(v[a]for v in decoded)for a in range(len(decoded[0]))];meta['max']=[max(v[a]for v in decoded)for a in range(len(decoded[0]))]
        attrs[role]=append(data,meta,34962);hashes[role]=hashlib.sha256(data).hexdigest()
    packed=struct.pack('<'+'I'*len(surviving),*(mapping[i]for i in surviving));ix=append(packed,{'componentType':5125,'type':'SCALAR','count':len(surviving),'min':[0],'max':[len(vertices)-1]},34963)
    out['meshes'][0]['primitives']=[{'attributes':attrs,'indices':ix,'material':0,'mode':4}];out['buffers']=[{'byteLength':len(blob)}]
    encoded=glb(out,blob);rd,rb=read(encoded);rp=rd['meshes'][0]['primitives'][0];values,fmt=elements(rd,rb,rp['indices']);new_ids=[struct.unpack(fmt,v)[0]for v in values]
    for role,ai in p['attributes'].items():
        before,_=elements(doc,binary,ai);after,_=elements(rd,rb,rp['attributes'][role])
        if [before[i]for i in surviving]!=[after[i]for i in new_ids]:raise ValueError('Bathroom remainder corner attributes differ')
    output.write_bytes(encoded)
    return {'node':node,'mesh':original['mesh'],'original_material':p['material'],'source_triangles':900,'removed_triangle_ids':sorted(REMOVALS[node]),'retained_triangle_ids':keep,'retained_triangles':len(keep),'retained_corner_attributes_byte_exact':True,'attribute_sha256':hashes,'glb_sha256':hashlib.sha256(encoded).hexdigest()}


def build(home,wc,output):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    home,wc,output=Path(home),Path(wc),Path(output);output.mkdir(parents=True,exist_ok=False)
    if hashlib.sha256(home.read_bytes()).hexdigest()!=HOME_SHA or hashlib.sha256(wc.read_bytes()).hexdigest()!=WC_SHA:raise ValueError('Exact original home and genuine CC0 WC required')
    hd,hb=read_gltf(home);wd,wb=read_gltf(wc);hm=world_matrices(hd);wm=world_matrices(wd)
    if len(wd['meshes'])!=10 or len(wd['materials'])!=3 or len(wd['nodes'])!=11:raise ValueError('Complete authentic source WC changed')
    floor=node_geometry(hd,hb,117,hm)
    if hd['nodes'][117].get('mesh')!=100 or len(floor)!=1 or floor[0]['material']!=60:raise ValueError('Exact actual bathroom tile slab required')
    floor_top=max(p[1]for p in floor[0]['points'])
    rows=[r for ni,n in enumerate(wd['nodes'])if 'mesh'in n for r in node_geometry(wd,wb,ni,wm)]
    positive=[];zero=[]
    for row in rows:
        for fi,face in enumerate(row['faces']):
            ps=[Vector(row['points'][j])for j in face]
            if (ps[1]-ps[0]).cross(ps[2]-ps[0]).length_squared>0:positive.extend(p.y for p in ps)
            else:zero.append([row['node'],fi])
    if not positive:raise ValueError('Genuine WC has no physical faces')
    physical_bottom=min(positive)
    translation=[-2.9,floor_top-physical_bottom,2.19]
    placed=[]
    for row in rows:
        row=dict(row);row['points']=[(-p[0]+translation[0],p[1]+translation[1],-p[2]+translation[2])for p in row['points']];placed.append(row)
    allpoints=[p for r in placed for p in r['points']];bounds=[[min(p[a]for p in allpoints)for a in range(3)],[max(p[a]for p in allpoints)for a in range(3)]]
    doc=copy.deepcopy(wd);roots=doc['scenes'][doc.get('scene',0)]['nodes'];wrapper=len(doc['nodes']);doc['nodes'].append({'name':'SUB01_RealWC_Placement_3dd8c8d5','translation':translation,'rotation':[0,1,0,0],'children':roots});doc['scenes'][doc.get('scene',0)]['nodes']=[wrapper]
    names={}
    for i,n in enumerate(doc['nodes'][:-1]):names[str(i)]=n.get('name');n['name']=f'SUB01_RealWC_3dd8c8d5_Node{i:03d}'
    export=output/'real-wc.glb';encoded=glb(doc,wb);export.write_bytes(encoded)
    od,ob=read(encoded)
    if ob!=wb or od['materials']!=wd['materials'] or od['meshes']!=wd['meshes']or od['textures']!=wd['textures']or od['images']!=wd['images']:raise ValueError('Genuine WC geometry/PBR bytes changed')
    remainders=[remainder(hd,hb,n,output/f'remainder-{n}.glb')for n in REMOVALS]
    report={'schema':'sub01.real-compact-wc-source.v1','home_sha256':HOME_SHA,'model_sha256':WC_SHA,'output_sha256':hashlib.sha256(encoded).hexdigest(),'translation_source_m':translation,'rotation_y_degrees':180,'bounds_source_m':bounds,'floor_node':117,'floor_top_m':floor_top,'source_bottom_m':physical_bottom,'exact_zero_area_source_faces':zero,'original_node_names':names,'complete_binary_and_pbr_unchanged':True,'source_triangles':sum(len(r['faces'])for r in rows),'remainders':remainders,'issues':[],'source_collision_proof_complete':False,'native_imported':False,'runtime_ready':False}
    def tree(points,faces):return BVHTree.FromPolygons([Vector(p)for p in points],faces,all_triangles=True,epsilon=0)
    wc_bvhs=[(row,tree(row['points'],row['faces']))for row in placed]
    contacts=0;boundary_contacts=0;contact_area=0.;contact_faces=[];foot_points=[]
    tile_top_faces=[i for i,f in enumerate(floor[0]['faces'])if all(abs(floor[0]['points'][j][1]-floor_top)<=1e-10 for j in f)]
    if len(tile_top_faces)!=2:raise ValueError('Exact two-triangle bathroom tile top required')
    def inside_top(point):
        for fi in tile_top_faces:
            a,b,c=[floor[0]['points'][j]for j in floor[0]['faces'][fi]]
            def cross(p,q,r):return(q[0]-p[0])*(r[2]-p[2])-(q[2]-p[2])*(r[0]-p[0])
            signs=[cross(a,b,point),cross(b,c,point),cross(c,a,point)]
            if min(signs)>=0 or max(signs)<=0:return True
        return False
    for row in placed:
        for fi,face in enumerate(row['faces']):
            points=[row['points'][j]for j in face]
            if all(abs(p[1]-floor_top)<=1e-7 for p in points):
                area=(Vector(points[1])-Vector(points[0])).cross(Vector(points[2])-Vector(points[0])).length*.5
                if area>0:contact_area+=area;contact_faces.append((row['node'],fi));foot_points.extend(points)
    if contact_area<=0 or not all(inside_top(p)for p in foot_points):report['issues'].append({'support':'Positive-area real pedestal foot is not fully on actual tile top triangles'})
    for ni,node in enumerate(hd['nodes']):
        if 'mesh'not in node:continue
        for pi,p in enumerate(hd['meshes'][node['mesh']]['primitives']):
            a=hd['accessors'][p['attributes']['POSITION']]
            corners=[transformed(hm[ni],(x,y,z))for x in(a['min'][0],a['max'][0])for y in(a['min'][1],a['max'][1])for z in(a['min'][2],a['max'][2])]
            lo=[min(q[k]for q in corners)for k in range(3)];hi=[max(q[k]for q in corners)for k in range(3)]
            if any(hi[k]<bounds[0][k]or lo[k]>bounds[1][k]for k in range(3)):continue
            row=node_geometry(hd,hb,ni,hm)[pi];kept=[i for i in range(len(row['faces']))if i not in REMOVALS.get(ni,set())];faces=[row['faces'][i]for i in kept]
            if not faces:continue
            ht=tree(row['points'],faces)
            for model,wt in wc_bvhs:
                for wi,hi in wt.overlap(ht):
                    wp=[model['points'][j]for j in model['faces'][wi]];hp=[row['points'][j]for j in faces[hi]]
                    # Exact source tile top separates the entire pedestal face
                    # from the solid slab. Side-face bottom edges are legitimate
                    # boundary contacts too; no penetrating face is exempted.
                    if ni==117 and model['node']==0 and kept[hi]in tile_top_faces and contact_area>0 and min(q[1]for q in wp)>=floor_top-1e-7 and all(abs(q[1]-floor_top)<=1e-7 for q in hp):
                        if (model['node'],wi)in contact_faces:contacts+=1
                        else:boundary_contacts+=1
                        continue
                    report['issues'].append({'wc_node':model['node'],'wc_triangle':wi,'home_node':ni,'home_triangle':kept[hi]})
    report.update(source_collision_proof_complete=True,exact_floor_contact_pairs=contacts,exact_nonpenetrating_pedestal_edge_contact_pairs=boundary_contacts,actual_tile_top_triangle_ids=tile_top_faces,foot_vertices_inside_actual_tile_top_triangles=all(inside_top(p)for p in foot_points),positive_area_foot_contact_m2=contact_area,ok=not report['issues'])
    (output/'wc-source-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['issues']:raise RuntimeError('Actual WC source geometry collision/support refused '+json.dumps(report['issues'][:8]))
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(export))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if len(meshes)!=10:raise RuntimeError('Blender did not retain complete authentic10-part WC')
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(output/'real-compact-wc.blend'))
    report['editable_blend_sha256']=hashlib.sha256((output/'real-compact-wc.blend').read_bytes()).hexdigest()
    (output/'wc-source-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print('ACTUAL_REAL_WC_SOURCE_PASS',report['source_triangles'],report['positive_area_foot_contact_m2'],flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--wc',required=True);p.add_argument('--output',required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);build(args.home,args.wc,args.output)
