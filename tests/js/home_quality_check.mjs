import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const actual=source.slice(source.indexOf('const lite ='),source.indexOf('const assetRoot ='));
const select=new Function('location','innerWidth','navigator','matchMedia',actual+'return Boolean(lite);');
const mode=({width=1200,memory=8,touch=0,coarse=false,query=''}={})=>select(
  {search:query},width,{deviceMemory:memory,maxTouchPoints:touch},()=>({matches:coarse}));
assert.equal(mode(),false,'Normal desktop keeps full detail');
assert.equal(mode({query:'?lite'}),true,'Explicit lightweight mode');
assert.equal(mode({memory:4}),true,'Known lower-memory desktop');
assert.equal(mode({width:390,memory:undefined,touch:5,coarse:true}),true,'Phone portrait');
assert.equal(mode({width:844,memory:undefined,touch:5,coarse:true}),true,'Phone landscape must not switch to full textures');
assert.equal(mode({width:1200,touch:10,coarse:false}),false,'Fine-pointer desktop retains quality despite touchscreen');
console.log('PASS: actual quality selector protects portrait/landscape phones and preserves full desktop detail');
