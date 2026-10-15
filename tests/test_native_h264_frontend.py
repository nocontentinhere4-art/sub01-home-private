import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/pixel_streaming'))
from native_h264_frontend import H264_JS,h264_html
import native_live_viewer as viewer


def test_generated_player_keeps_controls_and_privacy_and_changes_only_video():
 page=h264_html(viewer.HTML)
 assert '<canvas id="game"'in page and "type:'video/h264'"in page
 assert 'requestPointerLock()'in page and 'acknowledgeNativeSocketInput(ws,e.data)'in page
 assert 'nativeH264Metadata.clear()'in page and 'function clearPixels(){game.hidden=true;closeNativeH264();'in page
 assert 'streamGeneration' in page and 'Video … FPS' in page
 assert '<img id="game"'not in page


def test_actual_decoder_wrapper_checks_packet_identity_and_discards_private_generation(tmp_path):
 script='''const vm=require('node:vm'),assert=require('node:assert/strict');
let output,draws=0,closed=0;
const ctx={window:{nativeViewerDecodedFrames:0},performance:{now:()=>1000},
 document:{querySelector:()=>({})},streamGeneration:1,streaming:true,live:true,
 game:{width:1280,height:720,getContext:()=>({drawImage:()=>draws++})},empty:{},
 EncodedVideoChunk:class{constructor(x){Object.assign(this,x)}},
 VideoDecoder:class{constructor(x){output=x.output;this.state='configured';this.decodeQueueSize=0}
 configure(x){assert.equal(x.codec,'avc1.640020');assert.equal(x.optimizeForLatency,true)}
 decode(x){this.last=x}close(){this.state='closed'}}};
vm.createContext(ctx);vm.runInContext(SOURCE,ctx);
const au=new Uint8Array([0,0,0,1,9,240,0,0,1,103,100,0,32,0,0,1,104,1,0,0,1,101,99]);
assert.equal(ctx.h264ParameterSets(au).codec,'avc1.640020');
assert.throws(()=>ctx.h264ParameterSets(new Uint8Array([0,0,1,65,1])));
(async()=>{
 await ctx.decodeNativeH264({arrayBuffer:async()=>au.buffer},10,100,1);
 output({timestamp:10*16667,displayWidth:1280,displayHeight:720,close:()=>closed++});
 assert.equal(draws,1);assert.equal(closed,1);assert.equal(ctx.window.nativeViewerDecodedFrames,1);
 await ctx.decodeNativeH264({arrayBuffer:async()=>au.buffer},11,100,1);
 ctx.streamGeneration=2;ctx.live=false;
 output({timestamp:11*16667,displayWidth:1280,displayHeight:720,close:()=>closed++});
 assert.equal(draws,1);assert.equal(closed,2);
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('SOURCE',json.dumps(H264_JS))
 p=tmp_path/'h264-wrapper.cjs';p.write_text(script)
 r=subprocess.run(['node',str(p)],capture_output=True,text=True)
 assert r.returncode==0,r.stderr


def test_h264_viewer_reports_actual_transport_codec():
    from tools.pixel_streaming.native_h264_frontend import h264_html
    from tools.pixel_streaming.native_live_viewer import HTML
    actual=h264_html(HTML)
    assert "'wss-h264'"in actual and "'https-h264'"in actual
    assert "'wss-jpeg'"not in actual and "'https-jpeg'"not in actual
    assert "'wss-jpeg'"in HTML
