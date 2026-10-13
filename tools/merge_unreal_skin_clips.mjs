// Bundle canonical real skin + retargeted real clips in one official glTF import.
// One import creates its actual SkeletalMesh/USkeleton/AnimSequences together.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {basename} from 'node:path';
import {Matrix4,Quaternion,Vector3} from '../web/house/vendor/three.core.js';
import {readGLB,writeGLB,accessorHashes} from './uncompress_unreal_glb.mjs';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function world(file){
 const parent=new Map();file.doc.nodes.forEach((n,i)=>(n.children||[]).forEach(child=>{assert(!parent.has(child));parent.set(child,i);}));
 const result=new Map(),active=new Set();
 function visit(i){if(result.has(i))return result.get(i);assert(!active.has(i));active.add(i);const n=file.doc.nodes[i],local=n.matrix?new Matrix4().fromArray(n.matrix):new Matrix4().compose(new Vector3().fromArray(n.translation||[0,0,0]),new Quaternion().fromArray(n.rotation||[0,0,0,1]),new Vector3().fromArray(n.scale||[1,1,1]));const m=parent.has(i)?visit(parent.get(i)).clone().multiply(local):local;active.delete(i);result.set(i,m);return m;}
 file.doc.nodes.forEach((_,i)=>visit(i));return result;
}
export async function mergeSkinClips(ownerPath,clipPaths,output){
 const owner=readGLB(ownerPath);assert(owner.doc.skins?.length===1);assert(!owner.doc.extensionsRequired?.length,'Owner still requires compressed/noncore glTF decoding');
 const doc=structuredClone(owner.doc),ownerHashes=await accessorHashes(owner),nodes=new Map(),ownerWorld=world(owner),chunks=[owner.bin],inputs=[];let bytes=owner.bin.length;
 for(const joint of doc.skins[0].joints){const name=doc.nodes[joint].name;assert(name&&!nodes.has(name),'Duplicate/unnamed canonical skin joint');nodes.set(name,joint);}
 doc.animations=[];const names=new Set();
 for(const path of clipPaths){
  const clip=readGLB(path);assert(!clip.doc.meshes?.length&&!clip.doc.skins?.length,'Clip must not import a second skin/mesh');assert(!clip.doc.extensionsRequired?.length);assert(clip.doc.animations?.length);
  const positions=world(clip),viewOffset=doc.bufferViews.length,accessorOffset=doc.accessors.length;
  for(const view of clip.doc.bufferViews){assert.equal(view.buffer,0);assert(!view.extensions?.EXT_meshopt_compression);doc.bufferViews.push({...view,byteOffset:(view.byteOffset||0)+bytes});}
  for(const accessor of clip.doc.accessors){assert(!accessor.sparse);doc.accessors.push({...accessor,bufferView:accessor.bufferView+viewOffset});}
  for(const animation of clip.doc.animations){
   assert(animation.name,'Captured clip name missing');
   const converted=structuredClone(animation);
   converted.name=basename(path,'.glb')+(clip.doc.animations.length>1?'__'+animation.name:'');
   assert(!names.has(converted.name),'Logical clip asset name duplicate');names.add(converted.name);
   for(const sampler of converted.samplers){sampler.input+=accessorOffset;sampler.output+=accessorOffset;}
   for(const channel of converted.channels){
    const sourceIndex=channel.target.node,name=clip.doc.nodes[sourceIndex].name;assert(nodes.has(name),'Captured channel has no exact canonical skin joint: '+name);
    const targetIndex=nodes.get(name),a=positions.get(sourceIndex).elements,b=ownerWorld.get(targetIndex).elements;
    assert(Math.max(...a.map((v,i)=>Math.abs(v-b[i])))<1e-5,'Retargeted reference-pose world differs from owner: '+name);
    channel.target.node=targetIndex;
   }doc.animations.push(converted);
  }
  chunks.push(clip.bin);bytes+=clip.bin.length;inputs.push({file:path,sha256:clip.sha,animations:clip.doc.animations.map(a=>a.name),accessor_hashes:await accessorHashes(clip)});
 }
 doc.buffers=[{byteLength:bytes}];writeGLB(output,doc,Buffer.concat(chunks));
 const combined=readGLB(output),combinedHashes=await accessorHashes(combined);
 assert.deepEqual(combinedHashes.slice(0,ownerHashes.length),ownerHashes,'Canonical geometry/weights/joints/IBMs changed');
 let offset=ownerHashes.length;for(const input of inputs){assert.deepEqual(combinedHashes.slice(offset,offset+input.accessor_hashes.length),input.accessor_hashes,'Captured clip accessor values changed');offset+=input.accessor_hashes.length;delete input.accessor_hashes;}
 assert.deepEqual(doc.skins,owner.doc.skins);assert.deepEqual(doc.nodes,owner.doc.nodes);assert.deepEqual(doc.meshes,owner.doc.meshes);
 const audit={canonical_owner_sha256:owner.sha,output_sha256:combined.sha,skin_joints:nodes.size,canonical_owner_accessors_unchanged:ownerHashes.length,captured_inputs:inputs,animations:doc.animations.map(a=>a.name),all_captured_animation_values_unchanged:true,reference_pose_alignment_verified:true,scope:'Actual source skin/reference pose and real retargeted motion bundled for one import; UE imported skeleton/POV/contact still unverified'};
 fs.writeFileSync(output+'.audit.json',JSON.stringify(audit,null,2)+'\n');return audit;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const[owner,output,...clips]=process.argv.slice(2);assert(owner&&output&&clips.length,'Usage OWNER.glb OUTPUT.glb CLIP.glb [...]');console.log(JSON.stringify(await mergeSkinClips(owner,clips,output)));}
