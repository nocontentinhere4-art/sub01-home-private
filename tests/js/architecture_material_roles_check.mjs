import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
const source=fs.readFileSync('web/house/home.js','utf8');
const oak=new T.MeshStandardMaterial(),plaster=new T.MeshStandardMaterial();
const M={architectureOak:oak,wall:plaster};
const scannedWood=new T.MeshStandardMaterial({map:new T.Texture(),normalMap:new T.Texture(),roughnessMap:new T.Texture()});
const scene=new T.Scene(),boxes=[];
const box=(...args)=>boxes.push(args);
const start=source.indexOf('function floor('),end=source.indexOf('\nfunction rug(',start);
const floor=new Function('T','scannedWood','scene','box','M',source.slice(start,end)+';return floor;')(T,scannedWood,scene,box,M);
for(const [w,d,x,y,z] of [[8,8,0,0,0],[3.8,8,-2.1,3,0],[1,2.15,.3,3,-2.775],[3.8,1.25,-2.1,3,4.625]]){
 floor(w,d,x,y,z);
 const slab=boxes.at(-1),top=scene.children.at(-1);
 assert.deepEqual(slab.slice(0,6),[w,.12,d,x,y-.06,z],'supporting slab dimensions/position unchanged');
 assert.equal(slab[6],y>0?plaster:oak);
 assert.equal(slab[7],0);
 assert.equal(top.geometry.type,'PlaneGeometry');assert.equal(top.position.y,y+.025);
 assert.deepEqual(top.material.map.repeat.toArray(),[w/1.2,d/1.2],'oak top uses actual scan coverage');
 assert.notEqual(top.material.map,scannedWood.map);
}
const stairStart=source.indexOf('for (let i = 0; i < 17; i++) {',source.indexOf('const STEP ='));
const stairEnd=source.indexOf('\nfor (const x of',stairStart);
const stairs=[];
new Function('box','M',source.slice(stairStart,stairEnd))((...args)=>stairs.push(args),M);
assert.equal(stairs.length,34,'17 supporting bodies and 17 independent oak treads, no extra geometry');
for(let i=0;i<17;i++){
 const body=stairs[i*2],tread=stairs[i*2+1],h=(i+1)*3/17,z=2.55-(i+.5)*.25;
 assert.deepEqual(body.slice(0,6),[.96,h,.25,.3,h/2,z]);
 assert.deepEqual(tread.slice(0,6),[1.02,.035,.27,.3,h+.006,z]);
 assert.equal(body[6],plaster);assert.equal(tread[6],oak);
 assert.ok(!Array.isArray(body[6])&&!Array.isArray(tread[6]),'single-material receiver path remains bake-compatible');
}
console.log('PASS: slab/stair counts and repaired landing footprint; upper plaster soffits/body, oak top/treads/nosing; physical top UV; single-material bake receivers');
