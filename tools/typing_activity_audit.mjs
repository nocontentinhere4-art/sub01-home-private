import * as T from '../web/house/vendor/three.module.js';
import { productionGlb } from '../tests/js/first_person_asset_fixture.mjs';
const results={};
for(const [label,url]of Object.entries({original:'/room/mh_mx/room_mx_typing.glb',referenceT:'out/first-person-assets/ReferenceT/typing.glb'})){
 const owner=await productionGlb('/room/char_mixamo.glb'),capture=await productionGlb(url),clip=capture.animations[0];
 const mixer=new T.AnimationMixer(owner.scene);mixer.clipAction(clip).play();
 const bones=[];owner.scene.traverse(b=>{if(b.isBone&&/(Left|Right)Hand/.test(b.name))bones.push(b)});
 const samples=new Map(bones.map(b=>[b.name,[]]));
 for(let f=0;f<clip.duration*30;f++){
  mixer.setTime(f/30);owner.scene.updateMatrixWorld(true);
  for(const b of bones)samples.get(b.name).push({p:b.getWorldPosition(new T.Vector3()),q:b.quaternion.clone()});
 }
 const sides={};
 for(const side of ['Left','Right']){
  const movement={};
  for(const b of bones.filter(b=>b.name.includes(side))){
   const values=samples.get(b.name),bounds=new T.Box3(),mean=new T.Vector3();let path=0,angularPath=0,maxRestDelta=0;
   values.forEach((v,i)=>{bounds.expandByPoint(v.p);mean.add(v.p);maxRestDelta=Math.max(maxRestDelta,values[0].q.angleTo(v.q));if(i){path+=v.p.distanceTo(values[i-1].p);angularPath+=values[i-1].q.angleTo(v.q);}});
   movement[b.name]={worldSpanMeters:bounds.getSize(new T.Vector3()).toArray(),worldMeanMeters:mean.divideScalar(values.length).toArray(),worldPathMeters:path,maxLocalAngleFromFirstDegrees:maxRestDelta*180/Math.PI,localAngularPathDegrees:angularPath*180/Math.PI};
  }
  const finger=Object.entries(movement).filter(([n])=>/Hand(Thumb|Index|Middle|Ring|Pinky)[1-3]$/.test(n));
  sides[side]={fingerChannels: finger.length,movingFingerChannels: finger.filter(([,m])=>m.maxLocalAngleFromFirstDegrees>1).length,totalFingerAngularPathDegrees:finger.reduce((sum,[,m])=>sum+m.localAngularPathDegrees,0),meanMaxFingerAngleDegrees:finger.reduce((sum,[,m])=>sum+m.maxLocalAngleFromFirstDegrees,0)/finger.length,movement};
 }
 const contact = {};
 for(const side of ['Left','Right']){
  const vals=samples.get('mixamorig'+side+'HandIndex4');
  contact[side]={};
  for(let t=0;t<clip.duration;t+=1){
   const subset=vals.slice(Math.floor(t*30),Math.min(vals.length,Math.floor((t+1)*30)));
   const inside=subset.filter(v=>{const x=2.039-v.p.x,z=-2.323-v.p.z;return Math.abs(x-2)<=.1855&&Math.abs(z+2.94)<=.1;});
   const joints = bones.filter(b=>b.name.includes(side)&&/Hand(Thumb|Index|Middle|Ring|Pinky)[1-3]$/.test(b.name));
   let angularPath=0,activeJoints=0;
   for(const bone of joints){
    const poses=samples.get(bone.name).slice(Math.floor(t*30),Math.min(vals.length,Math.floor((t+1)*30)));
    let travel=0;for(let k=1;k<poses.length;k++)travel+=poses[k-1].q.angleTo(poses[k].q)*180/Math.PI;
    angularPath+=travel;if(travel>2)activeJoints++;
   }
   contact[side][t]={fingerAngularPathDegrees:angularPath,activeFingerJointsAbove2Degrees:activeJoints,keyboardHorizontalFootprintFraction:inside.length/subset.length,tipHeightRangeMeters:[Math.min(...subset.map(v=>v.p.y-.006)),Math.max(...subset.map(v=>v.p.y-.006))]};
  }
 }
 results[label]={keyboardIndexEndpointContactBins:contact,duration:clip.duration,sides,rawReferencePreserved:label==='original'};
}
console.log(JSON.stringify(results,null,2));
