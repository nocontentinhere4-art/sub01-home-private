// Bounded single-scattering window shafts. The house renders once into HDR +
// depth; a quarter-size march uses that depth and the actual sun shadow map.
// Lite mode allocates no targets. No second room or hidden game scene exists.
export function createSunShafts(T, renderer, lite) {
  let colorTarget, volumeTarget, march, composite, screen, quad;
  const size = new T.Vector2();
  const cameraWorld = new T.Matrix4(), inverseProjection = new T.Matrix4();
  const sunDirection = new T.Vector3(), sunTarget = new T.Vector3();
  const fullCamera = new T.OrthographicCamera(-1,1,1,-1,0,1);
  const vertex = `varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`;
  function setup() {
    colorTarget = new T.WebGLRenderTarget(1,1,{type:T.HalfFloatType,depthBuffer:true});
    colorTarget.samples = Math.min(2, renderer.capabilities.maxSamples);
    colorTarget.depthTexture = new T.DepthTexture(1,1,T.UnsignedIntType);
    colorTarget.texture.minFilter=colorTarget.texture.magFilter=T.LinearFilter;
    volumeTarget = new T.WebGLRenderTarget(1,1,{type:T.HalfFloatType,depthBuffer:false});
    volumeTarget.texture.minFilter=volumeTarget.texture.magFilter=T.NearestFilter;
    march = new T.ShaderMaterial({depthTest:false,depthWrite:false,toneMapped:false,
      uniforms:{depth:{value:colorTarget.depthTexture}, invProjection:{value:inverseProjection},
        cameraWorld:{value:cameraWorld}, shadowMap:{value:null},shadowMatrix:{value:new T.Matrix4()},
        sunDirection:{value:sunDirection}, sunColor:{value:new T.Color()}, gain:{value:0}},
      vertexShader:vertex, fragmentShader:`
        varying vec2 vUv;
        uniform sampler2D depth,shadowMap; uniform mat4 invProjection,cameraWorld,shadowMatrix;
        uniform vec3 sunDirection,sunColor; uniform float gain;
        #include <packing>
        float aperture(vec3 p) {
          if(abs(p.x)>3.84 || p.z< -3.85 || p.z>3.84 || p.y<.08 || p.y>5.75) return 0.;
          if(p.y>3. && p.x<-.85 && p.z>.5 && p.z<2.7) return 0.;
          float light=0.;
          if(p.y<2.72 && sunDirection.x<-.05) {
            float t=(-3.84-p.x)/sunDirection.x; vec3 q=p+sunDirection*t;
            if(t>0. && q.y>.72 && q.y<2.70 && abs(q.z)<3.75 &&
              abs(q.z-1.35)>.10 && abs(q.z+1.35)>.10) light=1.;
          }
          if(sunDirection.z>.05) {
            float t=(3.84-p.z)/sunDirection.z; vec3 q=p+sunDirection*t;
            if(t>0. && p.y<2.72 && q.y>.72 && q.y<2.70 &&
              ((q.x> -3.82 && q.x<-.18)||(q.x>.2 && q.x<1.1)||(q.x>2.8 && q.x<3.7))) light=1.;
            if(t>0. && p.y>3.1 && p.x<-.2 && q.x> -3.82 && q.x<-.28 && q.y>3.2 && q.y<5.65) light=1.;
          }
          if(light<.5) return 0.;
          vec4 s=shadowMatrix*vec4(p,1.); vec3 uv=s.xyz/s.w;
          if(any(lessThan(uv,vec3(0.)))||any(greaterThan(uv,vec3(1.)))) return 0.;
          return step(uv.z-.00035,unpackRGBAToDepth(texture2D(shadowMap,uv.xy)));
        }
        void main(){
          float d=texture2D(depth,vUv).x;
          vec4 endpoint=invProjection*vec4(vUv*2.-1.,d*2.-1.,1.); endpoint/=endpoint.w;
          float surfaceDistance=length(endpoint.xyz), distance=min(surfaceDistance,12.);
          vec3 origin=cameraWorld[3].xyz, ray=normalize((cameraWorld*vec4(endpoint.xyz,0.)).xyz);
          float cosine=dot(ray,sunDirection), g=.45;
          float phase=(1.-g*g)/pow(max(.01,1.+g*g-2.*g*cosine),1.5);
          float stepSize=distance/24., integral=0.;
          for(int i=0;i<24;i++){
            vec3 p=origin+ray*(float(i)+.5)*stepSize;
            integral+=aperture(p)*stepSize;
          }
          vec3 scattering=sunColor*gain*phase*integral*.018;
          gl_FragColor=vec4(scattering,surfaceDistance);
        }`});
    composite = new T.ShaderMaterial({depthTest:false,depthWrite:false,
      uniforms:{color:{value:colorTarget.texture}, volume:{value:volumeTarget.texture},
        depth:{value:colorTarget.depthTexture}, invProjection:{value:inverseProjection}, texel:{value:new T.Vector2()}},
      vertexShader:vertex, fragmentShader:`
        varying vec2 vUv; uniform sampler2D color,volume,depth;
        uniform mat4 invProjection; uniform vec2 texel;
        void main(){
          float d=texture2D(depth,vUv).r;
          vec4 p=invProjection*vec4(vUv*2.-1.,d*2.-1.,1.); float distance=length(p.xyz/p.w);
          vec3 scatter=vec3(0.);float weights=0.;
          for(int x=0;x<2;x++)for(int y=0;y<2;y++){
            vec4 fog=texture2D(volume,vUv+(vec2(float(x),float(y))-.5)*texel);
            float w=1./(.02+abs(fog.a-distance));scatter+=fog.rgb*w;weights+=w;
          }
          gl_FragColor=vec4(texture2D(color,vUv).rgb+scatter/max(weights,.0001),1.);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`});
    screen=new T.Scene();quad=new T.Mesh(new T.PlaneGeometry(2,2),march);quad.frustumCulled=false;screen.add(quad);
  }
  return {
    async prepare(scene, camera) {
      if (lite || !renderer.extensions.has('EXT_color_buffer_float')) return;
      if (!colorTarget) setup();
      const previousTarget = renderer.getRenderTarget();
      try {
        // The HDR room pass has a different tone-mapping shader variant from
        // direct rendering. Compile both, without rendering or moving a camera.
        renderer.setRenderTarget(colorTarget);
        await renderer.compileAsync(scene, camera);
        quad.material = march;
        renderer.setRenderTarget(volumeTarget);
        await renderer.compileAsync(screen, fullCamera);
        quad.material = composite;
        renderer.setRenderTarget(null);
        await renderer.compileAsync(screen, fullCamera);
      } finally {
        renderer.setRenderTarget(previousTarget);
      }
    },
    render(scene,camera,light,sun,curtainOpen) {
      if(lite || !renderer.extensions.has('EXT_color_buffer_float') || !curtainOpen || light.sunIntensity<.2 || !sun.castShadow ||
        Math.abs(camera.position.x)>4 || camera.position.z>4 || camera.position.z< -4) return false;
      if(!colorTarget) setup();
      renderer.getDrawingBufferSize(size);
      const w=Math.max(1,Math.floor(size.x)),h=Math.max(1,Math.floor(size.y));
      const scale=Math.min(.5,Math.sqrt(240000/(w*h))), vw=Math.max(1,Math.floor(w*scale)),vh=Math.max(1,Math.floor(h*scale));
      if(colorTarget.width!==w||colorTarget.height!==h) colorTarget.setSize(w,h);
      if(volumeTarget.width!==vw||volumeTarget.height!==vh) volumeTarget.setSize(vw,vh);
      camera.updateMatrixWorld();
      cameraWorld.copy(camera.matrixWorld);inverseProjection.copy(camera.projectionMatrixInverse);
      sun.getWorldPosition(sunDirection);sun.target.getWorldPosition(sunTarget);sunDirection.sub(sunTarget).normalize();
      march.uniforms.sunColor.value.copy(sun.color);march.uniforms.gain.value=light.sunIntensity;
      renderer.setRenderTarget(colorTarget);renderer.render(scene,camera);
      march.uniforms.shadowMap.value=sun.shadow.map.texture;march.uniforms.shadowMatrix.value.copy(sun.shadow.matrix);
      quad.material=march;renderer.setRenderTarget(volumeTarget);renderer.render(screen,fullCamera);
      composite.uniforms.texel.value.set(1/vw,1/vh);
      quad.material=composite;renderer.setRenderTarget(null);renderer.render(screen,fullCamera);
      return true;
    },
    pixels(){return volumeTarget ? volumeTarget.width*volumeTarget.height : 0;},
    dispose(){colorTarget?.dispose();volumeTarget?.dispose();march?.dispose();composite?.dispose();quad?.geometry.dispose();}
  };
}
