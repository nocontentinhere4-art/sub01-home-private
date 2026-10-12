// Prepare the actual room without moving its camera or rendering a hidden scene.
// LoadingManager tracks nested glTF textures as well as the initial requests.
export function createHomeStartup(manager, report, pause = () => new Promise(resolve => setTimeout(resolve, 16))) {
  let busy = false, generation = 0, ready = false;
  const started = performance.now();
  manager.onStart = () => { busy = true; generation++; };
  manager.onProgress = (_url, loaded, total) => report('assets', `Opening his home · ${loaded} / ${total}`);
  manager.onLoad = () => { busy = false; generation++; };
  async function idle() {
    for (;;) {
      const version = generation;
      await pause();
      if (!busy && version === generation) return;
    }
  }
  function textures(scenes) {
    const found = new Set();
    const add = value => { if (value?.isTexture && !value.isRenderTargetTexture) found.add(value); };
    for (const scene of scenes) {
      add(scene.environment); add(scene.background);
      scene.traverse(object => {
        for (const material of [object.material].flat()) {
          if (!material) continue;
          for (const value of Object.values(material)) add(value);
          for (const uniform of Object.values(material.uniforms || {})) add(uniform.value);
        }
      });
    }
    return [...found];
  }
  return {
    get ready() { return ready; },
    async prepare(renderer, scene, camera, privacyScene, privacyCamera, prerequisites, effects) {
      await Promise.allSettled(prerequisites);
      await idle();
      const maps = textures([scene, privacyScene]);
      report('textures', `Preparing materials · 0 / ${maps.length}`);
      // One upload per task leaves the browser time to paint the loading UI.
      for (let i = 0; i < maps.length; i++) {
        renderer.initTexture(maps[i]);
        report('textures', `Preparing materials · ${i + 1} / ${maps.length}`);
        await pause();
      }
      report('shaders', 'Preparing the room lighting…');
      await renderer.compileAsync(scene, camera);
      await renderer.compileAsync(privacyScene, privacyCamera);
      await effects?.prepare(scene, camera);
      ready = true;
      report('ready', '', { textures: maps.length, milliseconds: Math.round(performance.now() - started) });
    },
    fallback() { ready = true; report('fallback', 'Opening the room with available materials…'); },
  };
}
