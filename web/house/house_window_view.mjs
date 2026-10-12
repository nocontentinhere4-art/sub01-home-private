import { BALCONY_ACCESS } from './balcony_access.mjs';
import {weatherAt,tokyoDayKey} from '../room/window_view.js?v=home1';

// The legacy room used one window-centred diorama. This two-floor house needs
// one coordinate system per facade, shared by every pane on that facade.
export const FACADE_ORIGINS = Object.freeze({
  west: Object.freeze([-3.94, 1.675, 0]),
  front: Object.freeze([0, 1.675, 3.94]),
});

export function facadeCoordinates(point, facade) {
  const origin = FACADE_ORIGINS[facade];
  if (!origin) throw new Error('Unknown house facade');
  return [facade === 'west' ? -(point[2] - origin[2]) : -(point[0] - origin[0]),
          point[1] - origin[1]];
}

export function photographicIntersection(camera, panePoint, facade, depth) {
  const glass = facadeCoordinates(panePoint, facade);
  const eye = facadeCoordinates(camera, facade);
  const outwardDistance = facade === 'west' ? camera[0] - panePoint[0] : panePoint[2] - camera[2];
  const origin=FACADE_ORIGINS[facade];
  const projectionDepth=facade==='west'?origin[0]-panePoint[0]:panePoint[2]-origin[2];
  return glass.map((coordinate, i) => coordinate + (coordinate - eye[i]) * (depth-projectionDepth) / outwardDistance);
}

export function doorGlassCoverage(x, y, openness) {
  const a=BALCONY_ACCESS, left=a.centre-a.width/2, right=a.centre+a.width/2;
  const amount=Number.isFinite(openness)?Math.max(0,Math.min(1,openness)):0;
  const cleared=Math.min(right,left+a.slide*amount);
  return x>=left+.025 && x<=cleared-.025 && y>=a.floor+.035 && y<=a.floor+2.665 ? 0 : 1;
}

export function createHouseWindowView(THREE, options, facade) {
  if(!FACADE_ORIGINS[facade])throw new Error('Unknown house facade');
  const a=BALCONY_ACCESS;
  const uniforms={uTime:{value:0},uRain:{value:0},uDoorReveal:{value:options.doorOpenness?1:0},
    uDoorOpenness:options.doorOpenness||{value:0},uDoorOpening:{value:new THREE.Vector4(a.centre-a.width/2,a.centre+a.width/2,a.floor,a.floor+2.7)},uDoorTravel:{value:a.slide}};
  const material=new THREE.ShaderMaterial({uniforms,transparent:true,depthWrite:false,side:THREE.DoubleSide,toneMapped:true,
    vertexShader:`varying vec3 vWorld;varying vec2 vUv;void main(){vUv=uv;vec4 world=modelMatrix*vec4(position,1.);vWorld=world.xyz;gl_Position=projectionMatrix*viewMatrix*world;}`,
    fragmentShader:`uniform float uTime,uRain,uDoorReveal,uDoorOpenness,uDoorTravel;uniform vec4 uDoorOpening;varying vec3 vWorld;varying vec2 vUv;
      void main(){
      if(uDoorReveal>.5){float edge=min(uDoorOpening.y,uDoorOpening.x+uDoorTravel*clamp(uDoorOpenness,0.,1.));
        if(vWorld.x>=uDoorOpening.x+.025&&vWorld.x<=edge-.025&&vWorld.y>=uDoorOpening.z+.035&&vWorld.y<=uDoorOpening.w-.035)discard;}
      vec3 eye=normalize(cameraPosition-vWorld);float facing=abs(dot(eye,vec3(${facade==='west'?'1.,0.,0.':'0.,0.,1.'})));
      float fres=.02+.12*pow(1.-facing,5.);
      vec2 cell=fract(vUv*vec2(90.,55.)+vec2(0.,uTime*.08));
      float drop=smoothstep(.045,.008,length((cell-vec2(.5,.5))*vec2(1.,.4)))*uRain;
      gl_FragColor=vec4(vec3(.48,.6,.64)+drop*.15,fres+drop*.2);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      }`});
  let mesh;
  return {material,get mesh(){return mesh;},build(surface,scene){mesh=new THREE.Mesh(new THREE.PlaneGeometry(surface.w,surface.h),material);mesh.position.set(...surface.c);mesh.rotation.y=surface.ry||0;mesh.name='physical_window_glass_'+facade;mesh.userData.excludeStaticBake=true;scene.add(mesh);return mesh;},
    update(dt,hour){
      if(!Number.isFinite(dt)||dt<0)dt=0;
      uniforms.uTime.value+=dt;
      const rain=Number.isFinite(hour)?weatherAt(tokyoDayKey(),hour).rain:0;
      uniforms.uRain.value+=(rain-uniforms.uRain.value)*(1-Math.exp(-dt*.05));
    },state(){return {probes:0,textures:0,physicalGlass:true,rain:uniforms.uRain.value};}};
}
