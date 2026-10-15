"""Actual imported node scale and the production C++ extent guard."""
import hashlib
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from tools import unreal_controller_play_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]


def test_actual_controller_source_matches_native_import_scale():
    proof=json.loads((ROOT/'docs/proposed/actual-controller-source-scale-20261015.json').read_text())
    raw=(ROOT/proof['original_source_glb']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==proof['original_source_sha256']
    size,_=struct.unpack_from('<II',raw,12)
    doc=json.loads(raw[20:20+size])
    mesh_index=next(i for i,m in enumerate(doc['meshes']) if m.get('name')=='controller')
    node=next(n for n in doc['nodes'] if n.get('mesh')==mesh_index)
    accessor=doc['accessors'][doc['meshes'][mesh_index]['primitives'][0]['attributes']['POSITION']]
    assert accessor['componentType']==5122 and accessor['normalized'] is True
    local=[max(abs(accessor['min'][i]),abs(accessor['max'][i]))/32767*100 for i in (0,2,1)]
    assert node['scale']==proof['actual_native_import_component_scale']
    expected=proof['actual_native_import_world_extent_cm']
    restored=[value*scale for value,scale in zip(local,node['scale'])]
    assert restored==pytest.approx(expected,abs=1e-6)
    assert local[0]*2==200
    assert restored[0]*2==pytest.approx(15.38021713495)
    assert all(abs(a-b)>.001 for a,b in zip(local,expected))


def test_production_extent_guard_rejects_unit_and_invalid_scale(tmp_path):
    compiler=shutil.which('clang++') or shutil.which('g++')
    if not compiler:pytest.skip('C++ compiler unavailable')
    function=re.search(r'static bool Sub01ControllerPhysicalExtentMatches\([^\n]+\)\{.*?\n\}',runtime.CHARACTER_METHODS,re.S).group()
    proof=json.loads((ROOT/'docs/proposed/actual-controller-source-scale-20261015.json').read_text())
    vec=lambda values:'FVector{{'+','.join(repr(v) for v in values)+'}}'
    source='''#include <cmath>
#include <cassert>
using int32=int;
struct FVector{double V[3];double operator[](int I)const{return V[I];}};
struct FMath{static bool IsFinite(double X){return std::isfinite(X);}static double Abs(double X){return std::abs(X);}};
'''+function+'\nint main(){\n'
    source+='auto Local='+vec(proof['raw_mesh_local_extent_cm_derived_from_actual_import'])+';\n'
    source+='auto Scale='+vec(proof['actual_native_import_component_scale'])+';\n'
    source+='auto Expected='+vec(proof['actual_native_import_world_extent_cm'])+';\n'
    source+='''assert(Sub01ControllerPhysicalExtentMatches(Local,Scale,Expected));
assert(!Sub01ControllerPhysicalExtentMatches(Local,FVector{{1,1,1}},Expected));
for(double Bad:{0.,-1.,double(NAN),double(INFINITY)}){auto S=Scale;S.V[1]=Bad;assert(!Sub01ControllerPhysicalExtentMatches(Local,S,Expected));}
auto Wrong=Expected;Wrong.V[2]+=.01;assert(!Sub01ControllerPhysicalExtentMatches(Local,Scale,Wrong));
}\n'''
    source=source.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
    path=tmp_path/'guard.cpp';path.write_text(source)
    subprocess.run([compiler,'-std=c++17',str(path),'-o',str(tmp_path/'guard')],check=True,capture_output=True)
    subprocess.run([str(tmp_path/'guard')],check=True)
    load=runtime.CHARACTER_METHODS.split('void ASub01HomeCharacter::LoadControllerPlay(){',1)[1].split('void ASub01HomeCharacter::',1)[0]
    assert 'original_source_transform' in load and 'original_source_bounds_cm' in load
    assert load.index('Sub01ControllerPhysicalExtentMatches(Prop->GetBounds()')<load.index('NewObject<UStaticMeshComponent>')
    assert 'ControllerPlayProp->SetWorldScale3D(PropScale)' in load
    assert 'ControllerPlayProp->SetWorldScale3D(FVector' not in load


def test_production_mount_preserves_original_source_node_frame(tmp_path):
    import itertools
    from tools.unreal_controller_play_runtime import ue_grip
    from tools import unreal_derived_controller_visual_review as review
    compiler=shutil.which('clang++') or shutil.which('g++')
    if not compiler:pytest.skip('C++ compiler unavailable')
    proof=json.loads((ROOT/'docs/proposed/actual-controller-source-scale-20261015.json').read_text())
    raw=(ROOT/proof['original_source_glb']).read_bytes();size,_=struct.unpack_from('<II',raw,12);doc=json.loads(raw[20:20+size])
    index=next(i for i,m in enumerate(doc['meshes'])if m.get('name')=='controller')
    node=next(n for n in doc['nodes']if n.get('mesh')==index)
    accessor=doc['accessors'][doc['meshes'][index]['primitives'][0]['attributes']['POSITION']]
    offset=proof['actual_native_import_component_translation_cm']
    assert offset==[node['translation'][i]*100 for i in (0,2,1)]
    assert proof['actual_native_import_component_quaternion']==[0,0,0,1]
    report=json.loads((ROOT/'docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json').read_text())
    grip=report['fixed_offset']['controller_in_right_hand_gltf'];position,rotation=ue_grip(grip)
    function=re.search(r'static FVector Sub01ControllerSourceMountPosition\([^\n]+\)\{.*?\n\}',runtime.CHARACTER_METHODS,re.S).group()
    vec=lambda a:'FVector('+','.join(repr(x)for x in a)+')'
    source='''#include <cassert>
#include <cmath>
struct FVector{double X,Y,Z;FVector(double A,double B,double C):X(A),Y(B),Z(C){};FVector operator+(const FVector&B)const{return {X+B.X,Y+B.Y,Z+B.Z};}};
struct FQuat{double X,Y,Z,W;FVector RotateVector(const FVector&V)const{double T[3]={2*(Y*V.Z-Z*V.Y),2*(Z*V.X-X*V.Z),2*(X*V.Y-Y*V.X)};return {V.X+W*T[0]+Y*T[2]-Z*T[1],V.Y+W*T[1]+Z*T[0]-X*T[2],V.Z+W*T[2]+X*T[1]-Y*T[0]};}};
'''+function+'\nint main(){\n'
    source+='const auto P='+vec(position)+';const FQuat Q{'+','.join(repr(x)for x in rotation)+'};\n'
    source+='const auto Mount=Sub01ControllerSourceMountPosition(P,Q,'+vec(offset)+');\n'
    for point in itertools.product(*[(lo/32767,hi/32767)for lo,hi in zip(accessor['min'],accessor['max'])]):
        authored=[node['translation'][i]+node['scale'][i]*point[i]for i in range(3)]
        target=[sum(grip[i][j]*authored[j]for j in range(3))+grip[i][3]for i in range(3)]
        expected=[target[i]*100 for i in (0,2,1)]
        scaled=[point[i]*node['scale'][i]*100 for i in (0,2,1)]
        source+='{const auto V=Q.RotateVector('+vec(scaled)+');const auto A=Mount+V;const auto Old=P+V;const auto E='+vec(expected)+';'
        source+='assert(std::abs(A.X-E.X)<1.e-10&&std::abs(A.Y-E.Y)<1.e-10&&std::abs(A.Z-E.Z)<1.e-10);'
        source+='assert(std::sqrt((Old.X-E.X)*(Old.X-E.X)+(Old.Y-E.Y)*(Old.Y-E.Y)+(Old.Z-E.Z)*(Old.Z-E.Z))>2.79);}\n'
    source+='}\n';path=tmp_path/'mount.cpp';path.write_text(source)
    subprocess.run([compiler,'-std=c++17',str(path),'-o',str(tmp_path/'mount')],check=True,capture_output=True)
    subprocess.run([str(tmp_path/'mount')],check=True)
    assert 'Sub01ControllerSourceMountPosition(GripPosition,GripRotation,ControllerPlaySourceOffset)' in runtime.CHARACTER_METHODS
    assert 'GripRotation*ControllerPlaySourceRotation' in runtime.CHARACTER_METHODS
    assert 'Sub01ControllerSourceMountPosition(P,R,ControllerPlaySourceOffset)' in review.METHODS
    assert 'R*ControllerPlaySourceRotation' in review.METHODS
