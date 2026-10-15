import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {clipBarycentricTriangle,Appender,loadGLB,values} from '../tools/gltf_binary_patch.mjs';
const plane={normal:[1,0,0],offset:0};
test('crossing source triangle retains exact negative halfspace and barycentric UV support',()=>{
 const p=clipBarycentricTriangle([[-1,0,0],[1,0,0],[-1,2,0]],plane);assert.equal(p.length,4);
 const boundary=p.find(v=>Math.abs(v.p[0])<1e-8&&Math.abs(v.p[1]-1)<1e-8);assert.deepEqual(boundary.b,[0,.5,.5]);
 assert(p.every(v=>v.p[0]<=1e-10&&Math.abs(v.b.reduce((a,b)=>a+b)-1)<1e-10));
 let area=0;for(let i=1;i<p.length-1;i++)area+=Math.abs((p[i].p[0]-p[0].p[0])*(p[i+1].p[1]-p[0].p[1])-(p[i].p[1]-p[0].p[1])*(p[i+1].p[0]-p[0].p[0]))/2;
 assert.equal(area,1.5);
});
test('fully retained and fully retired triangles never grow arbitrary replacement faces',()=>{
 const source=[[-1,0,0],[-2,0,0],[-1,1,0]];assert.deepEqual(clipBarycentricTriangle(source,plane).map(v=>v.p),source);
 assert.equal(clipBarycentricTriangle(source.map(p=>[-p[0],p[1],p[2]]),plane).length,0);
});
test('actual normalized uint16 UV, signed normals and uint8 weights roundtrip without unit errors',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sub01-glb-normalized-'));try{
  const a=new Appender({doc:{asset:{version:'2.0'},buffers:[{}],bufferViews:[],accessors:[]},bin:Buffer.alloc(4)});
  const uv=a.accessor([[.4,.8]],'VEC2',5123,true),normal=a.accessor([[-1,0,1]],'VEC3',5122,true),weights=a.accessor([[.2,.4,.4,0]],'VEC4',5121,true);
  const file=path.join(dir,'test.glb');a.finish(file);const f=loadGLB(file);
  assert(Math.abs(values(f,uv)[0][0]-.4)<=.5/65535);assert.deepEqual(values(f,normal)[0],[-1,0,1]);assert.deepEqual(values(f,weights)[0],[.2,.4,.4,0]);
 }finally{fs.rmSync(dir,{recursive:true});}
});
