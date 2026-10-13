import {cleanKitchenBoxUv} from './clean_oak_material.mjs';
export const LOWER_CABINET = Object.freeze({
  centers:Object.freeze([-3.3,-2.6,-1.9,-1.2]),width:.65,halfHeight:.38,
  hingeY:.44,hingeZ:-3.192,minimumZ:-.0405,maximumZ:.022,
  angle:-Math.PI*.49,radius:.16,headAboveEye:.17,safety:.015,
});
export function lowerDoorBlocks(hinge,angle,position,feet=position[1]-1.65,height=1.82) {
  const p=LOWER_CABINET;
  if(feet+height<=hinge[1]-p.halfHeight||feet>=hinge[1]+p.halfHeight)return false;
  const dx=position[0]-hinge[0],dz=position[2]-hinge[2],c=Math.cos(angle),s=Math.sin(angle);
  const x=c*dx-s*dz,z=s*dx+c*dz;
  return Math.hypot(x-Math.max(0,Math.min(p.width,x)),z-Math.max(p.minimumZ,Math.min(p.maximumZ,z)))<=p.radius+p.safety;
}
export function lowerDoorSweepClear(hinge,from,to,positions) {
  const steps=Math.max(1,Math.ceil(Math.abs(to-from)/(Math.PI/180)));
  for(let i=0;i<=steps;i++)for(const position of positions)
    if(position&&lowerDoorBlocks(hinge,from+(to-from)*i/steps,position))return false;
  return true;
}

// Modules receive existing constructors/materials. No additional maps or loader.
export function createLowerKitchenCabinet(T,{RoundedBoxGeometry,mergeGeometries,oak,brass,
  interactions=[],getPositions=()=>[],onToggle=null,onBlocked=()=>{}}) {
  const root=new T.Group();root.name='Lower_kitchen_cabinet';
  const staticParts=[];
  const rounded=(w,h,d,r)=>new RoundedBoxGeometry(w,h,d,2,Math.min(r,w/3,h/3,d/3));
  function panel(name,w,h,d,x,y,z,r=.002) {
    const geometry=rounded(w,h,d,r);cleanKitchenBoxUv(geometry,[x,y,z]);geometry.translate(x,y,z);
    staticParts.push(geometry);return name;
  }
  // X/Z footprint retained; thin supports reach the unchanged slab underside at .8675m.
  panel('left side',.018,.8675,.62,-3.716,.43375,-3.55);
  panel('right side',.018,.8675,.62,-.684,.43375,-3.55);
  panel('back',3.014,.8315,.018,-2.2,.43375,-3.851);
  panel('base',3.014,.018,.584,-2.2,.089,-3.55);
  panel('recessed toe kick',3.014,.080,.018,-2.2,.04,-3.32);
  for(const x of [-2.95,-2.25,-1.55]) {
    panel('partition',.018,.7695,.578,x,.48275,-3.548);
    panel('original visible reveal',.05,.8675,.026,x,.43375,-3.253);
  }
  panel('left front filler',.10,.8675,.026,-3.675,.43375,-3.253);
  panel('right front filler',.20,.8675,.026,-.775,.43375,-3.253);
  panel('fixed upper reveal',3.014,.0475,.026,-2.2,.84375,-3.253);
  // Support rails leave the current stone slab/sink opening entirely untouched.
  panel('front support rail',3.014,.018,.045,-2.2,.8585,-3.273);
  panel('rear support rail',3.014,.018,.045,-2.2,.8585,-3.828);
  for(const [left,right,y] of [[-3.707,-2.959,.385],[-2.941,-2.259,.245],[-2.241,-1.559,.385],[-1.541,-.693,.385]])
    panel('shelf',right-left,.018,.51,(left+right)/2,y,-3.555);
  const carcass=new T.Mesh(mergeGeometries(staticParts,false),oak);carcass.name='Lower_cabinet_carcass';
  staticParts.forEach(g=>g.dispose());carcass.castShadow=carcass.receiveShadow=true;
  carcass.userData.bakeId='house-lower-cabinet-carcass';root.add(carcass);
  const doors=[];
  LOWER_CABINET.centers.forEach((x,i)=>{
    const pivot=new T.Group();pivot.name='Lower_cabinet_hinge_'+(i+1);
    pivot.position.set(x-.325,.44,LOWER_CABINET.hingeZ);pivot.userData.excludeStaticBake=true;
    const leafGeometry=rounded(.65,.76,.035,.006);cleanKitchenBoxUv(leafGeometry,[x,.44,-3.215]);
    const leaf=new T.Mesh(leafGeometry,oak);leaf.name='Lower_cabinet_door_'+(i+1);
    leaf.position.set(.325,0,-.023);leaf.castShadow=leaf.receiveShadow=true;
    leaf.userData.excludeStaticBake=true;leaf.userData.dynamicCabinetDoor=true;pivot.add(leaf);
    const pull=new T.Mesh(new T.CylinderGeometry(.01,.01,.30,10),brass);pull.name='Lower_cabinet_pull_'+(i+1);
    pull.position.set(.325,.31,.012);pull.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),new T.Vector3(1,0,0));
    pull.castShadow=true;pull.userData.excludeStaticBake=true;pull.userData.dynamicCabinetDoor=true;pivot.add(pull);root.add(pivot);
    const state={pivot,leaf,pull,hinge:pivot.position.toArray(),angle:0,target:0,velocity:0};
    state.interaction={object:pivot,reach:2,label:'E · Open lower cabinet '+(i+1),fn:()=>{
      const open=state.target===0,target=open?LOWER_CABINET.angle:0;
      if(!lowerDoorSweepClear(state.hinge,state.angle,target,getPositions())) {onBlocked('Step back to move the cabinet door.');return false;}
      return onToggle?onToggle(i,open):false;
    }};
    interactions.push(state.interaction);doors.push(state);
  });
  return {
    root,carcass,doors,
    setTargets(values) {
      if(!Array.isArray(values)||values.length!==4||values.some(v=>typeof v!=='boolean'))throw new TypeError('Four shared lower-cabinet booleans required');
      doors.forEach((d,i)=>{d.target=values[i]?LOWER_CABINET.angle:0;d.interaction.label='E · '+(values[i]?'Close':'Open')+' lower cabinet '+(i+1);});
    },
    update(dt) {
      let moving=false;const elapsed=Math.min(.05,Math.max(0,dt));
      for(const d of doors) {
        const distance=d.target-d.angle;
        if(Math.abs(distance)<.0001){d.angle=d.target;d.velocity=0;d.pivot.rotation.y=d.angle;continue;}
        const desired=Math.sign(distance)*Math.min(1.25,Math.sqrt(6*Math.abs(distance))),delta=desired-d.velocity;
        const velocity=d.velocity+Math.sign(delta)*Math.min(Math.abs(delta),3*elapsed),step=velocity*elapsed;
        const next=Math.sign(step)===Math.sign(distance)&&Math.abs(step)>=Math.abs(distance)?d.target:Math.max(LOWER_CABINET.angle,Math.min(0,d.angle+step));
        if(!lowerDoorSweepClear(d.hinge,d.angle,next,getPositions())){d.velocity=0;continue;}
        d.angle=next;d.velocity=next===d.target?0:velocity;d.pivot.rotation.y=next;moving=true;
      }
      return moving;
    },
    allowsPosition(x,z,feet=0,height=1.82){return doors.every(d=>!lowerDoorBlocks(d.hinge,d.angle,[x,feet+1.65,z],feet,height));},
  };
}
