import {createResidentialForeground} from './residential_foreground.mjs';
import {createStreetMaterials,streetMetricUv} from './street_materials.mjs';
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
  const {pavement,asphalt}=createStreetMaterials(T,{lite,manager});
  function slab(w,h,d,x,y,z,mat){
    const geometry=new T.BoxGeometry(w,h,d);
    streetMetricUv(geometry,[x,y,z],mat.userData.tileMetres||1.8);
    const m=new T.Mesh(geometry,mat);m.position.set(x,y,z);m.receiveShadow=true;foreground.add(m);return m;
  }
  slab(60,.08,60,0,-.2,0,pavement);
  slab(60,.16,3.1,0,-.08,7.25,pavement);
  slab(60,.16,3.1,0,-.08,15.75,pavement);
  slab(60,.04,5.2,0,-.135,11.5,asphalt);
  const curb=pavement.clone();curb.onBeforeCompile=pavement.onBeforeCompile;curb.customProgramCacheKey=pavement.customProgramCacheKey;
  curb.color.set('#ddd9ce');
  slab(60,.13,.18,0,-.075,8.8,curb);slab(60,.13,.18,0,-.075,14.2,curb);
  // Recessed narrow curb joints at one-metre spacing, in one instanced draw.
  const joints=new T.InstancedMesh(new T.BoxGeometry(.012,.12,.184),new T.MeshStandardMaterial({color:'#5c5b56',roughness:1}),120);
  const jointMatrix=new T.Matrix4();let joint=0;
  for(const z of [8.8,14.2])for(let x=-29.5;x<30;x+=1){jointMatrix.makeTranslation(x,-.079,z);joints.setMatrixAt(joint++,jointMatrix);}
  foreground.add(joints);
  const paint=new T.MeshStandardMaterial({color:'#d2cdb7',roughness:1});
  for(const z of [9.05,13.95])slab(60,.005,.06,0,-.107,z,paint);
  const frontage=createResidentialForeground(T,foreground,{gateOpen:true});
  let ready=false;
  return {
    texture,group,sphere,get ready(){return ready;},
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
