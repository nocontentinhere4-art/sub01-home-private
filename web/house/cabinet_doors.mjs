// Existing original upper cabinet: four actual edge-pivot fronts and parented pulls.
// Integration requires a fresh static bake that excludes these moving leaves.
export const CABINET_DOOR_POLICY = Object.freeze({
  width:.771, thickness:.044, hingeOffset:.014, halfHeight:.33, openAngle:-Math.PI * .49,
  reach:2, capsuleRadius:.16, bodyHeight:1.82, sweepPadding:.015,
  speed:1.25, acceleration:3, sweepStep:Math.PI / 180,
});

// Point/capsule to actual hinged rectangle, with Y overlap for standing/seated bodies.
export function cabinetDoorBlocksCapsule(hinge, angle, position, feet = position[1] - 1.65,
                                        radius = CABINET_DOOR_POLICY.capsuleRadius,
                                        height = CABINET_DOOR_POLICY.bodyHeight) {
  const p=CABINET_DOOR_POLICY;
  if (feet+height<=hinge[1]-p.halfHeight || feet>=hinge[1]+p.halfHeight) return false;
  const dx=position[0]-hinge[0],dz=position[2]-hinge[2],c=Math.cos(angle),s=Math.sin(angle);
  // Three.js Y rotation: worldX=c*localX+s*localZ, worldZ=-s*localX+c*localZ.
  const x=c*dx-s*dz,z=s*dx+c*dz;
  const nx=Math.max(0,Math.min(p.width,x));
  const nz=Math.max(-p.hingeOffset-p.thickness/2,Math.min(-p.hingeOffset+p.thickness/2,z));
  return Math.hypot(x-nx,z-nz)<=radius+p.sweepPadding;
}
export function cabinetSweepIsClear(hinge, from, to, positions) {
  const steps=Math.max(1,Math.ceil(Math.abs(to-from)/CABINET_DOOR_POLICY.sweepStep));
  for(let i=0;i<=steps;i++) {
    const angle=from+(to-from)*i/steps;
    for(const position of positions) if(position && cabinetDoorBlocksCapsule(hinge,angle,position)) return false;
  }
  return true;
}

export function attachUpperCabinetDoors(T, root, {interactions=[], getPositions=()=>[], onBlocked=()=>{}, onToggle=null}={}) {
  const doors=[];
  root.updateMatrixWorld(true);
  for(let i=1;i<=4;i++) {
    const panel=root.getObjectByName('Cabinet_door_'+i) || root.getObjectByName('Cabinet door '+i);
    if(!panel) throw new Error('Original cabinet is missing independent door '+i);
    const leaf=new T.Group();leaf.name='Cabinet hinge '+i;
    leaf.position.copy(panel.position);leaf.position.z+=CABINET_DOOR_POLICY.hingeOffset;
    panel.parent.add(leaf);root.updateMatrixWorld(true);
    // Reparent while preserving every closed mesh/handle world vertex exactly.
    leaf.attach(panel);root.updateMatrixWorld(true);
    const pivot=new T.Vector3();leaf.getWorldPosition(pivot);
    const hinge=pivot.toArray();
    leaf.traverse(object=>{
      object.userData.excludeStaticBake=true;
      object.userData.dynamicCabinetDoor=true;
      if(!object.isMesh)return;
      // Static day/night GI/closed AO cannot move with the panel.
      object.material=object.material.clone();
      object.material.lightMap=null;object.material.aoMap=null;
      object.material.onBeforeCompile=()=>{};
      object.material.customProgramCacheKey=()=> 'private-dynamic-cabinet-source-v1';
      object.material.needsUpdate=true;
      object.castShadow=object.receiveShadow=true;
    });
    const state={leaf,panel,hinge,angle:0,target:0,velocity:0};
    const interaction={object:leaf,reach:CABINET_DOOR_POLICY.reach,label:'E · Open cabinet '+i,fn:()=>{
      const target=state.target===0?CABINET_DOOR_POLICY.openAngle:0;
      if(!cabinetSweepIsClear(hinge,state.angle,target,getPositions())) {
        onBlocked('Step back to open or close the cabinet.');return false;
      }
      // Root persists the requested target; only setTargets applies shared state.
      return onToggle ? onToggle(i-1,target!==0) : false;
    }};
    state.interaction=interaction;interactions.push(interaction);doors.push(state);
  }
  return {
    doors,
    setTargets(open) {
      if(!Array.isArray(open)||open.length!==4||open.some(v=>v!==true&&v!==false))
        throw new TypeError('Shared cabinet state must contain exactly four booleans');
      doors.forEach((d,i)=>{
        d.target=open[i]?CABINET_DOOR_POLICY.openAngle:0;
        d.interaction.label='E · '+(open[i]?'Close':'Open')+' cabinet '+(i+1);
      });
    },
    update(dt) {
      const elapsed=Math.min(.05,Math.max(0,dt));let moving=false;
      for(const d of doors) {
        const distance=d.target-d.angle;
        if(Math.abs(distance)<.0001) {d.angle=d.target;d.velocity=0;d.leaf.rotation.y=d.angle;continue;}
        const desired=Math.sign(distance)*Math.min(CABINET_DOOR_POLICY.speed,Math.sqrt(2*CABINET_DOOR_POLICY.acceleration*Math.abs(distance)));
        const dv=desired-d.velocity;
        const velocity=d.velocity+Math.sign(dv)*Math.min(Math.abs(dv),CABINET_DOOR_POLICY.acceleration*elapsed);
        const step=velocity*elapsed;
        const next=Math.sign(step)===Math.sign(distance)&&Math.abs(step)>=Math.abs(distance)?d.target:
                   Math.max(CABINET_DOOR_POLICY.openAngle,Math.min(0,d.angle+step));
        if(!cabinetSweepIsClear(d.hinge,d.angle,next,getPositions())) {d.velocity=0;continue;}
        d.angle=next;d.velocity=next===d.target?0:velocity;d.leaf.rotation.y=next;moving=true;
      }
      return moving;
    },
    allowsPosition(x,z,feet=0,height=CABINET_DOOR_POLICY.bodyHeight) {
      return doors.every(d=>!cabinetDoorBlocksCapsule(d.hinge,d.angle,[x,feet+1.65,z],feet,
                                                     CABINET_DOOR_POLICY.capsuleRadius,height));
    },
    snapshot(){return doors.map(d=>({name:d.panel.name,angle:d.angle,target:d.target}));},
  };
}
