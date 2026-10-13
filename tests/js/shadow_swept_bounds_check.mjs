import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
import{createShadowFit,homeShadowSweptBounds}from '../../web/house/shadow_fit.mjs';
import{createBalconyDoor}from '../../web/house/balcony_access.mjs';
import{createResidentialForeground}from '../../web/house/residential_foreground.mjs';
import{createCurtainPanel}from '../../web/house/curtain_panels.mjs';
import{homeLighting}from '../../web/house/lighting.mjs';
import{BATHROOM_ACCESS}from '../../web/house/bathroom_access.mjs';
import{GLTFLoader}from '../../web/house/vendor/GLTFLoader.js';
import{attachUpperCabinetDoors,CABINET_DOOR_POLICY}from '../../web/house/cabinet_doors.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
// These fixture dimensions must stay synchronized with the actual house builder.
for(const fragment of['frontDoorGroup.position.set(1.47, 0, 3.9)','box(1.05, 2.2, 0.075, 0, 0, 0','frontDoor.position.set(0.525, 1.1, 0)','box(0.065, 2, 0.89, -0.85, 4.05, 1.35','entranceOpen ? -Math.PI * 0.48 : 0','for (const anchor of [-3.8, -0.2])','panel.group.position.set(anchor, 4.43, 3.82)'])assert.ok(source.includes(fragment),`Actual-source fixture drift: ${fragment}`);
const scene=new T.Scene(),material=new T.MeshStandardMaterial();
const front=new T.Group();front.position.set(1.47,0,3.9);scene.add(front);
const frontLeaf=new T.Mesh(new T.BoxGeometry(1.05,2.2,.075),material);frontLeaf.position.set(.525,1.1,0);front.add(frontLeaf);
const knob=new T.Mesh(new T.SphereGeometry(.027,12,8),material);knob.position.set(.94,1.05,-.06);front.add(knob);
const bath=new T.Mesh(new T.BoxGeometry(.065,2,.89),material);bath.position.set(-.85,4.05,1.35);scene.add(bath);
const balcony=createBalconyDoor(T,scene,material),foreground=createResidentialForeground(T,scene,{gateOpen:true});
const curtains=[-3.8,-.2].map(anchor=>{const p=createCurtainPanel(T,material,{direction:anchor<-2?1:-1});p.group.position.set(anchor,4.43,3.82);scene.add(p.group);return p;});
const cabinetBytes=fs.readFileSync(new URL('../../web/house/assets/kitchen-cabinet-original/cabinet.glb',import.meta.url));
const cabinet=(await new GLTFLoader().parseAsync(cabinetBytes.buffer.slice(cabinetBytes.byteOffset,cabinetBytes.byteOffset+cabinetBytes.byteLength),'')).scene;
assert.ok(source.includes('root.position.set(-2.2, 2.05, -3.71)'));
cabinet.position.set(-2.2,2.05,-3.71);scene.add(cabinet);
const cabinetDoors=attachUpperCabinetDoors(T,cabinet);
const envelopes=homeShadowSweptBounds(T),poses=[];
const corner=new T.Vector3(),matrix=new T.Matrix4(),instance=new T.Matrix4();
function collect(group){
 const result=[];group.updateWorldMatrix(true,true);
 group.traverse(o=>{
  if(!o.isMesh)return;o.geometry.computeBoundingBox();const b=o.geometry.boundingBox;
  const add=m=>{for(const x of[b.min.x,b.max.x])for(const y of[b.min.y,b.max.y])for(const z of[b.min.z,b.max.z])result.push(new T.Vector3(x,y,z).applyMatrix4(m));};
  if(o.isInstancedMesh){for(let i=0;i<o.count;i++){o.getMatrixAt(i,instance);matrix.multiplyMatrices(o.matrixWorld,instance);add(matrix);}}else add(o.matrixWorld);
 });return result;
}
for(let step=0;step<=40;step++){
 const amount=step/40;
 front.rotation.y=-Math.PI*.48*amount;bath.position.z=BATHROOM_ACCESS.closed+(BATHROOM_ACCESS.open-BATHROOM_ACCESS.closed)*amount;
 balcony.leaf.position.x=-2.2+1.1*amount;foreground.gate.rotation.y=-Math.PI*.53*amount;
 for(const p of curtains){p.setOpen(true);p.update(.04);}
 for(const d of cabinetDoors.doors)d.leaf.rotation.y=CABINET_DOOR_POLICY.openAngle*amount;
 const points=[...collect(front),...collect(bath),...collect(balcony.leaf),...collect(foreground.group),...collect(cabinet),...curtains.flatMap(p=>collect(p.group))];
 for(const point of points)assert.ok(envelopes.some(b=>b.containsPoint(point)),`Dynamic corner outside source envelope: ${point.toArray()}`);
 poses.push(points);
}
for(const p of curtains){p.setOpen(true,{immediate:true});poses.push(collect(p.group));p.setOpen(false,{immediate:true});poses.push(collect(p.group));}
const fit=createShadowFit(T);fit.capture(new T.Scene(),envelopes);
const light=new T.DirectionalLight();light.target.position.set(0,1,0);light.shadow.mapSize.set(2048,2048);
const projection=new T.Matrix4();let tested=0;
for(let hour=6;hour<=18;hour+=.25){
 light.position.fromArray(homeLighting((hour-9)*3600).sunPosition);fit.fit(light);assert.equal(fit.coverage(light).outside,0);
 projection.multiplyMatrices(light.shadow.camera.projectionMatrix,light.shadow.camera.matrixWorldInverse);
 for(const points of poses)for(const point of points){corner.copy(point).applyMatrix4(projection);assert.ok(Math.max(Math.abs(corner.x),Math.abs(corner.y),Math.abs(corner.z))<=1+1e-6);tested++;}
}
assert.throws(()=>fit.capture(scene,[new T.Box3()]),/Finite/);
console.log(`PASS: actual-source front/bath dimensions; actual balcony/gate/cloth constructors+actual cabinet GLB hinges;41 swept door poses+cloth endpoints;49 daylight orientations; ${tested} projected dynamic corners covered; no city-sized envelope`);
