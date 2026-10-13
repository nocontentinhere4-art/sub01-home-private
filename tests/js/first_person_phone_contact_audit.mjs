import * as T from '../../web/house/vendor/three.module.js';
import { productionGlb } from './first_person_asset_fixture.mjs';
const root='out/first-person-assets/ReferenceT/';
const owner=await productionGlb(root+'owner.glb');
const capture=await productionGlb(root+'texting.glb');
const clip=capture.animations[0],mixer=new T.AnimationMixer(owner.scene);
mixer.clipAction(clip).play();
const get=n=>owner.scene.getObjectByName('mixamorig'+n).getWorldPosition(new T.Vector3());
const projections=[],samples=[];
for(let f=0;f<clip.duration*30;f++){
 mixer.setTime(f/30);owner.scene.updateMatrixWorld(true);
 const wrist=get('RightHand'), index=get('RightHandIndex1'),pinky=get('RightHandPinky1'),middle=get('RightHandMiddle1'),thumb=get('RightHandThumb4');
 const across=index.clone().sub(pinky).normalize();
 const forward=middle.clone().sub(wrist);forward.addScaledVector(across,-forward.dot(across)).normalize();
 const normal=across.clone().cross(forward).normalize();
 if(normal.dot(get('Head').sub(wrist))<0)normal.negate();
 // Diagnostic candidate only: a 75 × 150 × 8mm device resting along the
 // recorded right palm, screen toward head. No pose/track modifications.
 const center=wrist.clone().addScaledVector(forward,.055).addScaledVector(normal,.01);
 const delta=thumb.clone().sub(center);const x=delta.dot(across),y=delta.dot(forward),z=delta.dot(normal);
 projections.push([x,y,z]);
 if(f%60===0)samples.push({time:f/30,wrist:wrist.toArray(),phoneCenter:center.toArray(),across:across.toArray(),forward:forward.toArray(),screenNormal:normal.toArray(),thumbScreenCoordinates:[x,y,z]});
}
const contact=projections.filter(([x,y,z])=>Math.abs(x)<=.0375&&Math.abs(y)<=.075&&Math.abs(z)<=.025).length;
console.log(JSON.stringify({reference:'Original owner T-reference with unchanged inverse bind matrices',capture:'Actual downloaded Texting, retargeted; one-handed action is permitted',visualAccepted:false,attachedInRuntime:false,deviceDimensionsMeters:[.075,.15,.008],candidateOrigin:'right wrist + palm-forward 0.055m + screen normal 0.010m',thumbContactFraction:contact/projections.length,thumbRanges:['across','forward','normal'].map((axis,k)=>({axis,min:Math.min(...projections.map(v=>v[k])),max:Math.max(...projections.map(v=>v[k]))})),requiredReview:'Inspect the actual rendered palm and thumb skin against phone before accepting this candidate attachment',samples},null,2));
