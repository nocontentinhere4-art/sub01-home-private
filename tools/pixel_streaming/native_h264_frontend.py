"""Low-latency WebCodecs rendering for independent native H264 access units.

Transport/control/privacy remain the existing viewer. No synthetic scene frames.
"""
H264_JS = r'''
let nativeH264Decoder=null,nativeH264Codec='',nativeH264Generation=-1;
const nativeH264Metadata=new Map(),nativeFrameTimes=[];
function h264ParameterSets(data){
 const starts=[];
 for(let i=0;i+3<data.length;i++){
  if(data[i]===0&&data[i+1]===0&&data[i+2]===1){starts.push(i+3);i+=2;}
  else if(i+4<data.length&&data[i]===0&&data[i+1]===0&&data[i+2]===0&&data[i+3]===1){starts.push(i+4);i+=3;}
 }
 let codec='',pps=false,idr=false;
 for(const start of starts){const type=data[start]&31;
  if(type===7&&start+3<data.length)codec='avc1.'+[data[start+1],data[start+2],data[start+3]].map(v=>v.toString(16).padStart(2,'0')).join('');
  if(type===8)pps=true;if(type===5)idr=true;
 }
 if(!codec||!pps||!idr)throw Error('Independent native H264 frame required');
 return {codec};
}
function closeNativeH264(){
 if(nativeH264Decoder){try{nativeH264Decoder.close();}catch(e){}}
 nativeH264Decoder=null;nativeH264Codec='';nativeH264Generation=-1;nativeH264Metadata.clear();
}
function recordNativeVideoFrame(sequence,captured){
 window.nativeViewerDecodedFrames++;
 window.nativeViewerLastSequence=sequence;window.nativeViewerLastCaptureUtc=captured;
 const now=performance.now();window.nativeViewerLastDecodedAt=now;nativeFrameTimes.push(now);
 while(nativeFrameTimes.length>1&&nativeFrameTimes[0]<now-2000)nativeFrameTimes.shift();
 const elapsed=now-nativeFrameTimes[0];
 if(elapsed>=500){window.nativeViewerDecodedFps=(nativeFrameTimes.length-1)*1000/elapsed;
  const el=document.querySelector('#videoRate');if(el)el.textContent='Video '+window.nativeViewerDecodedFps.toFixed(0)+' FPS';}
 game.hidden=false;empty.hidden=true;
}
async function decodeNativeH264(blob,sequence,captured,generation){
 if(typeof VideoDecoder==='undefined'||typeof EncodedVideoChunk==='undefined')throw Error('This browser needs WebCodecs H264 support');
 const data=new Uint8Array(await blob.arrayBuffer()),{codec}=h264ParameterSets(data);
 if(generation!==streamGeneration||!streaming||!live)return;
 if(!nativeH264Decoder||nativeH264Decoder.state==='closed'||nativeH264Codec!==codec||nativeH264Generation!==generation){
  closeNativeH264();nativeH264Codec=codec;nativeH264Generation=generation;
  nativeH264Decoder=new VideoDecoder({output:frame=>{
   try{
    const meta=nativeH264Metadata.get(frame.timestamp);nativeH264Metadata.delete(frame.timestamp);
    if(!meta||meta.generation!==streamGeneration||!streaming||!live)return;
    if(game.width!==frame.displayWidth)game.width=frame.displayWidth;
    if(game.height!==frame.displayHeight)game.height=frame.displayHeight;
    game.getContext('2d',{alpha:false,desynchronized:true}).drawImage(frame,0,0,game.width,game.height);
    recordNativeVideoFrame(meta.sequence,meta.captured);
   }finally{frame.close();}
  },error:()=>{closeNativeH264();}});
  nativeH264Decoder.configure({codec,optimizeForLatency:true,hardwareAcceleration:'prefer-hardware'});
 }
 // Every packet is an IDR with SPS/PPS, so dropping a congested frame is safe.
 if(nativeH264Decoder.decodeQueueSize>2)return;
 const timestamp=sequence*16667;
 nativeH264Metadata.set(timestamp,{sequence,captured,generation});
 while(nativeH264Metadata.size>32)nativeH264Metadata.delete(nativeH264Metadata.keys().next().value);
 nativeH264Decoder.decode(new EncodedVideoChunk({type:'key',timestamp,data}));
}
'''

DECODE = r'''async function decode(blob,sequence,captured,generation){
 if(blob.type==='video/h264'){await decodeNativeH264(blob,sequence,captured,generation);return;}
 const url=URL.createObjectURL(blob);
 try{
  if(generation!==streamGeneration)return;
  const decoded=new Image();decoded.src=url;await decoded.decode();
  if(generation!==streamGeneration||!streaming||!live)return;
  game.width=decoded.naturalWidth;game.height=decoded.naturalHeight;
  game.getContext('2d',{alpha:false,desynchronized:true}).drawImage(decoded,0,0);
  recordNativeVideoFrame(sequence,captured);
 }finally{URL.revokeObjectURL(url);}
}'''


def h264_html(html):
    old_img='<img id="game" alt="Live first-person view of the home" hidden>'
    start=html.find('async function decode(blob,sequence,captured,generation){')
    end=html.find('\nasync function finite(',start)
    if html.count(old_img)!=1 or start<0 or end<0 or html.count("type:'image/jpeg'")!=1:
        raise ValueError('Exact existing native video/control hooks required')
    html=html.replace(old_img,'<canvas id="game" width="1280" height="720" aria-label="Live first-person view of the home" hidden></canvas>',1)
    start=html.index('async function decode(blob,sequence,captured,generation){')
    end=html.index('\nasync function finite(',start)
    html=html[:start]+H264_JS+'\n'+DECODE+html[end:]
    html=html.replace("type:'image/jpeg'","type:'video/h264'",1)
    html=html.replace("'wss-jpeg'","'wss-h264'",1).replace("'https-jpeg'","'https-h264'",1)
    clear="function clearPixels(){game.hidden=true;game.removeAttribute('src');if(previous){URL.revokeObjectURL(previous);previous=null;}}"
    if html.count(clear)!=1:
        raise ValueError('Exact privacy clear hook required')
    html=html.replace(clear,"function clearPixels(){game.hidden=true;closeNativeH264();game.getContext('2d').clearRect(0,0,game.width,game.height);if(previous){URL.revokeObjectURL(previous);previous=null;}}",1)
    html=html.replace('<span class="help" id="help"','<span class="pill" id="videoRate">Video … FPS</span><span class="help" id="help"',1)
    return html
