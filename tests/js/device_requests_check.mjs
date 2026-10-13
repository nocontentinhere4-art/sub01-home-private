import assert from 'node:assert/strict';
import {createOwnedBitmapPainter} from '../../web/house/owned_bitmap_painter.mjs';
import {createMinecraftFrameFeed, actionErrorMessage} from '../../web/house/device_requests.mjs';
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const headers=h=>({get:k=>h[k]??null});
function fixture(){
  const requests=[],painted=[],unavailable=[];let key='minecraft',frame='A';
  const feed=createMinecraftFrameFeed({
    getContextKey:()=>key,isActive:()=>true,getURL:()=>'/api/home/minecraft/frame.jpg',
    paint:(image)=>painted.push(image.name),onUnavailable:(k,r)=>unavailable.push(r.status),
    fetch:async(url,init)=>{
      const tag=`"${frame}"`;requests.push(init.headers['If-None-Match']||null);
      if(init.headers['If-None-Match']===tag)return{ok:false,status:304,headers:headers({ETag:tag})};
      return{ok:true,status:200,headers:headers({ETag:tag}),blob:async()=>({frame})};
    },
    painterFactory:cfg=>createOwnedBitmapPainter({...cfg,decode:async blob=>({name:blob.frame,close(){}})}),
  });
  return{feed,requests,painted,unavailable,setFrame:f=>{frame=f;},setKey:k=>{key=k;}};
}
{
  const f=fixture();
  assert.equal(await f.feed.update(),true);assert.deepEqual(f.painted,['A']);assert.equal(f.requests[0],null);
  for(let i=0;i<5;i++){await f.feed.update();await flush();}
  assert.deepEqual(f.painted,['A'],'unchanged (paused) frame is not decoded or repainted');
  assert.ok(f.requests.slice(1).every(t=>t==='"A"'));assert.deepEqual(f.unavailable,[],'304 is not an unavailable state');
  f.setFrame('B');await f.feed.update();await flush();assert.deepEqual(f.painted,['A','B'],'live play still updates');
  f.feed.invalidate();await f.feed.update();await flush();
  assert.equal(f.requests.at(-1),null,'after invalidate the next request downloads the frame again');assert.deepEqual(f.painted,['A','B','B']);
  f.setKey(null);await f.feed.update();f.setKey('minecraft');await f.feed.update();await flush();
  assert.equal(f.requests.at(-1),null,'an inactive context forgets the validator');
  f.feed.dispose();
  console.log('PASS: Minecraft frames use conditional requests; paused games cost empty 304s, live play repaints, invalidation re-downloads');
}
const res=(status,text,type='text/plain; charset=utf-8')=>({status,headers:headers({'Content-Type':type}),text:async()=>text});
assert.equal(await actionErrorMessage(res(409,'Bathroom privacy is active')),'Bathroom privacy is active');
assert.equal(await actionErrorMessage(res(400,'  Use a public web\n page address ')),'Use a public web page address');
assert.equal(await actionErrorMessage(res(409,'<html><b>x</b></html>','text/html')),null);
assert.equal(await actionErrorMessage(res(409,'<script>alert(1)</script>')),null,'markup never shown');
assert.equal(await actionErrorMessage(res(409,'409: Conflict')),null,'bare default status bodies fall back');
assert.equal(await actionErrorMessage(res(500,'Traceback')),null,'server errors stay generic');
assert.equal((await actionErrorMessage(res(400,'x'.repeat(400)))).length,158);
console.log('PASS: 400/409 reasons shown as bounded plain text; HTML, markup and 5xx fall back');
