import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {writeGLB,readGLB,uncompress,accessorHashes} from '../../tools/uncompress_unreal_glb.mjs';
import {mergeSkinClips} from '../../tools/merge_unreal_skin_clips.mjs';
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'sub01-ue-skin-check-'));
try{
 const owner=path.join(folder,'owner.glb'),plain=path.join(folder,'plain.glb'),clip=path.join(folder,'typing.glb'),merged=path.join(folder,'merged.glb');
 const nodes=[{name:'Hips',children:[1,2]},{name:'LeftHandIndex1',translation:[-1,1,0]},{name:'RightHandIndex1',translation:[1,1,0]}];
 const doc={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0]}],nodes,skins:[{joints:[0,1,2]}],meshes:[],buffers:[{byteLength:20}],bufferViews:[{buffer:0,byteLength:16},{buffer:0,byteOffset:16,byteLength:4}],accessors:[{bufferView:0,componentType:5126,count:1,type:'VEC4'},{bufferView:1,componentType:5121,count:1,type:'VEC4',normalized:true}]};
 const bytes=Buffer.alloc(20);bytes.writeFloatLE(1,12);bytes[16]=255;writeGLB(owner,doc,bytes);
 const original=fs.readFileSync(owner);
 await uncompress(owner,plain);assert.equal(fs.readFileSync(owner).equals(original),true);assert.deepEqual(await accessorHashes(readGLB(owner)),await accessorHashes(readGLB(plain)));
 const captured={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0]}],nodes:structuredClone(nodes),buffers:[{byteLength:40}],bufferViews:[{buffer:0,byteOffset:0,byteLength:8},{buffer:0,byteOffset:8,byteLength:32}],accessors:[{bufferView:0,componentType:5126,count:2,type:'SCALAR',min:[0],max:[1]},{bufferView:1,componentType:5126,count:2,type:'VEC4'}],animations:[{name:'mixamo.com',samplers:[{input:0,output:1}],channels:[{sampler:0,target:{node:1,path:'rotation'}}]}]};
 const motion=Buffer.alloc(40);motion.writeFloatLE(1,4);motion.writeFloatLE(1,20);motion.writeFloatLE(Math.sin(.15),24);motion.writeFloatLE(Math.cos(.15),36);writeGLB(clip,captured,motion);
 await mergeSkinClips(plain,[clip],merged);const out=readGLB(merged);
 assert.equal(out.doc.animations[0].name,'typing','logical asset name disambiguates generic Mixamo source clip names');
 assert.equal(out.doc.animations[0].channels[0].target.node,1);
 assert.deepEqual(out.doc.skins,doc.skins);assert.deepEqual(out.doc.nodes,nodes);
 const hashes=await accessorHashes(out);assert.equal(hashes[1].normalized,true);assert.deepEqual(hashes.slice(2),await accessorHashes(readGLB(clip)),'captured quaternion/timing bytes preserved');
 captured.nodes[1].translation[0]-=.1;writeGLB(clip,captured,motion);
 await assert.rejects(()=>mergeSkinClips(plain,[clip],merged),/reference-pose world differs/,'same bone names alone must not pass different bind/rest');
 captured.nodes[1].translation[0]+=.1;captured.nodes[1].name='UnknownFinger';writeGLB(clip,captured,motion);
 await assert.rejects(()=>mergeSkinClips(plain,[clip],merged),/no exact canonical skin joint/);
 console.log('PASS: plain format conversion leaves source/normalized accessor data unchanged; one canonical skin retains graphs and exact captured quaternion/time bytes; generic clip name disambiguated; wrong rest/bind and missing finger rejected before import.');
}finally{fs.rmSync(folder,{recursive:true,force:true});}
