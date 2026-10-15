// Assemble genuine Blender geometry into the authoritative original65 GLB.
// Original body/animation binary is a byte-exact prefix, not re-exported.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {Matrix4,Quaternion,Vector3} from '../web/house/vendor/three.core.js';
import {loadGLB,values,Appender,clipBarycentricTriangle} from './gltf_binary_patch.mjs';
const [originalPath,geometryPath,packetPath,outputPath]=process.argv.slice(2);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const original=loadGLB(originalPath),geometry=loadGLB(geometryPath),packet=JSON.parse(fs.readFileSync(packetPath));
assert.equal(sha(original.raw),packet.original_body_sha256);assert.equal(sha(geometry.raw),packet.geometry_sha256);
const writer=new Appender(original),d=writer.doc,normalize=n=>n.replace(/^mixamorig[:_]?/i,'');
const toY=([x,y,z])=>[x,z,-y],C=new Matrix4().set(1,0,0,0,0,0,1,0,0,-1,0,0,0,0,0,1);
const oldSkin=original.doc.skins[0];assert.equal(oldSkin.joints.length,65);
const names=new Map(oldSkin.joints.map((n,i)=>[normalize(d.nodes[n].name),{node:n,index:i}]));assert.equal(names.size,65);
const parents=new Map();d.nodes.forEach((n,i)=>(n.children||[]).forEach(c=>parents.set(c,i)));
function world(nodes,i,cache=new Map()){if(cache.has(i))return cache.get(i);const n=nodes[i],m=n.matrix?new Matrix4().fromArray(n.matrix):new Matrix4().compose(new Vector3().fromArray(n.translation||[0,0,0]),new Quaternion().fromArray(n.rotation||[0,0,0,1]),new Vector3().fromArray(n.scale||[1,1,1]));if(parents.has(i))m.premultiply(world(nodes,parents.get(i),cache));cache.set(i,m);return m;}
const originalWorlds=new Map();oldSkin.joints.forEach(i=>world(original.doc.nodes,i,originalWorlds));
const originalIBMs=values(original,oldSkin.inverseBindMatrices),newIBMs=originalIBMs.map(r=>r.slice());
const desiredWorlds=new Map(),binds=packet.new_finger_bind_worlds_original_scale_0p01;assert.equal(Object.keys(binds).length,40);
for(const[name,rows]of Object.entries(binds)){
 const key=normalize(name),entry=names.get(key);assert(entry&&/Hand(Thumb|Index|Middle|Ring|Pinky)[1-4]$/.test(key));
 const bind=new Matrix4().set(...rows.flat()).premultiply(C),side=key.startsWith('Left')?'Left':'Right';
 const hand=names.get(side+'Hand'),handBind=new Matrix4().fromArray(originalIBMs[hand.index]).invert();
 const wristDeformation=originalWorlds.get(hand.node).clone().multiply(handBind.clone().invert());
 desiredWorlds.set(entry.node,wristDeformation.multiply(bind));newIBMs[entry.index]=bind.clone().invert().elements;
}
for(const[node,desired]of desiredWorlds){const parent=parents.get(node),parentWorld=desiredWorlds.get(parent)||originalWorlds.get(parent);assert(parentWorld);const local=parentWorld.clone().invert().multiply(desired),position=new Vector3(),rotation=new Quaternion(),scale=new Vector3();local.decompose(position,rotation,scale);assert(Math.max(scale.x,scale.y,scale.z)-Math.min(scale.x,scale.y,scale.z)<1e-5);const n=d.nodes[node];delete n.matrix;n.translation=position.toArray();n.rotation=rotation.toArray();n.scale=scale.toArray();}
d.skins[0].inverseBindMatrices=writer.accessor(newIBMs,'MAT4');
const clipping=[],removedByPrimitive=new Map(),pendingIndices=new Map();
for(const mask of packet.original_triangle_retirement_masks){
 const point=toY(mask.clip_plane_point_m),normal=toY(mask.clip_plane_normal),plane={normal,offset:normal.reduce((s,x,i)=>s+x*point[i],0)};
 const grouped=new Map();for(const r of mask.original_main_mesh_triangles_touched){if(!grouped.has(r.primitive))grouped.set(r.primitive,new Set());assert(!grouped.get(r.primitive).has(r.triangle));grouped.get(r.primitive).add(r.triangle);}
 for(const[primitiveIndex,touched]of grouped){
  const p=d.meshes[0].primitives[primitiveIndex],sourcePrimitive=original.doc.meshes[0].primitives[primitiveIndex];
  assert.equal(p.indices,sourcePrimitive.indices,'Overlapping side retirement masks require explicit combined clipping');
  const indices=values(original,p.indices).map(r=>r[0]),attrs=Object.fromEntries(Object.entries(p.attributes).map(([k,i])=>[k,values(original,i)])),kept=[],fragments=[];
  if(!removedByPrimitive.has(primitiveIndex))removedByPrimitive.set(primitiveIndex,new Set());const removed=removedByPrimitive.get(primitiveIndex);
  let retired=0,crossings=0;assert.equal(indices.length%3,0);
  for(let triangle=0;triangle<indices.length/3;triangle++){
   const ids=indices.slice(triangle*3,triangle*3+3);if(!touched.has(triangle)){if(!removed.has(triangle))kept.push(...ids);continue;}
   assert(!removed.has(triangle),'Both hand masks touch the same original triangle');removed.add(triangle);
   const clipped=clipBarycentricTriangle(ids.map(i=>attrs.POSITION[i]),plane);
   assert(clipped.length<3||clipped.length!==3||clipped.some(v=>v.b.some(x=>x>0&&x<1)),'Retirement mask contains an entirely retained source triangle');
   if(clipped.length<3){retired++;continue;}crossings++;
   for(let i=1;i<clipped.length-1;i++)fragments.push([clipped[0],clipped[i],clipped[i+1]].map(v=>({ids,b:v.b,p:v.p})));
  }
  assert(kept.length>0&&touched.size===retired+crossings);
  pendingIndices.set(primitiveIndex,kept);
  if(fragments.length){
   const vertices=fragments.flat(),outAttrs={};
   for(const[name,rows]of Object.entries(attrs)){
    if(/^(JOINTS|WEIGHTS)_/.test(name))continue;
    const a=original.doc.accessors[p.attributes[name]],result=vertices.map(v=>name==='POSITION'?v.p:v.ids.reduce((sum,index,k)=>sum.map((x,j)=>x+rows[index][j]*v.b[k]),Array(rows[0].length).fill(0)));
    if(name==='NORMAL'||name==='TANGENT')for(const row of result){const length=Math.hypot(...row.slice(0,3));assert(length>1e-8);for(let k=0;k<3;k++)row[k]/=length;}
    outAttrs[name]=writer.accessor(result,a.type,a.componentType,a.normalized||false);
   }
   const influences=vertices.map(v=>{const merged=new Map();for(let j=0;j<v.ids.length;j++)for(const set of[0,1]){const js=attrs['JOINTS_'+set]?.[v.ids[j]],ws=attrs['WEIGHTS_'+set]?.[v.ids[j]];if(!js)continue;assert(ws);for(let k=0;k<js.length;k++)if(ws[k]*v.b[j]>1e-12)merged.set(js[k],(merged.get(js[k])||0)+ws[k]*v.b[j]);}const rows=[...merged].sort((a,b)=>b[1]-a[1]);assert(rows.length<=8,'Never discard skin influences on a clipped edge');const total=rows.reduce((s,r)=>s+r[1],0);assert(total>.99&&total<1.01);while(rows.length<8)rows.push([0,0]);return rows.map(([joint,weight])=>[joint,weight/total]);});
   for(const set of[0,1]){outAttrs['JOINTS_'+set]=writer.accessor(influences.map(r=>r.slice(set*4,set*4+4).map(x=>x[0])),'VEC4',5123);outAttrs['WEIGHTS_'+set]=writer.accessor(influences.map(r=>r.slice(set*4,set*4+4).map(x=>x[1])),'VEC4');}
   d.meshes[0].primitives.push({attributes:outAttrs,indices:writer.accessor(vertices.map((_,i)=>[i]),'SCALAR',5125),material:p.material,mode:4,extras:{actual_source_clipped_boundary:mask.side}});
  }
  clipping.push({side:mask.side,primitive:primitiveIndex,touched:touched.size,retired,crossings,retained_original_triangles:kept.length/3,clipped_fragment_triangles:fragments.length});
 }
}
for(const[primitive,indices]of pendingIndices)d.meshes[0].primitives[primitive].indices=writer.accessor(indices.map(i=>[i]),'SCALAR',5125);
// Copy canonical resources; only skin joint indices need a new accessor.
const offset=writer.bytes(geometry.bin),viewBase=d.bufferViews.length,accessorBase=d.accessors.length;
for(const v of geometry.doc.bufferViews){assert(!v.extensions);d.bufferViews.push({...v,buffer:0,byteOffset:offset+(v.byteOffset||0)});}
for(const a of geometry.doc.accessors){assert(!a.sparse);d.accessors.push({...a,bufferView:viewBase+a.bufferView});}
const imageBase=(d.images||=[]).length,samplerBase=(d.samplers||=[]).length,textureBase=(d.textures||=[]).length,materialBase=(d.materials||=[]).length;
for(const image of geometry.doc.images||[]){assert(!image.uri);d.images.push({...image,bufferView:viewBase+image.bufferView});}
for(const sampler of geometry.doc.samplers||[])d.samplers.push(structuredClone(sampler));
for(const texture of geometry.doc.textures||[]){assert(!texture.extensions);d.textures.push({...texture,...(texture.source!==undefined?{source:imageBase+texture.source}:{}),...(texture.sampler!==undefined?{sampler:samplerBase+texture.sampler}:{})});}
function textureRefs(value,key=''){if(!value||typeof value!=='object')return;if(key.endsWith('Texture')&&Number.isInteger(value.index))value.index+=textureBase;for(const[k,v]of Object.entries(value))textureRefs(v,k);}
for(const material of geometry.doc.materials||[]){const copy=structuredClone(material);textureRefs(copy);d.materials.push(copy);}
const geometryNodes=geometry.doc.nodes.filter(n=>n.mesh!==undefined),added=[];
for(const node of geometryNodes){assert(Number.isInteger(node.skin));const skin=geometry.doc.skins[node.skin],jointMap=skin.joints.map(i=>{const target=names.get(normalize(geometry.doc.nodes[i].name));assert(target,'Unmapped anatomical source bone');return target.index;});const mesh=structuredClone(geometry.doc.meshes[node.mesh]);
 for(const p of mesh.primitives){assert((p.mode??4)===4&&!p.targets);p.indices+=accessorBase;if(p.material!==undefined)p.material+=materialBase;for(const[name,index]of Object.entries(p.attributes)){if(name.startsWith('JOINTS_')){const a=geometry.doc.accessors[index];p.attributes[name]=writer.accessor(values(geometry,index).map(row=>row.map(i=>{assert(i<jointMap.length);return jointMap[i];})),a.type,a.componentType);}else p.attributes[name]=index+accessorBase;}}
 const meshIndex=d.meshes.length;d.meshes.push(mesh);const nodeIndex=d.nodes.length;d.nodes.push({name:node.name,mesh:meshIndex,skin:0});d.scenes[d.scene||0].nodes.push(nodeIndex);added.push({name:node.name,node:nodeIndex,primitives:mesh.primitives.length});
}
d.extensionsUsed=[...new Set([...(d.extensionsUsed||[]),...(geometry.doc.extensionsUsed||[])])];
d.extensionsRequired=[...new Set([...(d.extensionsRequired||[]),...(geometry.doc.extensionsRequired||[])])];
// Old finger curves target obsolete rests. Retarget separately before selection.
delete d.animations;
writer.finish(outputPath);
const after=loadGLB(outputPath);assert(after.bin.subarray(0,original.bin.length).equals(original.bin));
for(const[name,entry]of names)if(!/Hand(Thumb|Index|Middle|Ring|Pinky)[1-4]$/.test(name))assert.deepEqual(d.nodes[entry.node],original.doc.nodes[entry.node]);
fs.writeFileSync(outputPath+'.assembly.json',JSON.stringify({schema:'sub01.original65-canonical-hand-assembly.v1',original_sha256:sha(original.raw),canonical_geometry_sha256:sha(geometry.raw),output_sha256:sha(after.raw),original_binary_prefix_exact:true,original25_nonfinger_nodes_exact:true,skin65_names_hierarchy_preserved:true,changed_finger_binds:40,clipping,added_meshes:added,old_animation_curves_not_selected:true,native_or_contact_accepted:false},null,2)+'\n');
console.log(JSON.stringify({output_sha256:sha(after.raw),clipping,added_meshes:added}));
