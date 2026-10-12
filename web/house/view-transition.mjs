// Observer mode change, not an animated physical journey through the house.
// No camera, Three scene, renderer, timer, network or animation-frame ownership.
export function createViewTransition({initialMode='follow',overlay,reducedMotion=false,
  fadeOut=.16,opaqueHold=.034,fadeIn=.18}={}) {
  let current=initialMode,target=initialMode,phase='idle',opacity=0,pending=null,hold=0,generation=0;
  const labels={follow:"Switching to SUB-01's view",explore:'Switching to visitor view'};
  function paint(){overlay?.paint({opacity,visible:phase!=='idle',phase,label:labels[target]||'Switching view',mode:target});}
  function clear(){phase='idle';opacity=0;pending=null;hold=0;target=current;paint();}
  paint();
  return {
    get busy(){return phase!=='idle';},
    get currentMode(){return current;},
    request(mode,swap){
      if(typeof swap!=='function')throw new TypeError('View transition requires a swap callback');
      if(mode===target&&phase!=='idle')return false; // repeat must not restart or replace a pending swap
      if(mode===current){
        if(phase==='idle')return false;
        generation++;pending=null;target=current;phase='in';paint();return true;
      }
      generation++;target=mode;pending={swap,generation};hold=0;
      if(reducedMotion){opacity=1;phase='covered';}else phase='out';
      paint();return true;
    },
    cancel(){
      if(phase==='idle')return false;
      generation++;pending=null;target=current;phase='in';paint();return true;
    },
    step(dt){
      if(!Number.isFinite(dt)||dt<0)return;
      dt=Math.min(dt,.1); // hidden-tab/resume cannot skip the separate opaque frame
      if(phase==='out'){
        opacity=Math.min(1,opacity+dt/Math.max(.001,fadeOut));
        if(opacity===1){phase='covered';hold=0;}
        paint();return; // never swap on the frame that first paints opaque
      }
      if(phase==='covered'){
        hold+=dt;paint();
        if(hold<opaqueHold)return;
        const work=pending;pending=null;
        if(work&&work.generation===generation){
          current=target;
          // Opaque paint happened on an earlier frame. Root now copies camera
          // directly to the chosen view; normal actor following resumes there.
          work.swap();
        }
        // A fresh request from inside the callback wins; no stale completion.
        if(work&&work.generation!==generation)return;
        phase='reveal';hold=0;paint();return;
      }
      if(phase==='reveal'){
        // Render at least one post-swap frame behind the fully opaque overlay.
        phase='in';paint();return;
      }
      if(phase==='in'){
        opacity=reducedMotion?0:Math.max(0,opacity-dt/Math.max(.001,fadeIn));
        if(opacity===0)clear();else paint();
      }
    },
    // Only initialization/teardown use reset; user mode changes use request.
    reset(mode=current){generation++;current=target=mode;clear();},
    state(){return {current,target,phase,opacity,generation,pending:!!pending};},
    dispose(){generation++;pending=null;overlay?.dispose();},
  };
}

export function createViewTransitionOverlay(doc) {
  const element=doc.createElement('div');element.id='observer-view-transition';
  element.setAttribute('role','status');element.setAttribute('aria-live','polite');
  element.style.cssText='position:fixed;inset:0;z-index:10000;background:#10141a;color:#e8e7e2;display:grid;place-items:center;font:14px system-ui;pointer-events:none;transition:none;opacity:0;visibility:hidden';
  doc.body.append(element);
  return {
    element,
    paint({opacity,visible,label,phase}){
      element.style.opacity=String(opacity);element.style.visibility=visible?'visible':'hidden';
      if(element.textContent!==label)element.textContent=label;
      element.dataset.phase=phase;
    },
    dispose(){element.remove();},
  };
}
