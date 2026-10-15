"""Independent binary/channel and same-side capture quaternion verification."""
import bisect,hashlib,json,math,struct,sys
from pathlib import Path

def load(path):
 data=Path(path).read_bytes();assert data[:4]==b'glTF';offset=12;doc=blob=None
 while offset<len(data):
  n,kind=struct.unpack_from('<II',data,offset);chunk=data[offset+8:offset+8+n]
  if kind==0x4e4f534a:doc=json.loads(chunk)
  if kind==0x004e4942:blob=chunk
  offset+=8+n
 return doc,blob,hashlib.sha256(data).hexdigest()
def accessor(doc,blob,index):
 a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];assert not v.get('extensions')and not a.get('sparse')and a['componentType']==5126
 count={'SCALAR':1,'VEC4':4}[a['type']];return [struct.unpack_from('<'+'f'*count,blob,v.get('byteOffset',0)+a.get('byteOffset',0)+i*v.get('byteStride',4*count))for i in range(a['count'])]
def unit(q):
 length=math.sqrt(sum(v*v for v in q));return [v/length for v in q]
def angle(a,b):return 2*math.acos(min(1,abs(sum(x*y for x,y in zip(unit(a),unit(b))))))
def slerp(a,b,t):
 a,b=unit(a),unit(b);dot=sum(x*y for x,y in zip(a,b))
 if dot<0:b=[-v for v in b];dot=-dot
 if dot>.9995:return unit([x+(y-x)*t for x,y in zip(a,b)])
 theta=math.acos(min(1,dot));return [(x*math.sin((1-t)*theta)+y*math.sin(t*theta))/math.sin(theta)for x,y in zip(a,b)]
def prove(body,capture,candidate,output):
 bd,bb,bsha=load(body);sd,sb,ssha=load(capture);nd,nb,nsha=load(candidate)
 assert nb[:len(bb)]==bb and nd['nodes']==bd['nodes']and nd['skins']==bd['skins']and nd['meshes']==bd['meshes']
 assert nd['accessors'][:len(bd['accessors'])]==bd['accessors']and nd['bufferViews'][:len(bd['bufferViews'])]==bd['bufferViews']
 base=bd['animations'][0];new=nd['animations'][0];assert new['channels'][:len(base['channels'])]==base['channels']and new['samplers'][:len(base['samplers'])]==base['samplers']
 source={sd['nodes'][c['target']['node']]['name']:c for c in sd['animations'][0]['channels']if c['target']['path']=='rotation'}
 rows=[];duration=max(accessor(sd,sb,s['input'])[-1][0]for s in sd['animations'][0]['samplers'])
 for ch in new['channels'][len(base['channels']):]:
  name=nd['nodes'][ch['target']['node']]['name'];assert 'Hand'in name and ch['target']['path']=='rotation';sc=source[name];sp=sd['animations'][0]['samplers'][sc['sampler']];st=[r[0]for r in accessor(sd,sb,sp['input'])];sv=accessor(sd,sb,sp['output']);np=new['samplers'][ch['sampler']];nt=[r[0]for r in accessor(nd,nb,np['input'])];nv=accessor(nd,nb,np['output']);maximum=0
  assert len(nt)==len(nv) and all(nt[i]>nt[i-1] for i in range(1,len(nt))),'Non-increasing stored float32 hand times '+name
  for time,q in zip(nt,nv):
   phase=time%duration;hi=min(bisect.bisect_left(st,phase),len(st)-1);lo=hi if st[hi]==phase else max(0,hi-1);alpha=0 if hi==lo else(phase-st[lo])/(st[hi]-st[lo]);maximum=max(maximum,angle(q,slerp(sv[lo],sv[hi],alpha)))
  assert maximum<1e-5,'Capture layer changed same-side bend '+name
  rows.append({'name':name,'source_node':sc['target']['node'],'candidate_node':ch['target']['node'],'frames':len(nt),'max_same_side_capture_quaternion_error_degrees':math.degrees(maximum)})
 assert len(rows)==42 and sum('Left'in r['name']for r in rows)==21 and sum('Right'in r['name']for r in rows)==21
 report={'schema':'sub01.independent-captured-hand-layer.v1','body_sha256':bsha,'capture_sha256':ssha,'candidate_sha256':nsha,'all_original_body_channels_samplers_exact':True,'all_original_owner_binary_nodes_skins_meshes_exact':True,'same_side_capture_quaternion_verified':True,'no_joint_curl_or_mirroring_added':True,'rows':rows,'native_imported':False,'visual_or_contact_accepted':False,'limitation':'Existing source retarget anatomy is evaluated separately in rendered left/right skin; quaternion fidelity alone does not certify anatomy or skin contact.'};Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'channels':len(rows),'max_error_degrees':max(r['max_same_side_capture_quaternion_error_degrees']for r in rows)}))
if __name__=='__main__':prove(*sys.argv[1:])
