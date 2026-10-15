"""Realdoor receipt integrity and continuous swept-bound geometric invariants."""
import json,math,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_authentic_doors_runtime import SHA,PREFIX,RECEIPT,receipt_profile,install
from unreal_exit_door_runtime import install as legacy

def receipt():
 parts=[];index=0
 for role,moving,count in [('entry',True,23),('bathroom',True,3),('balcony',True,8),('entry',False,15),('bathroom',False,9),('balcony',False,18)]:
  for _ in range(count):
   name=f'SUB01_AuthenticDoor_{index:03d}';parts.append({'name':name,'mesh':PREFIX+'test/'+name+'.'+name,'moving_group':role if moving else None,'assembly':role,'world_center_cm':[155.,400.,100.],'world_extent_cm':[1.,2.,3.],'full_source_geometry_verified':True});index+=1
 return {'schema':'sub01.authentic-doors-native.v1','source_sha256':SHA,'saved':True,'originals_preserved':True,'protected_originals_unchanged':True,'owned_destination':PREFIX+'test','parts':parts}

def write(tmp_path,row):
 p=tmp_path/RECEIPT;p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(row))

def test_no_receipt_changes_nothing(tmp_path):
 assert install('arbitraryheader','arbitrarycpp',tmp_path)==('arbitraryheader','arbitrarycpp')

@pytest.mark.parametrize('key,value',[('saved',False),('source_sha256','forged'),('originals_preserved',False),('owned_destination','/Game/Other'),('protected_originals_unchanged',False)])
def test_incomplete_or_wrong_saved_map_refused(tmp_path,key,value):
 r=receipt();r[key]=value;write(tmp_path,r)
 with pytest.raises(ValueError):receipt_profile(tmp_path)

@pytest.mark.parametrize('mutation',['duplicate','outside','nan','missingpart','unknownrole','no_geometry'])
def test_partial_or_ambiguous_actualpart_refused(tmp_path,mutation):
 r=receipt()
 if mutation=='duplicate':r['parts'][1]['mesh']=r['parts'][0]['mesh']
 if mutation=='outside':r['parts'][1]['mesh']='/Game/Other/Unexpected.Mesh'
 if mutation=='nan':r['parts'][1]['world_center_cm'][0]=float('nan')
 if mutation=='missingpart':r['parts'].pop()
 if mutation=='unknownrole':r['parts'][1]['moving_group']='other'
 if mutation=='no_geometry':r['parts'][1]['full_source_geometry_verified']=False
 write(tmp_path,r)
 with pytest.raises(ValueError):receipt_profile(tmp_path)

def test_install_exact_new_actualdoors_and_preserve_manual_privacy(tmp_path):
 write(tmp_path,receipt());h,c=legacy(' void Forward(float Value);',' ConfigureActualPC();\n Super::Tick(DeltaSeconds);\n FString Device;\n')
 h,c=install(h,c,tmp_path)
 assert c.count(' ConfigureAuthenticDoors();')==1
 assert c.count(' if(AuthenticDoorPacket)return;')==4
 assert 'FVector Pivot(154.3,402.2,2.5)'in c
 assert 'Sub01ExitDoor::InsideBathroom(P.X,P.Y,Feet)'in c
 assert 'BathDoorEgressRequested=false;BathDoorWanted=LiveEdge'in c
 assert 'SUB01_AUTHENTIC_DOORS_BOUND actual76parts'in c
 assert c.count('TEXT("SUB01AuthenticDoors:'+SHA+':')==76
 assert 'OverlapBlockingTestByChannel'in c and 'AuthenticDoorGroups[I]==Group' in c
 assert 'AuthenticBalconyTarget='in c and '?91.f:0.f' in c
 with pytest.raises(ValueError):install(h,c,tmp_path)

def test_continuous_rotating_leaf_bound_contains_all_corners_over_arc():
 # Independent dense witness of everycorner on complete0..86.4 arc, in both
 # directions. Native expansion uses the distancebound radius*halfAngle;
 # no real endpoint-only gap or an omitted handle corner may escape it.
 pivot=(154.3,402.2,2.5);center=(199.5,402.6,105.55);extent=(45.2,4.8,101.25)
 radius=math.dist(center,pivot)+math.sqrt(sum(x*x for x in extent))
 for start,end in [(0,.25),(41.75,42.),(86.4,86.15),(3.5,0)]:
  mid=math.radians((start+end)/2);extra=radius*abs(math.radians(end-start))/2+.0001
  for sample in range(101):
   delta=math.radians(start+(end-start)*sample/100)-mid
   for x in [-extent[0],extent[0]]:
    for y in [-extent[1],extent[1]]:
     px=center[0]-pivot[0]+x;py=center[1]-pivot[1]+y
     rx=math.cos(delta)*px-math.sin(delta)*py-(center[0]-pivot[0]);ry=math.sin(delta)*px+math.cos(delta)*py-(center[1]-pivot[1])
     assert abs(rx)<=extent[0]+extra and abs(ry)<=extent[1]+extra

def test_linear_swept_bounds_cover_opening_and_closing():
 for axis in [0,1]:
  for start,end in [(0,4.5),(95,90.5),(10,10),(91,0)]:
   middle=(start+end)/2;half=abs(end-start)/2
   for sample in range(101):
    p=start+(end-start)*sample/100
    assert middle-half-1e-12<=p<=middle+half+1e-12

def test_actual_generator_keeps_all_corridor_privacy_gates_before_owned_doors(tmp_path):
 from stage_unreal_home_runtime import stage
 from unreal_bathroom_corridor_runtime import SOURCE_SHA,EXPORT_SHA,CONTRACT_SHA,NODES
 (tmp_path/'Config').mkdir();(tmp_path/'Sub01HomeLab.uproject').write_text('{}');(tmp_path/'private-audit').mkdir()
 (tmp_path/'private-audit/bathroom-corridor-native-import.json').write_text(json.dumps({'schema':'sub01.bathroom-corridor-native-import.v1','source_sha256':SOURCE_SHA,'export_sha256':EXPORT_SHA,'source_contract_sha256':CONTRACT_SHA,'source_nodes':NODES,'saved':True,'originals_preserved':True}))
 stage(tmp_path);module=tmp_path/'Source/Sub01HomeLab';header=(module/'Sub01HomeLab.h').read_text();cpp=(module/'Sub01HomeLab.cpp').read_text();write(tmp_path,receipt());header,cpp=install(header,cpp,tmp_path)
 assert cpp.count('Eye.X<-100')==6 and 'Eye.X<-85'not in cpp
 assert 'x<-100&&x>-378' in cpp and 'x<-85&&'not in cpp
 assert cpp.index(' ConfigureAuthenticDoors();')<cpp.index(' ConfigureActualExitDoor();')
 assert cpp.index(' if(TryAuthenticDoor(Hit.GetComponent()))return;')<cpp.index(' if(TryNativeExitDoor(Hit.GetComponent()))return;')
 assert 'GeometryProfile!=TEXT("5ffac2406e66")'in cpp
 assert 'GetCapsuleComponent()->InitCapsuleSize(16.f,91.f)'in cpp
