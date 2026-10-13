import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {createShadowFit}from '../../web/house/shadow_fit.mjs';
import {homeLighting}from '../../web/house/lighting.mjs';
const scene=new T.Scene();
const box=(dimensions,position,parent=scene)=>{
 const m=new T.Mesh(new T.BoxGeometry(...dimensions),new T.MeshBasicMaterial());m.castShadow=true;m.position.fromArray(position);parent.add(m);return m;
};
box([8,6.6,8],[0,3.2,0]);box([.2,1.15,.2],[2.7,.575,6.25]);
const hidden=new T.Group();hidden.visible=false;scene.add(hidden);box([1000,1000,1000],[0,0,0],hidden);
const sphere=new T.Mesh(new T.SphereGeometry(110));sphere.castShadow=false;scene.add(sphere);
const fence=new T.InstancedMesh(new T.BoxGeometry(.025,.8,.025),new T.MeshBasicMaterial(),3);fence.castShadow=true;
for(let i=0;i<3;i++)fence.setMatrixAt(i,new T.Matrix4().makeTranslation(-3+i,.6,6.25));scene.add(fence);
const fit=createShadowFit(T);assert.equal(fit.capture(scene).casters,5);
const light=new T.DirectionalLight();scene.add(light,light.target);light.target.position.set(0,1,0);light.shadow.mapSize.set(2048,2048);light.shadow.normalBias=.025;
const reports=[];
for(let hour=6;hour<=18;hour+=.25){
 light.position.fromArray(homeLighting((hour-9)*3600).sunPosition);const r=fit.fit(light);assert.equal(fit.coverage(light).outside,0);
 assert.equal(light.shadow.normalBias,.025);assert.equal(light.shadow.mapSize.x,2048);
 assert.ok(r.width<20&&r.height<20);reports.push(r);
 const previous=light.shadow.camera.projectionMatrix.clone();fit.fit(light);assert.deepEqual(light.shadow.camera.projectionMatrix.elements,previous.elements,'stable repeated fit');
}
const original=scene.children[0].position.clone();fit.fit(light);assert.ok(scene.children[0].position.equals(original),'no object/camera-state changes');
assert.equal(createShadowFit(T).fit(light),null);
console.log('PASS:49 real homeLighting orientations, caster/instance coverage, excludes invisible geometry/noncasting panorama, stable center/projection, unchanged bias/map size, no scene mutation');
console.log('Projection ranges:',Math.min(...reports.map(r=>r.width)).toFixed(3),Math.max(...reports.map(r=>r.width)).toFixed(3),Math.min(...reports.map(r=>r.height)).toFixed(3),Math.max(...reports.map(r=>r.height)).toFixed(3));
