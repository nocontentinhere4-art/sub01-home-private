export const BALCONY_ACCESS = Object.freeze({
  centre: -2.2, width: 1.05, plane: 3.85, slide: 1.1,
  radius: .16, approach: 1.7, floor: 3,
});

export function balconyApproach(position) {
  return !!position && position[1] > 3 &&
    Math.hypot(position[0] - BALCONY_ACCESS.centre, position[2] - BALCONY_ACCESS.plane) < BALCONY_ACCESS.approach;
}

export function balconyAllows(x, z, feet, openness) {
  const a = BALCONY_ACCESS;
  if (feet < 2.5 || z < a.plane - a.radius - .105 || z > a.plane + a.radius + .035) return true;
  const left = a.centre - a.width / 2, right = a.centre + a.width / 2;
  if (x < left + a.radius + .025 || x > right - a.radius - .025) return false;
  // Check the actual moving leaf edge, not the open/close intention. Closing
  // glass and fixed sidelight frames cannot be crossed while it is still shut.
  const amount = Number.isFinite(openness) ? Math.max(0, Math.min(1, openness)) : 0;
  return x + a.radius + .025 <= left + a.slide * amount;
}

export function createBalconyDoor(T, scene, wood) {
  const a = BALCONY_ACCESS;
  const left = a.centre - a.width / 2, right = a.centre + a.width / 2;
  const staticParts = [
    [3.6,.055,.06,-2,5.7,a.plane],
    [.045,2.5,.06,-3.8,4.45,a.plane], [.045,2.5,.06,-.2,4.45,a.plane],
    [left+3.8,.055,.06,(-3.8+left)/2,3.2,a.plane],
    [-.2-right,.055,.06,(right-.2)/2,3.2,a.plane],
    [.045,2.7,.06,left,4.35,a.plane], [.045,2.7,.06,right,4.35,a.plane],
    [3.6,.012,.09,-2,3.012,a.plane],
  ];
  function frames(parts) {
    const mesh = new T.InstancedMesh(new T.BoxGeometry(1,1,1), wood, parts.length);
    parts.forEach(([w,h,d,x,y,z], i) => mesh.setMatrixAt(i,
      new T.Matrix4().compose(new T.Vector3(x,y,z),new T.Quaternion(),new T.Vector3(w,h,d))));
    mesh.castShadow = mesh.receiveShadow = true;
    return mesh;
  }
  const fixed = frames(staticParts);
  fixed.name = 'balcony_fixed_sidelight_frames';
  scene.add(fixed);
  const leaf = new T.Group();
  leaf.name = 'balcony_sliding_leaf';
  leaf.userData.excludeStaticBake = true;
  leaf.position.set(a.centre,a.floor,a.plane-.045);
  leaf.add(frames([
    [a.width,.055,.06,0,.028,0], [a.width,.055,.06,0,2.672,0],
    [.045,2.7,.06,-a.width/2,1.35,0], [.045,2.7,.06,a.width/2,1.35,0],
  ]));
  const glass = new T.Mesh(new T.PlaneGeometry(a.width-.07,2.62),new T.MeshStandardMaterial({
    color:'#d7e2df',roughness:.13,metalness:.12,transparent:true,opacity:.055,
    side:T.DoubleSide,depthWrite:false,
  }));
  glass.position.y=1.35;
  leaf.add(glass);
  const handle = new T.Mesh(new T.CylinderGeometry(.012,.012,.22,8),new T.MeshStandardMaterial({
    color:'#a1a4a2',metalness:.8,roughness:.3,
  }));
  handle.position.set(-a.width/2+.07,1.1,-.06);
  handle.castShadow=true;leaf.add(handle);
  scene.add(leaf);
  let velocity=0;
  return {
    leaf,
    get openness(){return (leaf.position.x-a.centre)/a.slide;},
    update(dt, open){
      const target=a.centre+(open?a.slide:0);
      const elapsed=Math.min(.1,Math.max(0,dt)), distance=target-leaf.position.x;
      const desired=Math.sign(distance)*Math.min(.85,Math.sqrt(2*1.8*Math.abs(distance)));
      velocity+=Math.max(-1.8*elapsed,Math.min(1.8*elapsed,desired-velocity));
      const step=velocity*elapsed;
      if(Math.sign(step)===Math.sign(distance) && Math.abs(step)>=Math.abs(distance)) {
        leaf.position.x=target;velocity=0;
      } else {
        const next=leaf.position.x+step;
        leaf.position.x=Math.max(a.centre,Math.min(a.centre+a.slide,next));
        if(next!==leaf.position.x) velocity=0;
      }
      return Math.abs(leaf.position.x-target)>.001 || Math.abs(velocity)>.001;
    },
  };
}

export function staticBakeScene(scene) {
  const copy=scene.clone(true), excluded=[];
  // glTF stores a light's local -Z axis, not Three's independent target.
  // Repair only the export clone, including lights under transformed parents.
  const originals=[], clones=[];
  scene.traverse(object=>originals.push(object));
  copy.traverse(object=>clones.push(object));
  scene.updateMatrixWorld(true);
  copy.updateMatrixWorld(true);
  originals.forEach((original,index)=>{
    if (!(original.isDirectionalLight || original.isSpotLight)) return;
    const light=clones[index];
    const targetWorld=original.target.getWorldPosition(original.position.clone());
    const targetLocal=targetWorld.clone();
    if (light.parent) targetLocal.applyMatrix4(light.parent.matrixWorld.clone().invert());
    if (!light.matrixAutoUpdate) light.matrix.decompose(light.position,light.quaternion,light.scale);
    const direction=targetLocal.clone().sub(light.position).normalize();
    const up=light.up.clone().normalize();
    if (Math.abs(direction.dot(up))>.999) {
      up.set(1,0,0);
      if (Math.abs(direction.dot(up))>.999) up.set(0,0,1);
    }
    light.quaternion.setFromRotationMatrix(light.matrix.clone().lookAt(light.position,targetLocal,up));
    light.matrixAutoUpdate=true;
    const target=original.target.clone(false);
    target.position.set(0,0,-1);
    target.quaternion.identity();
    target.scale.set(1,1,1);
    target.matrixAutoUpdate=true;
    light.add(target);
    light.target=target;
    light.updateMatrix();
  });
  copy.traverse(object=>{if(object.userData.excludeStaticBake) excluded.push(object);});
  for(const object of excluded) object.removeFromParent();
  return copy;
}
