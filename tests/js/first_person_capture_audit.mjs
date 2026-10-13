import * as T from '../../web/house/vendor/three.module.js';
import { productionGlb } from './first_person_asset_fixture.mjs';
const root=process.argv[2] || 'out/first-person-assets/ReferenceT/';
const output={};
for(const mode of ['typing','walking','texting']){
 const owner=await productionGlb(root+'owner.glb');
 const capture=await productionGlb(root+mode+'.glb');
 const clip=capture.animations[0], mixer=new T.AnimationMixer(owner.scene);
 mixer.clipAction(clip).play();
 const hips=owner.scene.getObjectByName('mixamorigHips');
 const head=owner.scene.getObjectByName('mixamorigHead');
 const tips=['Left','Right'].map(s=>owner.scene.getObjectByName('mixamorig'+s+'HandIndex4'));
 const hands=['Left','Right'].map(s=>owner.scene.getObjectByName('mixamorig'+s+'Hand'));
 const bounds=new T.Box3();const mean=new T.Vector3();let samples=0;const tipMeans=tips.map(()=>new T.Vector3());const headMean=new T.Vector3();const palmDistances=[];
 const count=Math.ceil(clip.duration*30);
 for(let f=0;f<=count;f++){
  mixer.setTime(Math.min(clip.duration-.00001,f/30));owner.scene.updateMatrixWorld(true);
  const p=hips.getWorldPosition(new T.Vector3());bounds.expandByPoint(p);mean.add(p);samples++;
  headMean.add(head.getWorldPosition(new T.Vector3()));
  tips.forEach((t,i)=>tipMeans[i].add(t.getWorldPosition(new T.Vector3())));
  palmDistances.push(hands[0].getWorldPosition(new T.Vector3()).distanceTo(hands[1].getWorldPosition(new T.Vector3())));
 }
 output[mode]={duration:clip.duration,hipsWorldMin:bounds.min.toArray(),hipsWorldMax:bounds.max.toArray(),hipsSpan:bounds.getSize(new T.Vector3()).toArray(),headMean:headMean.divideScalar(samples).toArray(),indexTipMeans:tipMeans.map(p=>p.divideScalar(samples).toArray()),wristSeparationRange:[Math.min(...palmDistances),Math.max(...palmDistances)],visualAccepted:false};
}
console.log(JSON.stringify(output,null,2));
