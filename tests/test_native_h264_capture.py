import importlib.util
from pathlib import Path
import struct
import pytest

P=Path(__file__).resolve().parents[1]/'tools/pixel_streaming/native_h264_capture.py'
spec=importlib.util.spec_from_file_location('native_h264_capture',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def nal(kind,payload=b'x',prefix=b'\0\0\0\1'):return prefix+bytes([kind])+payload

def stream():
 return nal(9)+nal(7,b'sps')+nal(8,b'pps')+nal(6,b'sei')+nal(5,b'first')+nal(9,prefix=b'\0\0\1')+nal(5,b'second')+nal(9)+nal(5,b'third')

@pytest.mark.parametrize('chunk_size',[1,2,3,4,7,16,65536])
def test_arbitrary_chunks_emit_independent_complete_idr_units(chunk_size):
 parser=m.AnnexBAccessUnits();data=stream();out=[]
 for i in range(0,len(data),chunk_size):out+=parser.feed(data[i:i+chunk_size])
 out+=parser.finish()
 assert len(out)==3
 for frame in out:
  types=[frame[x.end()]&31 for x in m._START.finditer(frame)]
  assert types[:3]==[9,7,8] and 5 in types and not any(x in(1,2,3,4)for x in types)
 assert b'first'in out[0] and b'second'not in out[0] and b'second'in out[1]
 assert out[1].count(b'sps')==1 and out[1].count(b'pps')==1

def test_latest_drop_and_existing_16_byte_packet_header_are_safe():
 p=m.AnnexBAccessUnits();out=p.feed(stream())+p.finish();latest=out[-1]
 wire=struct.pack('!Qd',17,1234.5)+latest
 assert struct.unpack('!Qd',wire[:16])==(17,1234.5)
 q=m.AnnexBAccessUnits();assert q.feed(wire[16:])+q.finish()==[latest]

@pytest.mark.parametrize('data',[nal(9)+nal(5),nal(5),nal(9)+nal(7)+nal(8)+nal(1),b'garbage'+nal(9),nal(9)+nal(7)+nal(8)+nal(0x85)])
def test_predictive_or_unframed_or_missing_headers_refused(data):
 p=m.AnnexBAccessUnits()
 with pytest.raises(ValueError):p.feed(data);p.finish()

def test_memory_bound_refuses_oversized_nal_and_unit():
 p=m.AnnexBAccessUnits(limit=128)
 with pytest.raises(ValueError):p.feed(nal(9)+nal(7)+nal(8)+nal(5,b'x'*300))

def test_actual_encoder_args_disable_interframe_dependencies_and_queueing():
 args=m.capture_command(60,1280)
 for flag,value in [('-c:v','h264_nvenc'),('-g','1'),('-bf','0'),('-rc-lookahead','0'),('-tune','ull'),('-aud','1'),('-framerate','60'),('-rc','cbr'),('-b:v','12M'),('-bufsize','2M'),('-bsf:v','dump_extra=freq=keyframe')]:assert args[args.index(flag)+1]==value
 assert args[-3:]==['-f','h264','pipe:1']
 with pytest.raises(ValueError):m.capture_command(120,1280)

@pytest.mark.parametrize('codec,mime',[('jpeg','image/jpeg'),('h264_nvenc','video/h264')])
def test_actual_http_frame_contract_and_capture_gate_unchanged(codec,mime):
 import sys,threading,urllib.request,urllib.error
 from types import SimpleNamespace
 from http.server import ThreadingHTTPServer
 sys.path.insert(0,str(P.parent))
 import native_live_viewer as viewer
 allowed=[True]
 state=SimpleNamespace(codec=codec,condition=threading.Condition(),sequence=1,latest_frame=b'actual-packet',capture_utc=123.5,frames=0,enabled=lambda name:allowed[0],ensure_capture=lambda:None)
 server=ThreadingHTTPServer(('127.0.0.1',0),viewer.Handler);server.state=state
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 try:
  url=f'http://127.0.0.1:{server.server_port}/frame.jpg?after=0'
  with urllib.request.urlopen(url,timeout=2)as response:
   assert response.headers['Content-Type']==mime
   assert response.headers['X-Native-Sequence']=='1'
   assert response.read()==b'actual-packet'
  allowed[0]=False
  with pytest.raises(urllib.error.HTTPError)as error:urllib.request.urlopen(url,timeout=2)
  assert error.value.code==409 and state.frames==1
 finally:server.shutdown();server.server_close();worker.join(timeout=2)


def test_default_capture_remains_jpeg_and_unsupported_codec_refuses():
 import sys
 sys.path.insert(0,str(P.parent))
 import native_live_viewer as viewer
 assert viewer.LiveState(9999999999).codec=='jpeg'
 with pytest.raises(ValueError):viewer.LiveState(9999999999,codec='unknown')
