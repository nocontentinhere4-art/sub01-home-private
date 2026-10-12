import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';

// Execute the real floor and staircase construction against Three meshes,
// then raycast triangles rather than inferring support from floorAt alone.
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const scene=new T.Scene();
const material=new T.MeshStandardMaterial({map:new T.Texture(),normalMap:new T.Texture(),roughnessMap:new T.Texture()});
const M={wall:material,architectureOak:material};
const box=(w,h,d,x,y,z,m)=>{
  const mesh=new T.Mesh(new T.BoxGeometry(w,h,d),m);
  mesh.position.set(x,y,z);scene.add(mesh);
};
const fn=source.slice(source.indexOf('function floor('),source.indexOf('function rug('));
const floor=new Function('T','scene','scannedWood','box','M',fn+';return floor;')(T,scene,material,box,M);
const architecture=source.slice(source.indexOf('// Architecture: loft'),source.indexOf('box(8, 0.2, 8'));
new Function('floor',architecture)(floor);
const begin=source.indexOf('for (let i = 0; i < 17; i++) {',source.indexOf('const STEP ='));
new Function('box','M',source.slice(begin,source.indexOf('for (const x of [-0.25, 0.85])',begin)))(box,M);
scene.updateMatrixWorld(true);
const ray=new T.Raycaster();
const supported=(x,z)=>{
  ray.set(new T.Vector3(x,3.2,z),new T.Vector3(0,-1,0));
  const hit=ray.intersectObjects(scene.children,false)[0];
  assert.ok(hit && hit.point.y>=3-.001,`Upper landing unsupported at ${x}, ${z}: ${hit?.point.y}`);
};
// Real full-width bridge to last nosing, including formerly unsupported .14m.
for(const x of [-.05,.3,.65])
  for(let i=0;i<=100;i++) supported(x,-1.69-i*.0042);
supported(.3,-3.84);
const upperPlanes=scene.children.filter(m=>m.geometry.type==='PlaneGeometry'&&Math.abs(m.position.y-3.025)<1e-6);
const landing=upperPlanes.find(m=>Math.abs(m.position.x-.3)<1e-6);
assert.ok(landing);
assert.ok(Math.abs(landing.position.z-landing.geometry.parameters.height/2-(-3.85))<1e-8,'Rear boundary preserved');
assert.ok(Math.abs(landing.position.z+landing.geometry.parameters.height/2-(-1.7))<1e-8,'Top meets real last stair');
console.log('PASS: actual Three triangle support across full stair→landing, preserved rear boundary and top connection');
