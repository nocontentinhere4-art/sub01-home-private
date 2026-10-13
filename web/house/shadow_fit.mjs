// Fit one existing directional shadow target to real, visible caster geometry.
// Capture after model readiness; fit only when the sun/light state changes.
// No render, camera movement, light/bias/map-size change or new GPU resources.
// Source-coordinate envelopes: 8m house walls/6.15m roof, then the low entrance
// terrace/front-door/gate sweep. They exclude the 110m photographed sphere and
// the 18m street receivers, which cannot cast shadows. Separate low entrance
// bounds avoid pretending the loft roof extends all the way to the street.
export function homeShadowSweptBounds(T) {
  return [
    new T.Box3(new T.Vector3(-4.12,-.15,-4.12),new T.Vector3(4.12,6.25,4.15)),
    new T.Box3(new T.Vector3(-4.12,-.15,3.75),new T.Vector3(4.12,2.3,7.5)),
  ];
}

export function createShadowFit(T,{padding=.28}={}) {
  const points=[];
  const corner=new T.Vector3(),instance=new T.Matrix4(),world=new T.Matrix4();
  const projected=new T.Vector3();
  let casters=0;
  const append=(box,matrix)=>{
    for(const x of[box.min.x,box.max.x])for(const y of[box.min.y,box.max.y])for(const z of[box.min.z,box.max.z])
      points.push(new T.Vector3(x,y,z).applyMatrix4(matrix));
  };
  return {
    capture(scene,extraBounds=[]){
      points.length=0;casters=0;scene.updateMatrixWorld(true);
      scene.traverseVisible(object=>{
        if(!object.isMesh||!object.castShadow)return;
        const geometry=object.geometry;
        if(!geometry.boundingBox)geometry.computeBoundingBox();
        if(!geometry.boundingBox||geometry.boundingBox.isEmpty())return;
        if(object.isInstancedMesh){
          for(let i=0;i<object.count;i++){
            object.getMatrixAt(i,instance);world.multiplyMatrices(object.matrixWorld,instance);
            append(geometry.boundingBox,world);casters++;
          }
        }else{append(geometry.boundingBox,object.matrixWorld);casters++;}
      });
      // Conservative dynamic envelopes remain stable for future door/sliding
      // cabinet/cloth poses without recomputing every mesh every animation frame.
      for(const bounds of extraBounds){
        if(!bounds?.isBox3||bounds.isEmpty()||![...bounds.min.toArray(),...bounds.max.toArray()].every(Number.isFinite))
          throw new TypeError('Finite nonempty Box3 envelope required');
        append(bounds,new T.Matrix4());
      }
      return{casters,cornerCount:points.length};
    },
    fit(light){
      if(!points.length)return null;
      if(!light.isDirectionalLight)throw new TypeError('Directional light required');
      light.updateWorldMatrix(true,false);light.target.updateWorldMatrix(true,false);
      light.shadow.updateMatrices(light);
      const camera=light.shadow.camera;
      let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity,near=Infinity,far=-Infinity;
      for(const point of points){
        projected.copy(point).applyMatrix4(camera.matrixWorldInverse);
        minX=Math.min(minX,projected.x);maxX=Math.max(maxX,projected.x);
        minY=Math.min(minY,projected.y);maxY=Math.max(maxY,projected.y);
        near=Math.min(near,-projected.z);far=Math.max(far,-projected.z);
      }
      let halfX=(maxX-minX)*.5+padding,halfY=(maxY-minY)*.5+padding;
      // One extra texel leaves conservative coverage after nearest-center snap.
      const stepX=2*halfX/light.shadow.mapSize.x,stepY=2*halfY/light.shadow.mapSize.y;
      const centerX=Math.round((minX+maxX)*.5/stepX)*stepX;
      const centerY=Math.round((minY+maxY)*.5/stepY)*stepY;
      halfX+=stepX;halfY+=stepY;
      camera.left=centerX-halfX;camera.right=centerX+halfX;
      camera.bottom=centerY-halfY;camera.top=centerY+halfY;
      camera.near=Math.max(.1,near-padding);camera.far=Math.max(camera.near+.5,far+padding);
      camera.updateProjectionMatrix();light.shadow.updateMatrices(light);
      return{casters,cornerCount:points.length,width:2*halfX,height:2*halfY,
        texelMetresX:2*halfX/light.shadow.mapSize.x,texelMetresY:2*halfY/light.shadow.mapSize.y,
        near:camera.near,far:camera.far,normalBias:light.shadow.normalBias};
    },
    // QA coverage is a read-only projection of the captured, real corners.
    coverage(light){
      const camera=light.shadow.camera;let outside=0;
      const projection=new T.Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);
      for(const point of points){corner.copy(point).applyMatrix4(projection);if(Math.max(Math.abs(corner.x),Math.abs(corner.y),Math.abs(corner.z))>1+1e-6)outside++;}
      return{outside,cornerCount:points.length};
    },
  };
}
