// Photographic camera response for the real house in full mode: the room is
// rendered once into a linear HDR target (or receives the sun-shaft composite),
// then a bounded post chain adds physically motivated lens bloom, slow eye
// adaptation, a soft optical vignette and fine sensor grain before the existing
// ACES/sRGB output transform. Lite, privacy and missing float targets bypass it
// and allocate nothing. No second room scene is created or rendered.
export const CAMERA_DEFAULTS = Object.freeze({
  // Subtle by design: the physically based exposure (1.0) stays the anchor;
  // adaptation only nudges it within roughly -15 % / +30 %, and bloom only
  // affects HDR values above the display white (windows, lamp shades).
  bloomStrength: .04, bloomThreshold: 1.1, bloomKnee: .5, bloomRadius: 1,
  reference: .22, adaptation: .3, minExposure: .85, maxExposure: 1.3,
  adaptSpeedUp: 1.6, adaptSpeedDown: .75,
  vignette: .18, grain: .008, aberration: .0015, maxLevels: 6,
});

export function adaptationBlend(dt, previous, target, up, down) {
  // Brightening (stepping into a sunlit room) adapts faster than darkening,
  // like the eye/auto-exposure of a real camera. Exponential in time, so 30
  // and 60 fps converge identically.
  const speed = target > previous ? up : down;
  return 1 - Math.exp(-Math.max(0, dt) * speed);
}

