// A bounded local light from the actual cached screen canvas. No extra render,
// shadow, readback of the WebGL scene, device command or source texture ownership.
export function createDeviceScreenLight(T,scene,screenMesh,{
 maxIntensity=.7,distance=1.8,sampleInterval=.5,
 createCanvas=()=>document.createElement('canvas'),
}={}){
 if(!Number.isFinite(maxIntensity)||maxIntensity<0||!Number.isFinite(distance)||distance<=0)throw new TypeError('Screen light needs finite nonnegative intensity and positive distance');
 if(!Number.isFinite(sampleInterval)||sampleInterval<.5)throw new TypeError('Screen light sampling must be at most 2 Hz');
 let sampler=null,context=null;
 try{sampler=createCanvas();sampler.width=sampler.height=1;context=sampler.getContext('2d',{willReadFrequently:true});}catch{/* Sampling unavailable: leave this optional light off. */}
 const light=new T.SpotLight(0xffffff,0,distance,Math.PI/3,1,2),target=new T.Object3D();
 light.castShadow=false;light.userData.excludeStaticBake=true;target.userData.excludeStaticBake=true;
 light.target=target;scene.add(light,target);
 const position=new T.Vector3(),normal=new T.Vector3(),normalMatrix=new T.Matrix3();
 const desiredColor=new T.Color(1,1,1);
 let elapsed=sampleInterval,desiredIntensity=0,disposed=false;
 const linear=value=>{value/=255;return value<=.04045?value/12.92:Math.pow((value+.055)/1.055,2.4);};
 function update(dt,canvas,{active=true,privacy=false,hidden=false}={}){
  if(disposed)return;
  const seconds=Number.isFinite(dt)?Math.max(0,dt):0;
  elapsed=Math.min(sampleInterval,elapsed+seconds);
  if(!active||privacy||hidden){light.intensity=desiredIntensity=0;return;}
  // Transform the physical plane normal, not camera/world Euler guesses.
  screenMesh.updateWorldMatrix(true,false);
  position.setFromMatrixPosition(screenMesh.matrixWorld);
  normal.set(0,0,1).applyNormalMatrix(normalMatrix.getNormalMatrix(screenMesh.matrixWorld));
  light.position.copy(position).addScaledVector(normal,.015);
  target.position.copy(position).addScaledVector(normal,distance);
  if(elapsed>=sampleInterval){
   elapsed=0;desiredIntensity=0;
   try{
    if(context&&canvas&&canvas.width>0&&canvas.height>0){
     context.clearRect(0,0,1,1);context.drawImage(canvas,0,0,1,1);
     const rgba=context.getImageData(0,0,1,1).data;
     const alpha=rgba[3]/255,r=linear(rgba[0])*alpha,g=linear(rgba[1])*alpha,b=linear(rgba[2])*alpha;
     const peak=Math.max(r,g,b),luminance=.2126*r+.7152*g+.0722*b;
     if(peak>0){desiredColor.setRGB(r/peak,g/peak,b/peak,T.LinearSRGBColorSpace);desiredIntensity=maxIntensity*Math.min(1,luminance);}
    }
   }catch{/* Tainted/missing canvas never leaves an old bright target. */}
  }
  const fade=1-Math.exp(-Math.min(seconds,.1)/.22);
  light.intensity+=(desiredIntensity-light.intensity)*fade;
  light.color.lerp(desiredColor,fade);
 }
 function dispose(){
  if(disposed)return;disposed=true;light.intensity=0;
  light.removeFromParent();target.removeFromParent();light.dispose();
  // Only our tiny sampling canvas is released, never the real device canvas,
  // screen material, shared map, source geometry, or scene-owned resources.
  if(sampler)sampler.width=sampler.height=0;
  sampler=context=null;
 }
 return{light,target,update,dispose};
}
