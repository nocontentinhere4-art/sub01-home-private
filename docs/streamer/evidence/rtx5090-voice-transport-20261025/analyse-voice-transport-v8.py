"""Bounded post-cleanup full decode and actual waveform verification; timing stays OPEN."""
from pathlib import Path
import hashlib,json,math,os,re,signal,stat,subprocess,sys,time,traceback,wave
if not __debug__ or sys.flags.optimize:raise SystemExit('Optimized Python refused')
START=float(os.environ['SUB01_DIAGNOSTIC_START'])
signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('Offline operation deadline')))
signal.setitimer(signal.ITIMER_REAL,max(.001,START+280-time.monotonic()))
os.sched_setaffinity(0,set(range(6,14)))
B=Path('/home/unreal/.sub01-private/voice-director-diagnostic-v8-20261025/confined')
P=Path('/home/unreal/.sub01-private');S=Path('/tmp/sub01-share');OUT=B/'offline-analysis'
report={'schema':'sub01.voice-transport-analysis.v2','status':'preflight','stage':'preflight','files':[],'commands':[],'input_sha256':{},'timing_available':False,'timing_within_bound':None,'timing_reason':'Recording start UTC is not independently anchored; no index-times-600 mapping accepted.','skin_or_lipsync_accepted':False,'voice_quality_accepted':False}
inputs={};created=False;output_limit=128*1024**2
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()
def pin(path,max_bytes=512*1024**2):
 p=Path(path);st=p.lstat()
 if not stat.S_ISREG(st.st_mode) or st.st_size>max_bytes:raise RuntimeError('Input identity/size')
 digest=sha(p);inputs[str(p)]=digest;report['input_sha256'][str(p)]=digest
 return p
def read_json(path):
 p=pin(path,1048576);data=p.read_bytes()
 if hashlib.sha256(data).hexdigest()!=inputs[str(p)]:raise RuntimeError('Input changed before parse')
 return json.loads(data)
def native():
 r=json.loads((P/'streamer-visual-receipt.json').read_text())
 if (r.get('native_pid'),r.get('native_start_ticks'))!=(29950,53274039) or not 0<=time.time()-r['captured_utc']<3 or not (P/'streamer/STOP').exists() or (S/'MEASURING').exists():raise RuntimeError('Native/STOP/measurement changed')
 if sha(P/'streamer-visual-face-tuning.json')!='561656b00848a851fd75bd3ee34e9f7823527c12e1c70ec992b958e30341337a':raise RuntimeError('P5 changed')
def budget():
 if time.monotonic()>=START+275:raise TimeoutError('Offline budget')
 if os.statvfs('/').f_bavail*os.statvfs('/').f_frsize<10*1024**3:raise RuntimeError('Root reserve')
 if OUT.exists() and sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())>output_limit:raise RuntimeError('Output cap')
 if sum(p.stat().st_size for p in B.parent.rglob('*') if p.is_file())>512*1024**2:raise RuntimeError('Combined artifact cap')
def command(args):
 budget();r=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=min(120,START+275-time.monotonic()))
 if len(r.stdout)>2*1024**2 or len(r.stderr)>1024**2:raise RuntimeError('Command diagnostic cap')
 row={'argv':args,'returncode':r.returncode,'stderr':r.stderr.decode(errors='replace')}
 report['commands'].append(row)
 if r.returncode or r.stderr.strip():raise RuntimeError('Probe/decode error')
 return r.stdout
def waveform(path):
 with wave.open(str(path),'rb')as f:
  if (f.getframerate(),f.getnchannels(),f.getsampwidth())!=(48000,2,2) or not 0<f.getnframes()<=48000*180:raise RuntimeError('PCM format/allocation bound')
  count=f.getnframes();raw=np.frombuffer(f.readframes(count),dtype='<i2').reshape(-1,2)
 return raw,raw.astype(np.float64).mean(axis=1)
