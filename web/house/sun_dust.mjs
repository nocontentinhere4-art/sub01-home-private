// One bounded particle draw. Light is projected through actual window apertures;
// outside those sunlit volumes particles are transparent, not glowing room-wide.
export function createSunDust(T, scene, lite) {
  const count = lite ? 100 : 500;
  const geometry = new T.BufferGeometry();
  const positions = new Float32Array(count * 3);
  let seed = 173;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  for (let i=0;i<count;i++) {
    positions[i*3] = random()*7.5-3.75;
    positions[i*3+1] = random()*5.5+.25;
    positions[i*3+2] = random()*7.5-3.75;
  }
  geometry.setAttribute('position', new T.BufferAttribute(positions,3));
  const material = new T.ShaderMaterial({
    transparent:true, depthWrite:false, depthTest:true, blending:T.AdditiveBlending,
    uniforms:{time:{value:0},sunDirection:{value:new T.Vector3()},gain:{value:0}},
    vertexShader:`
      uniform float time; uniform vec3 sunDirection; uniform float gain;
      varying float brightness;
      bool lowerWindow(vec3 p) {
        return p.y > .7 && p.y < 2.72 &&
          ((p.x > -3.82 && p.x < -.18) || (p.x > .2 && p.x < 1.1) || (p.x > 2.8 && p.x < 3.7));
      }
      void main() {
        vec3 p=position;
        p.x += .025*sin(time*.13+position.z*4.);
        p.z += .025*cos(time*.11+position.x*3.);
        p.y += .04*sin(time*.08+position.x*5.);
        float lit=0.;
        if (p.y < 2.72 && sunDirection.x < -.05) {
          float t=(-3.84-p.x)/sunDirection.x;
          vec3 q=p+sunDirection*t;
          if(t>0. && q.y>.7 && q.y<2.72 && abs(q.z)<3.75 &&
            abs(q.z-1.35)>.10 && abs(q.z+1.35)>.10) lit=1.;
        }
        if (sunDirection.z > .05) {
          float t=(3.85-p.z)/sunDirection.z;
          vec3 q=p+sunDirection*t;
          if(t>0. && p.y<2.72 && lowerWindow(q)) lit=1.;
          if(t>0. && p.y>3.1 && p.x<-.2 && q.x>-3.82 && q.x<-.28 && q.y>3.2 && q.y<5.65) lit=1.;
        }
        if(p.y>3. && p.x<-.85 && p.z>.5 && p.z<2.7) lit=0.;
        brightness=lit*gain;
        vec4 view=modelViewMatrix*vec4(p,1.);
        gl_Position=projectionMatrix*view;
        gl_PointSize=clamp(7./max(.6,-view.z),1.,2.6);
      }`,
    fragmentShader:`varying float brightness;
      void main() {
        float radial=1.-smoothstep(.08,.5,length(gl_PointCoord-.5));
        float alpha=radial*brightness*.38;
        if(alpha<.015) discard;
        gl_FragColor=vec4(1.,.88,.66,alpha);
      }`,
  });
  const points = new T.Points(geometry,material);
  points.frustumCulled=false;
  scene.add(points);
  return {
    count,
    update(dt,light,curtainOpen,camera) {
      material.uniforms.time.value += dt;
      material.uniforms.sunDirection.value.set(...light.sunPosition).normalize();
      material.uniforms.gain.value = Math.min(1,light.sunIntensity/2);
      points.visible = curtainOpen && light.sunIntensity>.2 && Math.abs(camera.x)<4 && camera.z<4;
      return points.visible;
    },
  };
}
