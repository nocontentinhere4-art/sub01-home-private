import {createResidentialForeground} from './residential_foreground.mjs';
import {createStreetMaterials,streetMetricUv} from './street_materials.mjs?v=2';
// A limited real foreground meets the historical capture, rather than paving
// an invented 60m square over its whole street. Values are world metres.
export const RESIDENTIAL_GROUND = Object.freeze({
  courtyardWidth:10,courtyardDepth:10.2,courtyardZ:.8,courtyardTop:-.02,
  streetWidth:18,streetFadeStart:7,streetHalfWidth:9,farFadeStart:14.7,farEdge:17.3,
});
export function foregroundFadeAt(x,z,{court=false}={}){
  const smooth=(a,b,v)=>{const t=Math.max(0,Math.min(1,(v-a)/(b-a)));return t*t*(3-2*t);};
  return court ? (1-smooth(4.65,5,Math.abs(x)))*(1-smooth(4.0,4.3,-z)) :
    (1-smooth(7,9,Math.abs(x)))*(1-smooth(14.7,17.3,z));
}
function transitionMaterial(source,{court=false}={}){
  const material=source.clone(),previous=source.onBeforeCompile;
  material.transparent=true;material.depthWrite=false;
  material.onBeforeCompile=(shader,renderer)=>{
    previous?.(shader,renderer);
    shader.vertexShader='varying vec3 vResidentialWorld;\n'+shader.vertexShader.replace('#include <project_vertex>',
      `#include <project_vertex>
       vec4 residentialWorld=vec4(transformed,1.);
       #ifdef USE_INSTANCING
         residentialWorld=instanceMatrix*residentialWorld;
       #endif
       vResidentialWorld=(modelMatrix*residentialWorld).xyz;`);
    shader.fragmentShader='varying vec3 vResidentialWorld;\n'+shader.fragmentShader.replace('#include <opaque_fragment>',
      (court ?
        'diffuseColor.a *= (1.-smoothstep(4.65,5.,abs(vResidentialWorld.x)))*(1.-smoothstep(4.,4.3,-vResidentialWorld.z));\n' :
        'diffuseColor.a *= (1.-smoothstep(7.,9.,abs(vResidentialWorld.x)))*(1.-smoothstep(14.7,17.3,vResidentialWorld.z));\n')+
      '#include <opaque_fragment>');
  };
  material.customProgramCacheKey=()=> (source.customProgramCacheKey?.()||'standard')+
    (court?'-residential-court-transition-v1':'-residential-street-transition-v1');
  return material;
}
// A single historical, attributed spherical capture is visible through every
// window and outside. No finite plates, portal copies, reflection scene or HDRI.
export function createExteriorBackdrops(T, scene, {lite=false, manager}={}, legacy) {
  const group=new T.Group(); group.name='residential_exterior';
  group.userData.excludeStaticBake=true; scene.add(group);
  const texture=new T.TextureLoader(manager).load(`/house/assets/tokyo-residential/residential-${lite?2048:4096}.webp`);
  texture.colorSpace=T.SRGBColorSpace; texture.wrapS=T.RepeatWrapping;
  const uniforms={tPanorama:{value:texture},uBrightness:{value:1},uTint:{value:new T.Color(1,1,1)}};
  const material=new T.ShaderMaterial({
    uniforms,side:T.BackSide,depthWrite:false,fog:false,toneMapped:true,
    vertexShader:`varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
    fragmentShader:`uniform sampler2D tPanorama;uniform float uBrightness;uniform vec3 uTint;varying vec2 vUv;
      void main(){gl_FragColor=vec4(texture2D(tPanorama,vUv).rgb*uTint*uBrightness,1.);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      }`,
  });
  const sphere=new T.Mesh(new T.SphereGeometry(110,48,24),material);
  sphere.name='tokyo_residential_spherical_capture'; sphere.position.y=1.65;
  sphere.renderOrder=-10; sphere.frustumCulled=false; sphere.visible=false;group.add(sphere);
  // Real nearby pavement gives translation parallax and hides the photographed
  // nadir. Distant buildings remain a static capture, not navigable geometry.
  const foreground=new T.Group();foreground.name='residential_pavement';foreground.visible=false;group.add(foreground);
  const sourceMaterials=createStreetMaterials(T,{lite,manager});
  const pavement=transitionMaterial(sourceMaterials.pavement),asphalt=transitionMaterial(sourceMaterials.asphalt);
  const courtyard=transitionMaterial(sourceMaterials.pavement,{court:true});
  function slab(w,h,d,x,y,z,mat){
    const geometry=new T.BoxGeometry(w,h,d);
    streetMetricUv(geometry,[x,y,z],mat.userData.tileMetres||1.8);
    const m=new T.Mesh(geometry,mat);m.position.set(x,y,z);m.receiveShadow=true;foreground.add(m);return m;
  }
  const court=slab(10,.08,10.2,0,-.06,.8,courtyard);court.name='bounded_ground_floor_courtyard';court.renderOrder=-5;
  const nearWalk=slab(18,.16,3.1,0,-.08,7.25,pavement);nearWalk.name='local_front_sidewalk';
  const farWalk=slab(18,.16,3.1,0,-.08,15.75,pavement);farWalk.name='local_far_sidewalk';
  const road=slab(18,.04,5.2,0,-.135,11.5,asphalt);road.name='local_residential_road';
  const curb=pavement.clone();curb.onBeforeCompile=pavement.onBeforeCompile;curb.customProgramCacheKey=pavement.customProgramCacheKey;
  curb.color.set('#ddd9ce');
  for(const z of [8.8,14.2]) slab(18,.13,.18,0,-.075,z,curb).renderOrder=2;
  // Recessed narrow curb joints at one-metre spacing, in one instanced draw.
  const jointMaterial=transitionMaterial(new T.MeshStandardMaterial({color:'#5c5b56',roughness:1}));
  const joints=new T.InstancedMesh(new T.BoxGeometry(.012,.12,.184),jointMaterial,36);
  const jointMatrix=new T.Matrix4();let joint=0;
  for(const z of [8.8,14.2])for(let x=-8.5;x<9;x+=1){jointMatrix.makeTranslation(x,-.079,z);joints.setMatrixAt(joint++,jointMatrix);}
  joints.renderOrder=3;foreground.add(joints);
  const paint=transitionMaterial(new T.MeshStandardMaterial({color:'#d2cdb7',roughness:1}));
  for(const z of [9.05,13.95])slab(18,.005,.06,0,-.107,z,paint).renderOrder=4;
  // A narrow side gravel bed and low curbing make the parcel read as a house
  // frontage. Neither rises into the windows or moves a walkable visitor surface.
  const gravel=new T.MeshStandardMaterial({color:'#66645a',roughness:1});
  slab(.40,.025,7.4,-4.72,-.016,-.05,gravel).name='side_gravel_bed';
  const boundary=new T.MeshStandardMaterial({color:'#aaa99b',roughness:.92});
  for(const x of [-4.95,-4.49]) slab(.04,.045,7.5,x,-.0025,-.05,boundary);
  for(const z of [-3.8,3.7]) slab(.50,.045,.04,-4.72,-.0025,z,boundary);
  const frontage=createResidentialForeground(T,foreground,{gateOpen:true});
  let ready=false;
  return {
    texture,group,sphere,get ready(){return ready;},
    get gateAngle(){return frontage.gate.rotation.y;},
    get draws(){let count=0;group.traverse(object=>{if(object.isMesh)count++;});return count;},
    activate(){
      if(ready)return true;
      const image=texture.image;
      if(!image||(image.naturalWidth??image.width)<=0||(image.naturalHeight??image.height)<=0)return false;
      ready=true;sphere.visible=true;foreground.visible=true;if(legacy)legacy.visible=false;return true;
    },
    update(dt,hour){
      frontage.update(dt);
      // Rendering of a 2009 daylight capture; not separate night photography.
      const sun=Math.max(0,Math.sin((hour-6)*Math.PI/12));
      uniforms.uBrightness.value=.08+.92*sun;
      uniforms.uTint.value.setRGB(.65+.35*sun,.73+.27*sun,1);
    },
    state(){return {capture:'2009-12-06 static residential Tokyo',panoramaTextures:1,probes:0,ready};},
  };
}