def stats(raw):
 x=raw.astype(np.float64)
 return dict(frames=len(raw),seconds=len(raw)/48000,peak=float(np.abs(x).max()),rms=float(np.sqrt(np.mean(x*x))),clipped_fraction=float(np.mean(np.abs(x)>=32767)))
def matched_waveform(audio,source):
 if not np.isfinite(audio).all() or not np.isfinite(source).all() or not len(audio)>=len(source)>0:raise RuntimeError('Waveform inputs')
 source=source-source.mean();energy=float(source@source)
 if energy<=0:raise RuntimeError('Silent source')
 dot=correlate(audio,source,mode='valid',method='fft')
 csum=np.concatenate(([0.],np.cumsum(audio)));squares=np.concatenate(([0.],np.cumsum(audio*audio)));n=len(source)
 sums=csum[n:]-csum[:-n];window=np.maximum(0.,squares[n:]-squares[:-n]-sums*sums/n)
 scores=np.divide(dot,np.sqrt(window*energy),out=np.full_like(dot,-1.),where=window>1e-9)
 at=int(np.argmax(scores));return at,float(np.clip(scores[at],-1.,1.))
try:
 native();capture=read_json(B/'result.json')
 if capture.get('cleanup_complete') is not True or capture.get('status')!='capture-ended-analysis-pending' or OUT.exists():raise RuntimeError('Capture/cleanup/new-analysis precondition')
 ready=read_json(B/'director-ready.json')
 journal=pin(B/'journal.jsonl',16*1024**2);raw=journal.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=inputs[str(journal)]:raise RuntimeError('Journal changed')
 rows=[json.loads(line) for line in raw.splitlines() if line]
 pids={v['pid'] for v in rows if v.get('event')=='child-start'}|{ready['ffmpeg_pid']}
 for pid in pids:
  if Path('/proc/'+str(pid)).exists():raise RuntimeError('Capture process still present; no offline processing')
 protocol=read_json(S/'voice-director-protocol.json')
 timeline_path=pin(B/'voice/speech/timeline.jsonl',1048576);raw=timeline_path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=inputs[str(timeline_path)]:raise RuntimeError('Timeline changed')
 timeline=[json.loads(v) for v in raw.splitlines() if v]
 if len(timeline)!=1 or timeline[0].get('cut') is not False:raise RuntimeError('One uncut utterance required')
 speech=timeline[0]
 if not re.fullmatch(r'[A-Za-z0-9_-]+',speech['id']):raise RuntimeError('Speech ID')
 source_path=pin(B/'voice/speech'/(speech['id']+'.wav'),4*1024**2)
 recordings=sorted((B/'director/recordings').glob('*.mp4'))
 if not 0<len(recordings)<=20 or sum(p.stat().st_size for p in recordings)>512*1024**2:raise RuntimeError('Recording count/size cap')
 for p in recordings:pin(p)
 if sum(p.stat().st_size for p in B.parent.rglob('*') if p.is_file())+180*48000*4+2*1024**2>512*1024**2:raise RuntimeError('Artifact reservation for PCM and final report')
 OUT.mkdir(mode=0o700);created=True;report['status']='analysing';report['stage']='imports'
 import numpy as np
 from scipy.signal import correlate
 source_raw,source=waveform(source_path);report['source']=dict(wav=str(source_path),pcm=stats(source_raw),timeline=speech)
 gates=protocol['offline_gates']
 if not gates['source_wav_duration_min_seconds']<=len(source)/48000<=gates['source_wav_duration_max_seconds']:raise RuntimeError('Source duration')
 allocated=len(source);decoded_count=0
 for index,path in enumerate(recordings):
  report['stage']='decode:'+path.name;budget()
  metadata=json.loads(command(['/usr/bin/ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
  audios=[s for s in metadata['streams'] if s.get('codec_type')=='audio']
  if not audios or not(audios[0].get('codec_name')=='aac' and audios[0].get('channels')==2 and audios[0].get('sample_rate')=='48000'):raise RuntimeError('Actual 0:a:0 native format')
  duration=float(audios[0].get('duration',metadata['format']['duration']))
  if not math.isfinite(duration) or duration<=0 or allocated+math.ceil(duration*48000)+4096>48000*180:raise RuntimeError('Cumulative audio allocation cap')
  command(['/usr/bin/ffmpeg','-v','error','-xerror','-nostdin','-threads','4','-i',str(path),'-f','null','-'])
  wav=OUT/f'audio-{index:02d}.wav'
  command(['/usr/bin/ffmpeg','-v','error','-xerror','-nostdin','-i',str(path),'-map','0:a:0','-ar','48000','-ac','2','-c:a','pcm_s16le','-fs',str((48000*180-allocated)*4+1024),str(wav)])
  if wav.stat().st_size>=(48000*180-allocated)*4-65536:raise RuntimeError('Extraction reached safety cap; reject possible truncation')
  data,audio=waveform(wav);allocated+=len(audio)
  if allocated>48000*180:raise RuntimeError('Cumulative decoded allocation exceeded')
  row=dict(name=path.name,bytes=path.stat().st_size,metadata=metadata,pcm=stats(data),full_decode_error_free=True)
  if len(audio)>=len(source):
   at,score=matched_waveform(audio,source);row.update(normalized_correlation=score,matched_offset_seconds=at/48000)
  report['files'].append(row);decoded_count+=1;del data,audio
  budget()
 best=max(report['files'],key=lambda v:v.get('normalized_correlation',-1))
 report['gates']=dict(all_full_decodes=decoded_count==len(recordings),actual_first_audio_aac_48k_stereo=True,single_uncut_utterance=True,source_duration=True,waveform_transport=best.get('normalized_correlation',-1)>=gates['aac_vs_source_wav_normalized_correlation_min'],decoded_clipping=all(v['pcm']['clipped_fraction']<=gates['decoded_audio_clipped_fraction_max'] for v in report['files']),timing_available=False,timing_within_bound=None)
 report.update(status='waveform-verified-timing-open' if all(v for k,v in report['gates'].items() if not k.startswith('timing')) else 'gates-failed',waveform_transport_pass=all(v for k,v in report['gates'].items() if not k.startswith('timing')),transport_gates_pass=False,best_match=best['name'],cumulative_audio_frames=allocated)
 report['stage']='verify-inputs'
 for name,digest in inputs.items():
  if sha(Path(name))!=digest:raise RuntimeError('Input changed during analysis: '+name)
 native();report['all_input_hashes_reverified']=True;budget()
except BaseException:
 report.update(status='failed',error=traceback.format_exc(),transport_gates_pass=False,waveform_transport_pass=False)
finally:
 # Disarm the worker alarm while serializing its small reserved report.
 # The corrected independent supervisor kills/reaps at296s and exits by300s.
 signal.setitimer(signal.ITIMER_REAL,0)
 report['elapsed']=time.monotonic()-START
 try:encoded=json.dumps(report,indent=2,allow_nan=False)+'\n'
 except (ValueError,TypeError):
  report={'status':'failed','transport_gates_pass':False,'waveform_transport_pass':False,'error':'Nonserializable/nonfinite report','stage':report.get('stage')};encoded=json.dumps(report)+'\n'
 if len(encoded.encode())>524288:
  report={'status':'failed','transport_gates_pass':False,'waveform_transport_pass':False,'error':'Analysis report size cap','stage':report.get('stage')};encoded=json.dumps(report)+'\n'
 reserve=len(encoded.encode())*2
 if created:
  root_size=sum(p.stat().st_size for p in B.parent.rglob('*') if p.is_file())
  output_size=sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
  if root_size+reserve>512*1024**2 or output_size+reserve>output_limit:
   report={'status':'failed','transport_gates_pass':False,'waveform_transport_pass':False,'error':'Final report reservation exhausted'};encoded=json.dumps(report)+'\n'
  else:
   temp=OUT/'result.tmp';temp.write_text(encoded);temp.rename(OUT/'result.json')
 shared=S/'voice-transport-v8-analysis-result.json'
 shared.write_text(encoded);os.chmod(shared,0o600)
