'use strict';
// Execute only on Runpod, against the private loopback official viewer.
const { createRequire } = require('node:module');
const fs = require('node:fs');
const req = createRequire('/workspace/sub01-home-private/streaming/PixelStreamingInfrastructure/package.json');
const { chromium } = req('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu', '--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  // Establish pointer position before the viewer registers native input.
  await page.mouse.move(640,360);
  const logs = [];
  page.on('console', m => { if(logs.length < 40) logs.push(m.text().slice(0,300)); });
  page.on('pageerror', e => logs.push('PAGEERROR=' + e.message.slice(0,300)));
  await page.addInitScript(() => {
    window.sub01Peers = [];
    const Original = window.RTCPeerConnection;
    window.RTCPeerConnection = class extends Original {
      constructor(...args) { super(...args); window.sub01Peers.push(this); }
    };
  });
  await page.goto('http://127.0.0.1:8890/?AutoConnect=true&AutoPlayVideo=true&StartVideoMuted=true', {waitUntil:'domcontentloaded',timeout:25000});
  for(let i=0;i<12;i++) {
    const buttons = page.getByText(/click to start|click to play|click to try again|start streaming|connect/i);
    if(await buttons.count()) await buttons.first().click({timeout:1000}).catch(()=>{});
    const ready = await page.evaluate(() => [...document.querySelectorAll('video')].some(v=>v.videoWidth>0 && v.readyState>=2));
    if(ready) break;
    await page.waitForTimeout(2000);
  }
  async function stats() {
    return page.evaluate(async () => {
      const video = document.querySelector('video');
      const reports=[];
      for(const pc of window.sub01Peers || []) {
        const data = await pc.getStats();
        reports.push({state:pc.connectionState, iceState:pc.iceConnectionState, stats:[...data.values()].filter(x=>['inbound-rtp','data-channel','candidate-pair'].includes(x.type)).map(x=>({type:x.type,kind:x.kind,state:x.state,bytesReceived:x.bytesReceived,framesDecoded:x.framesDecoded,packetsReceived:x.packetsReceived,messagesSent:x.messagesSent,messagesReceived:x.messagesReceived,nominated:x.nominated}))});
      }
      return {video:video?{width:video.videoWidth,height:video.videoHeight,currentTime:video.currentTime,readyState:video.readyState,quality:video.getVideoPlaybackQuality()?.totalVideoFrames}:null,reports};
    });
  }
  const before = await stats();
  await page.screenshot({path:'/workspace/sub01-home-private/streaming/local-proof-before.png'});
  if(before.video?.width && before.reports.some(r=>r.stats.some(s=>(s.framesDecoded||0)>0))) {
    await page.mouse.click(640,360);
    await page.keyboard.down('w'); await page.waitForTimeout(1200); await page.keyboard.up('w');
    await page.screenshot({path:'/workspace/sub01-home-private/streaming/local-proof-walk.png'});
    await page.mouse.move(780,360,{steps:12});
    await page.keyboard.press('e');
    await page.waitForTimeout(700);
  }
  const after = await stats();
  await page.screenshot({path:'/workspace/sub01-home-private/streaming/local-proof-after.png'});
  const result = {scope:'Runpod loopback only; authenticated Jupyter route not yet exercised',before,after,console:logs};
  fs.writeFileSync('/workspace/sub01-home-private/streaming/local-proof.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
  await browser.close();
  process.exit(before.reports.some(r=>r.stats.some(s=>(s.framesDecoded||0)>0))?0:2);
})().catch(e=>{console.error('LOCAL_BROWSER_PROOF_ERROR='+e.name+': '+e.message);process.exit(1);});
