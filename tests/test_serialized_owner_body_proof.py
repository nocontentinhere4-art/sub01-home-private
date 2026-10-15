"""Independent preservation proof must detect body changes and finger-weight leaks."""
import json,struct,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]


def write_pair(tmp_path,body_change=False,finger_weight=False):
    chunks=[];views=[];accessors=[]
    def array(values,kind,n):
        offset=sum(map(len,chunks));data=struct.pack('<'+kind*len(values),*values);chunks.append(data);views.append({'buffer':0,'byteOffset':offset,'byteLength':len(data)})
        accessors.append({'bufferView':len(views)-1,'componentType':{'f':5126,'I':5125}[kind],'type':{1:'SCALAR',2:'VEC2',3:'VEC3',4:'VEC4',16:'MAT4'}[n],'count':len(values)//n});return len(accessors)-1
    attrs={'POSITION':array([0,0,0,1,0,0,0,1,0],'f',3),'TEXCOORD_0':array([0,0,1,0,0,1],'f',2),'JOINTS_0':array(([25 if finger_weight else 0,0,0,0])*3,'I',4),'WEIGHTS_0':array([1,0,0,0]*3,'f',4)}
    indices=array([0,1,2],'I',1);ibm=array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]*65,'f',16)
    names=['Body'+str(i)for i in range(25)]+[side+'Hand'+digit+str(i)for side in ['Left','Right']for digit in ['Thumb','Index','Middle','Ring','Pinky']for i in range(1,5)]
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':sum(map(len,chunks))}],'bufferViews':views,'accessors':accessors,'nodes':[{'name':n}for n in names],'skins':[{'joints':list(range(65)),'inverseBindMatrices':ibm}],'meshes':[{'primitives':[{'attributes':attrs,'indices':indices}]}]}
    def save(path,d):
        j=json.dumps(d).encode();j+=b' '*(-len(j)%4);b=b''.join(chunks);path.write_bytes(struct.pack('<IIIII',0x46546c67,2,28+len(j)+len(b),len(j),0x4e4f534a)+j+struct.pack('<II',len(b),0x004e4942)+b)
    before=tmp_path/'before.glb';after=tmp_path/'after.glb';save(before,doc)
    if body_change:doc['nodes'][0]['translation']=[0,.01,0]
    else:doc['nodes'][25]['translation']=[0,.01,0]
    save(after,doc);return before,after


def run(tmp_path,**kwargs):
    a,b=write_pair(tmp_path,**kwargs);out=tmp_path/'proof.json';result=subprocess.run(['node',str(ROOT/'tools/prove_serialized_owner_body_preservation.mjs'),str(a),str(b),str(out)],capture_output=True,text=True);return result,out


def test_exact_body_with_changed_unweighted_fingers_passes(tmp_path):
    result,out=run(tmp_path);assert result.returncode==0,result.stderr
    proof=json.loads(out.read_text());assert proof['retained_original_vertices']==3
    assert proof['retained_original_changed_finger_influences']==0
    assert not proof['native_or_contact_accepted']


@pytest.mark.parametrize('kwargs',[{'body_change':True},{'finger_weight':True}])
def test_body_change_or_retained_finger_skin_dependency_refuses(tmp_path,kwargs):
    result,out=run(tmp_path,**kwargs);assert result.returncode!=0
    assert not out.exists()
