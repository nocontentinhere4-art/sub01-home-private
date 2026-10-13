'use strict';
// Run only on the authorized Runpod. Record the actual incoming native UE stream.
const fs=require('node:fs');
const {createRequire}=require('node:module');
const req=createRequire('/workspace/sub01-home-private/streaming/PixelStreamingInfrastructure/package.json');
const {chromium}=req('playwright');
const output='/workspace/sub01-home-private/streaming';
const token=fs.readFileSync('/workspace/sub01-home-private/pc-bridge/operator-token','utf8').trim();
const marker='SUB01_NATIVE_KEYBOARD_REAL_'+Date.now();
async function state(){const r=await fetch('http://127.0.0.1:8798/pc/state',{headers:{'X-Admin-Token':token}});if(!r.ok)throw new Error('PrivatePCStateUnavailable');return r.json();}
let browser;
(async()=>{
 if(Date.now()>=Date.parse('2026-10-13T18:16:00Z'))throw new Error('BudgetDeadlineEnded');
 browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1280,height:720}});
 await page.mouse.move(640,360); // Before registration; avoids an initial native look jump.
 await page.addInitScript(()=>{window.sub01Peers=[];const Original=window.RTCPeerConnection;window.RTCPeerConnection=class extends Original{constructor(...a){super(...a);window.sub01Peers.push(this);}};});
 await page.goto('http://127.0.0.1:8890/?AutoConnect=true&AutoPlayVideo=true&StartVideoMuted=true',{waitUntil:'domcontentloaded',timeout:25000});
 let ready=false;
 for(let i=0;i<50;i++){
  ready=await page.evaluate(()=>[...document.querySelectorAll('video')].some(v=>v.videoWidth>0&&v.readyState>=2));if(ready)break;
  const overlay=page.getByText(/click to start|click to play|click to try again/i);if(await overlay.count())await overlay.first().click({timeout:1000}).catch(()=>{});
  await page.waitForTimeout(1500);
 }
 if(!ready)throw new Error('ActualNativeVideoNotReady');
 await page.waitForTimeout(3000); // Native PC authentication/privacy synchronization.
 const before=await state();if(!before.ready||before.privacy)throw new Error('PrivatePCNotReady');
 await page.screenshot({path:output+'/native-hands-pc-before.png'});
 const rtcStart=await page.evaluate(async()=>{const rows=[];for(const pc of window.sub01Peers){const s=await pc.getStats();for(const x of s.values())if(x.type==='inbound-rtp'&&x.kind==='video')rows.push({id:x.id,framesDecoded:x.framesDecoded,timestamp:x.timestamp});}return rows;});
 const recordStarted=Date.now();
 const codec=await page.evaluate(()=>{
  const video=document.querySelector('video');
  if(!video?.srcObject)throw new Error('NoActualNativeMediaStream');
  const mime=['video/webm;codecs=vp8,opus','video/webm;codecs=vp8','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));
  if(!mime)throw new Error('BrowserRecorderCodecUnavailable');
  window.sub01RecordingChunks=[];window.sub01Recorder=new MediaRecorder(video.srcObject,{mimeType:mime,videoBitsPerSecond:4000000});
  window.sub01Recorder.ondataavailable=e=>{if(e.data.size)window.sub01RecordingChunks.push(e.data);};
  window.sub01Recorder.start(1000);return mime;
 });
 // These are actual browser keyboard events through the official WebRTC channel.
 await page.keyboard.press('e');await page.waitForTimeout(800);
 for(const c of 'echo '+marker+'; uname -m'){
  if(/[A-Z]/.test(c))await page.keyboard.press('Shift+'+c,{delay:65});
  else if(c==='_')await page.keyboard.press('Shift+Minus',{delay:65});
  else if(c===' ')await page.keyboard.press('Space',{delay:65});
  else await page.keyboard.press(c,{delay:65});
 }
 await page.screenshot({path:output+'/native-hands-pc-typing.png'});
 await page.keyboard.press('Enter');
 let commandObserved=false,after;
 for(let i=0;i<12;i++){
  await page.waitForTimeout(600);after=await state();
  const lines=(after.output||'').replace(/\r/g,'').split('\n');
  if(!after.privacy&&lines.includes(marker)&&lines.includes('i686')){commandObserved=true;break;}
 }
 await page.screenshot({path:output+'/native-hands-pc-after.png'});
 // Hold the real viewport so the complete clip is 12–20 seconds.
 await page.waitForTimeout(commandObserved?7500:2500);
 const recording=await page.evaluate(async()=>{
  const done=new Promise(resolve=>window.sub01Recorder.onstop=resolve);window.sub01Recorder.stop();await done;
  const blob=new Blob(window.sub01RecordingChunks,{type:window.sub01Recorder.mimeType});const data=new Uint8Array(await blob.arrayBuffer());
  let binary='';for(let i=0;i<data.length;i+=32768)binary+=String.fromCharCode(...data.subarray(i,i+32768));
  return btoa(binary);
 });
 fs.writeFileSync(output+'/native-hands-pc-actual.webm',Buffer.from(recording,'base64'));
 const rtc=await page.evaluate(async()=>{const reports=[];for(const pc of window.sub01Peers){const s=await pc.getStats();reports.push({state:pc.connectionState,ice:pc.iceConnectionState,video:[...s.values()].filter(x=>x.type==='inbound-rtp'&&x.kind==='video').map(x=>({id:x.id,timestamp:x.timestamp,framesDecoded:x.framesDecoded,framesPerSecond:x.framesPerSecond,bytesReceived:x.bytesReceived})),channels:[...s.values()].filter(x=>x.type==='data-channel').map(x=>({state:x.state,messagesSent:x.messagesSent}))});}return reports;});
 const proof={scope:'Actual UE PixelStreaming2 same-server private-loopback native viewport and real browser keyboard; no external viewer proof',marker,commandObserved,guestArchitecture:'i686',nativeMediaRecorderCodec:codec,rtc,recordingBytes:fs.statSync(output+'/native-hands-pc-actual.webm').size,rtcStart,recordElapsedSeconds:(Date.now()-recordStarted)/1000,poseScope:'Genuine source skeletal typing clip running as private pose diagnostic; not autonomous brain activity'};
 fs.writeFileSync(output+'/native-hands-pc-browser-proof.json',JSON.stringify(proof,null,2));console.log(JSON.stringify(proof));
 await page.keyboard.press('Escape');await browser.close();process.exit(commandObserved?0:2);
})().catch(async e=>{if(browser)await browser.close().catch(()=>{});console.error('NATIVE_PC_BROWSER_RECORD_ERROR='+e.name+': '+e.message.replace(/https?:\/\/\S+/g,'[private endpoint]'));process.exit(1);});