export function createCameraEffects(T, renderer, lite, settings = {}) {
  const S = { ...CAMERA_DEFAULTS, ...settings };
  let input, mips = [], lum = [], lumIndex = 0, down, up, luminance, final, screen, quad, primed = false;
  let time = 0, lastExposure = null, reading = false, readTimer = -Infinity;
  const size = new T.Vector2();
  const fullCamera = new T.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const vertex = `varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`;
  const half = { type: T.HalfFloatType, depthBuffer: false, minFilter: T.LinearFilter, magFilter: T.LinearFilter };
  const supported = () => !lite && renderer.extensions.has('EXT_color_buffer_float');

  function setup() {
    input = new T.WebGLRenderTarget(1, 1, { type: T.HalfFloatType, depthBuffer: true });
    input.samples = Math.min(2, renderer.capabilities.maxSamples);
    input.texture.minFilter = input.texture.magFilter = T.LinearFilter;
    for (let i = 0; i < 2; i++) {
      // 1x1 meter in full float: readable by readRenderTargetPixelsAsync.
      const t = new T.WebGLRenderTarget(1, 1, { type: T.FloatType, depthBuffer: false });
      t.texture.minFilter = t.texture.magFilter = T.NearestFilter;
      lum.push(t);
    }
    down = new T.ShaderMaterial({ depthTest: false, depthWrite: false, toneMapped: false,
      uniforms: { src: { value: null }, texel: { value: new T.Vector2() }, prefilter: { value: 0 },
        threshold: { value: S.bloomThreshold }, knee: { value: S.bloomKnee } },
      vertexShader: vertex, fragmentShader: `
        varying vec2 vUv; uniform sampler2D src; uniform vec2 texel; uniform float prefilter,threshold,knee;
        vec3 s(float x,float y){return texture2D(src,vUv+vec2(x,y)*texel).rgb;}
        float luma(vec3 c){return dot(c,vec3(.2126,.7152,.0722));}
        vec3 karis(vec3 a,vec3 b,vec3 c,vec3 d){vec3 m=(a+b+c+d)*.25;return m/(1.+luma(m));}
        void main(){
          vec3 a=s(-2.,2.),b=s(0.,2.),c=s(2.,2.),d=s(-2.,0.),e=s(0.,0.),f=s(2.,0.),
               g=s(-2.,-2.),h=s(0.,-2.),i=s(2.,-2.),j=s(-1.,1.),k=s(1.,1.),l=s(-1.,-1.),m=s(1.,-1.);
          vec3 color;
          if(prefilter>.5){
            // Karis-weighted 13-tap first level: a single bright texel (a lamp
            // filament, a specular glint) cannot flicker into a large flare.
            color=karis(j,k,l,m)*.5+(karis(a,b,d,e)+karis(b,c,e,f)+karis(d,e,g,h)+karis(e,f,h,i))*.125;
            color/=max(1.-luma(color),.05);
            float br=max(color.r,max(color.g,color.b));
            float soft=clamp(br-threshold+knee,0.,2.*knee); soft=soft*soft/(4.*knee+1e-4);
            color*=max(soft,br-threshold)/max(br,1e-4);
          } else color=e*.125+(a+c+g+i)*.03125+(b+d+f+h)*.0625+(j+k+l+m)*.125;
          gl_FragColor=vec4(max(color,vec3(0.)),1.);
        }` });
    up = new T.ShaderMaterial({ depthTest: false, depthWrite: false, toneMapped: false,
      blending: T.AdditiveBlending, transparent: true,
      uniforms: { src: { value: null }, texel: { value: new T.Vector2() }, weight: { value: 1 } },
      vertexShader: vertex, fragmentShader: `
        varying vec2 vUv; uniform sampler2D src; uniform vec2 texel; uniform float weight;
        vec3 s(float x,float y){return texture2D(src,vUv+vec2(x,y)*texel).rgb;}
        void main(){
          vec3 c=s(-1.,1.)+2.*s(0.,1.)+s(1.,1.)+2.*s(-1.,0.)+4.*s(0.,0.)+2.*s(1.,0.)+s(-1.,-1.)+2.*s(0.,-1.)+s(1.,-1.);
          gl_FragColor=vec4(c*(weight/16.),1.);
        }` });
    luminance = new T.ShaderMaterial({ depthTest: false, depthWrite: false, toneMapped: false,
      uniforms: { src: { value: null }, previous: { value: null }, dt: { value: 0 }, snap: { value: 1 },
        speedUp: { value: 0 }, speedDown: { value: 0 } },
      vertexShader: vertex, fragmentShader: `
        varying vec2 vUv; uniform sampler2D src,previous; uniform float dt,snap,speedUp,speedDown;
        void main(){
          // Centre-weighted log average over 256 linear taps of the HDR scene:
          // bright windows at the frame edge count less,
          // as in a photographer's centre-weighted meter.
          float total=0.,weights=0.;
          for(int x=0;x<16;x++)for(int y=0;y<16;y++){
            vec2 uv=mix(vec2(.04),vec2(.96),(vec2(float(x),float(y))+.5)/16.);
            float w=1.-.65*smoothstep(.1,.7,length(uv-.5));
            float l=dot(texture2D(src,uv).rgb,vec3(.2126,.7152,.0722));
            total+=w*log(max(l,1e-4));weights+=w;
          }
          float current=exp(total/weights), prior=texture2D(previous,vec2(.5)).r;
          float rate=snap>.5?1.:1.-exp(-dt*(current>prior?speedUp:speedDown));
          gl_FragColor=vec4(mix(prior,current,rate),0.,0.,1.);
        }` });
    final = new T.ShaderMaterial({ depthTest: false, depthWrite: false,
      uniforms: { color: { value: input.texture }, bloom: { value: null }, meter: { value: null },
        bloomStrength: { value: S.bloomStrength }, reference: { value: S.reference },
        adaptation: { value: S.adaptation }, minExposure: { value: S.minExposure }, maxExposure: { value: S.maxExposure },
        vignette: { value: S.vignette }, grain: { value: S.grain }, aberration: { value: S.aberration },
        aspect: { value: 1 }, time: { value: 0 } },
      vertexShader: vertex, fragmentShader: `
        varying vec2 vUv; uniform sampler2D color,bloom,meter;
        uniform float bloomStrength,reference,adaptation,minExposure,maxExposure,vignette,grain,aberration,aspect,time;
        void main(){
          float average=max(texture2D(meter,vec2(.5)).r,1e-4);
          float exposure=clamp(pow(reference/average,adaptation),minExposure,maxExposure);
          vec2 d=vUv-.5; vec2 shift=d*dot(d,d)*aberration;
          vec3 c=vec3(texture2D(color,vUv-shift).r,texture2D(color,vUv).g,texture2D(color,vUv+shift).b);
          c+=texture2D(bloom,vUv).rgb*bloomStrength;
          // cos^4-like natural falloff of a wide lens, never darker than 1-vignette.
          float r=length(d*vec2(aspect,1.))/length(vec2(aspect,1.)*.5);
          c*=exposure*(1.-vignette*smoothstep(.35,1.05,r)*smoothstep(.35,1.05,r));
          gl_FragColor=vec4(c,1.);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
          float n=fract(sin(dot(gl_FragCoord.xy+fract(time*7.31)*97.,vec2(12.9898,78.233)))*43758.5453);
          float m=fract(sin(dot(gl_FragCoord.yx+fract(time*3.17)*61.,vec2(39.3468,11.1353)))*24634.6345);
          // Triangular dither-grain: hides 8-bit banding in soft wall gradients.
          gl_FragColor.rgb+=(n+m-1.)*grain;
        }` });
    screen = new T.Scene();
    quad = new T.Mesh(new T.PlaneGeometry(2, 2), final);
    quad.frustumCulled = false;
    screen.add(quad);
  }

  function resize(w, h) {
    if (input.width !== w || input.height !== h) input.setSize(w, h);
    let mw = Math.max(1, w >> 1), mh = Math.max(1, h >> 1);
    const wanted = [];
    while (wanted.length < S.maxLevels && Math.min(mw, mh) >= 8) {
      wanted.push([mw, mh]); mw = Math.max(1, mw >> 1); mh = Math.max(1, mh >> 1);
    }
    while (mips.length > wanted.length) mips.pop().dispose();
    wanted.forEach(([x, y], i) => {
      if (!mips[i]) mips[i] = new T.WebGLRenderTarget(x, y, half);
      else if (mips[i].width !== x || mips[i].height !== y) mips[i].setSize(x, y);
    });
  }

  function pass(material, target) {
    quad.material = material;
    renderer.setRenderTarget(target);
    renderer.render(screen, fullCamera);
  }

  function post(dt) {
    // Bloom: downsample chain from half resolution, then tent upsample with
    // additive accumulation back into each larger level.
    let source = input;
    mips.forEach((target, i) => {
      down.uniforms.src.value = source.texture;
      down.uniforms.texel.value.set(1 / source.width, 1 / source.height);
      down.uniforms.prefilter.value = i === 0 ? 1 : 0;
      pass(down, target);
      source = target;
    });
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    try {
      for (let i = mips.length - 1; i > 0; i--) {
        up.uniforms.src.value = mips[i].texture;
        up.uniforms.texel.value.set(S.bloomRadius / mips[i].width, S.bloomRadius / mips[i].height);
        up.uniforms.weight.value = 1;
        pass(up, mips[i - 1]);
      }
    } finally { renderer.autoClear = autoClear; }
    // Exposure meter: ping-pong 1x1 targets, time-based smoothing.
    const previous = lum[lumIndex], next = lum[1 - lumIndex];
    luminance.uniforms.src.value = input.texture;  // the scene, never the thresholded bloom chain
    luminance.uniforms.previous.value = previous.texture;
    luminance.uniforms.dt.value = Math.min(Math.max(dt, 0), .1);
    luminance.uniforms.snap.value = primed ? 0 : 1;
    luminance.uniforms.speedUp.value = S.adaptSpeedUp;
    luminance.uniforms.speedDown.value = S.adaptSpeedDown;
    pass(luminance, next);
    lumIndex = 1 - lumIndex; primed = true;
    time = (time + dt) % 1000;
    final.uniforms.bloom.value = (mips[0] || input).texture;
    final.uniforms.meter.value = next.texture;
    final.uniforms.time.value = time;
    final.uniforms.aspect.value = input.width / Math.max(1, input.height);
    pass(final, null);
    sampleExposure(next, dt);
  }

  function sampleExposure(target, dt) {
    // Diagnostics only: an asynchronous 1x1 read at most once per second.
    // Wall-clock gate: the loop caps dt at 50 ms, so summing it would stall on slow GPUs.
    const now = globalThis.performance?.now?.() ?? Date.now();
    if (reading || now - readTimer < 1000 || !renderer.readRenderTargetPixelsAsync) return;
    readTimer = now; reading = true;
    const buffer = new Float32Array(4);
    Promise.resolve().then(() => renderer.readRenderTargetPixelsAsync(target, 0, 0, 1, 1, buffer))
      .then(() => {
        const average = Math.max(buffer[0], 1e-4);
        lastExposure = { average, exposure: Math.min(S.maxExposure, Math.max(S.minExposure, (S.reference / average) ** S.adaptation)) };
      }).catch(() => { lastExposure = null; }).finally(() => { reading = false; });
  }

  return {
    settings: S,
    async prepare(scene, camera) {
      if (!supported()) return;
      if (!input) setup();
      const previousTarget = renderer.getRenderTarget();
      try {
        renderer.setRenderTarget(input);
        await renderer.compileAsync(scene, camera);
        for (const [material, target] of [[down, input], [up, input], [luminance, lum[0]], [final, null]]) {
          quad.material = material;
          renderer.setRenderTarget(target);
          await renderer.compileAsync(screen, fullCamera);
        }
      } finally {
        renderer.setRenderTarget(previousTarget);
      }
    },
    // `renderRoom(target)` draws the house (directly or through the sun-shaft
    // composite) into the supplied linear HDR target and returns true; if it
    // returns false the house is rendered here into the same target.
    render(scene, camera, dt, renderRoom) {
      if (!supported()) return false;
      if (!input) setup();
      renderer.getDrawingBufferSize(size);
      const w = Math.max(1, Math.floor(size.x)), h = Math.max(1, Math.floor(size.y));
      resize(w, h);
      const previousTarget = renderer.getRenderTarget();
      try {
        if (!renderRoom?.(input)) {
          renderer.setRenderTarget(input);
          renderer.render(scene, camera);
        }
        post(dt);
      } finally {
        renderer.setRenderTarget(previousTarget);
      }
      return true;
    },
    target() {
      if (!supported()) return null;
      if (!input) setup();
      return input;
    },
    reset() { primed = false; },
    stats() {
      return { levels: mips.length, exposure: lastExposure && Number(lastExposure.exposure.toFixed(3)),
        meteredLuminance: lastExposure && Number(lastExposure.average.toFixed(4)) };
    },
    targets() { return [input, ...mips, ...lum].filter(Boolean); },
    dispose() {
      input?.dispose(); mips.forEach(t => t.dispose()); lum.forEach(t => t.dispose());
      down?.dispose(); up?.dispose(); luminance?.dispose(); final?.dispose(); quad?.geometry.dispose();
      mips = []; lum = []; input = null;
    },
  };
}
