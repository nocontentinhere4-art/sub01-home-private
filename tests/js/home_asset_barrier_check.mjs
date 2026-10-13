import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';
import {createSettledAssetBarrier} from '../../web/house/settled_asset_barrier.mjs';
import {createHomeStartup} from '../../web/house/startup.mjs';
import {inspectReplacedAssets,retireReplacedAssets,releaseStartupModelCache} from '../../web/house/replaced_asset_cleanup.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
function between(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a,`Actual source block missing: ${start}`);return source.slice(a,b);}
const furnishedCode=between('function furnished(...args)', '// Licensed CC0 modern linen sofa');
const chairCode=between('const officeChairReady =', '\nobstacle(2, -1.9');
const sofaCode=between('const sofaReady =', '\nconst coffeeTableReady =');
const registry=between('for (const task of [beddingReady', '\nasync function applyContactLighting()');
const contactCode=between('async function applyContactLighting()', '\nconst contactLightingReady =');
const startupCode=between('startup.prepare(renderer, scene, camera, privacyScene, privacyCamera,', '\nrenderer.info.autoReset = false;');
const exportCode=between('  const b = button("Export house geometry"', '\n  document.querySelector("footer").append(b);');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};

// Execute production source blocks; only network/renderer/DOM are test fixtures.
const chairParse=deferred(),sofaParse=deferred(),fallbackParse=deferred(),scene=new T.Scene(),status={dataset:{}},events=[],requests=[];
const manager={},officeChair=[new T.Mesh(new T.BoxGeometry(),new T.MeshStandardMaterial())];scene.add(...officeChair);
const chairCount=()=>{let n=0;scene.traverse(o=>{if(o.name.startsWith('chair_owner_'))n++;});return n;};
const scope={T,scene,officeChair,assetBarrier:createSettledAssetBarrier(),modelCache:new Map(),assetRoot:'/house/assets/',rigidPots:[],rigidPotFromMesh:()=>null,
 console:{warn(){}},notice(){},document:{getElementById:()=>status},bakedObjects:new Map(),havenSofaMaterials:{},
 renderer:{shadowMap:{},initTexture(){events.push(['texture',chairCount()]);},async compileAsync(target){events.push(['compile',chairCount(),target]);}},
 gltfLoader:{loadAsync(url){requests.push(url);if(url==='/room/chair_owner.glb')return chairParse.promise;if(url.includes('haven-sofa'))return sofaParse.promise;if(url.includes('sofa_03'))return fallbackParse.promise;events.push(['contact-load',chairCount()]);return Promise.resolve({scene:new T.Scene()});}},
 loader:{loadAsync(){events.push(['contact-texture',chairCount()]);return Promise.resolve(new T.Texture());}},
 location:{search:''},useIndirectLighting:false,lite:false,nightLightUniform:{value:null},switchedMaterials:new Set(),M:{},interactions:[],
 privacyScene:new T.Scene(),privacyCamera:new T.Camera(),camera:new T.Camera(),sunShafts:{async prepare(){events.push(['effects',chairCount()]);}},
 inspectReplacedAssets,retireReplacedAssets,
 releaseStartupModelCache:async(...args)=>{events.push(['cache-release',chairCount()]);return releaseStartupModelCache(...args);},
};
for(const name of registry.matchAll(/\b([A-Za-z]+Ready)\b/g))if(!['officeChairReady','sofaReady'].includes(name[1]))scope[name[1]]=Promise.resolve();
const actual=new Function('scope',`with(scope){${furnishedCode}\n${chairCode}\n${sofaCode}\n${registry}\nreturn{furnished,officeChairReady,sofaReady,homeAssetsReady};}`)(scope);
Object.assign(scope,actual);
const startup=createHomeStartup(manager,(stage)=>events.push([stage,chairCount()]),()=>Promise.resolve());scope.startup=startup;
manager.onLoad(); // Network has finished; GLTF parser is deliberately still pending.
scope.contactLightingReady=new Function('scope',`with(scope){${contactCode}\nreturn applyContactLighting();}`)(scope);
new Function('scope',`with(scope){${startupCode}}`)(scope);
let exportHandler;
scope.button=(_label,handler)=>{exportHandler=handler;return{};};
scope.staticBakeScene=s=>{events.push(['export-scene',chairCount()]);return s;};
scope.GLTFExporter=class{async parseAsync(s){events.push(['export-parse',chairCount()]);assert.equal(s,scene);return new ArrayBuffer(1);}};
scope.fetch=async()=>({ok:true});
new Function('scope',`with(scope){${exportCode}}`)(scope);
const exportDone=exportHandler();
await flush();assert.equal(startup.ready,false);assert.equal(chairCount(),0);assert.equal(events.some(e=>['contact-load','compile','texture','export-parse','cache-release'].includes(e[0])),false,'idle manager cannot bypass actual chair parse barrier');

// Execute real sofa catch→furnished wrapper→loadFurnished registration. The
// fallback is spawned after the bottom registry has already begun draining.
sofaParse.reject(new Error('Licensed sofa transport failed'));await flush();assert.ok(requests.some(url=>url.includes('sofa_03')));assert.equal(startup.ready,false);
const chair=new T.Scene(),chairMap=new T.Texture();for(let i=0;i<7;i++){const mesh=new T.Mesh(new T.BoxGeometry(),new T.MeshStandardMaterial({map:chairMap}));mesh.name=`chair_owner_${i}`;chair.add(mesh);}
chairParse.resolve({scene:chair});await actual.officeChairReady;await flush();assert.equal(chairCount(),7);assert.equal(startup.ready,false,'chair completion alone must not bypass transitive fallback parse');assert.equal(events.some(e=>['compile','export-parse','cache-release'].includes(e[0])),false);
const fallback=new T.Scene();fallback.add(new T.Mesh(new T.BoxGeometry(),new T.MeshStandardMaterial()));fallbackParse.resolve({scene:fallback});
await actual.homeAssetsReady;await exportDone;await scope.contactLightingReady;await flush();
assert.equal(startup.ready,true);assert.ok(events.some(e=>e[0]==='contact-load'));assert.ok(events.some(e=>e[0]==='compile'));assert.ok(events.some(e=>e[0]==='texture'));assert.ok(events.some(e=>e[0]==='export-parse'));assert.ok(events.some(e=>e[0]==='cache-release'));
for(const event of events.filter(e=>['contact-load','contact-texture','texture','compile','effects','ready','export-scene','export-parse','cache-release'].includes(e[0])))assert.equal(event[1],7,`${event[0]} must see all actual chair meshes`);
assert.equal(scene.children.includes(chair),true);assert.equal(officeChair[0],chair);assert.equal(officeChair.length,1);assert.equal(scope.modelCache.size,0);assert.equal(status.dataset.releasedModelCache!==undefined,true);
assert.ok(events.findIndex(e=>e[0]==='cache-release')>events.findIndex(e=>e[0]==='ready'),'cache releases only after actual startup readiness');
console.log('PASS actual home.js: deferred owner-chair parse blocks contact/compile/prewarm/export/cache cleanup despite idle manager; all downstream consumers see seven chair meshes; actual sofa rejection spawns furnished fallback tracked during drain; real startup and cache cleanup ordering preserved.');
