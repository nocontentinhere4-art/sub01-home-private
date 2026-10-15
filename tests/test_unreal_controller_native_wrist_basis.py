"""Production mount composed with the actual native/source phase-paired evidence."""
import itertools
import json
import re
import shutil
import subprocess
from pathlib import Path
import pytest
from tools import unreal_controller_play_runtime as runtime
from tools import unreal_derived_controller_visual_review as review
ROOT=Path(__file__).resolve().parents[1]


def test_actual_native_phases_preserve_source_controller_corners(tmp_path):
    compiler=shutil.which('clang++')or shutil.which('g++')
    if not compiler:pytest.skip('C++ compiler unavailable')
    proof=json.loads((ROOT/'docs/proposed/controller-native-wrist-basis-samples-20261015.json').read_text())
    assert len(proof['samples'])==201 and len({r[0]for r in proof['samples']})==66
    assert proof['source_sha256']=='bf31d64518d85f6eefd8150009a758ddddc95ca6afd63d5d83bdf29a2dcdaaf9'
    grip=json.loads((ROOT/'docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json').read_text())['fixed_offset']['controller_in_right_hand_gltf']
    position,rotation=runtime.ue_grip(grip)
    physical=json.loads((ROOT/'docs/proposed/actual-controller-source-scale-20261015.json').read_text())
    offset=physical['actual_native_import_component_translation_cm'];extent=physical['actual_native_import_world_extent_cm']
    function=re.search(r'static FQuat Sub01ControllerSourceHandFrameRotation\([^\n]+\)\{.*?\n\}',runtime.CHARACTER_METHODS,re.S).group()
    mount=re.search(r'static FVector Sub01ControllerSourceMountPosition\([^\n]+\)\{.*?\n\}',runtime.CHARACTER_METHODS,re.S).group()
    v=lambda a:'V{'+','.join(map(repr,a))+'}'
    q=lambda a:'Q{'+','.join(map(repr,a))+'}'
    code=r'''#include <cmath>
#include <iostream>
#include <algorithm>
struct V{double X,Y,Z;V operator+(const V&B)const{return{X+B.X,Y+B.Y,Z+B.Z};}};
struct Q{double X,Y,Z,W;Q(double A,double B,double C,double D):X(A),Y(B),Z(C),W(D){};
Q operator*(const Q&B)const{return{W*B.X+X*B.W+Y*B.Z-Z*B.Y,W*B.Y-X*B.Z+Y*B.W+Z*B.X,W*B.Z+X*B.Y-Y*B.X+Z*B.W,W*B.W-X*B.X-Y*B.Y-Z*B.Z};}
V RotateVector(const V&V0)const{double T[3]={2*(Y*V0.Z-Z*V0.Y),2*(Z*V0.X-X*V0.Z),2*(X*V0.Y-Y*V0.X)};return{V0.X+W*T[0]+Y*T[2]-Z*T[1],V0.Y+W*T[1]+Z*T[0]-X*T[2],V0.Z+W*T[2]+X*T[1]-Y*T[0]};}};
using FVector=V;using FQuat=Q;
double distance(const V&A,const V&B){return std::sqrt((A.X-B.X)*(A.X-B.X)+(A.Y-B.Y)*(A.Y-B.Y)+(A.Z-B.Z)*(A.Z-B.Z));}
'''+function+'\n'+mount+'\nint main(){double maximum=0,oldMaximum=0;\n'
    code+='const V Offset='+v(offset)+',GripT='+v(position)+';const Q GripQ='+q(rotation)+';\n'
    for _,np,nq,sp,sq in proof['samples']:
        code+='{const V NativeP='+v(np)+',SourceP='+v(sp)+';const Q NativeQ='+q(nq)+',SourceQ='+q(sq)+';'
        code+='const Q R=Sub01ControllerSourceHandFrameRotation(NativeQ),A=R*GripQ,E=SourceQ*GripQ,O=NativeQ*GripQ;const V P=NativeP+R.RotateVector(GripT),EP=SourceP+SourceQ.RotateVector(GripT),OP=NativeP+NativeQ.RotateVector(GripT);\n'
        for signs in itertools.product((-1,1),repeat=3):
            corner=[x*y for x,y in zip(extent,signs)]
            code+='{const V Corner='+v(corner)+';const V Actual=Sub01ControllerSourceMountPosition(P,A,Offset)+A.RotateVector(Corner),Expected=Sub01ControllerSourceMountPosition(EP,E,Offset)+E.RotateVector(Corner),Old=Sub01ControllerSourceMountPosition(OP,O,Offset)+O.RotateVector(Corner);maximum=std::max(maximum,distance(Actual,Expected));oldMaximum=std::max(oldMaximum,distance(Old,Expected));}\n'
        code+='}\n'
    code+='std::cout<<maximum<<" "<<oldMaximum;}'
    file=tmp_path/'basis.cpp';file.write_text(code)
    subprocess.run([compiler,'-std=c++17',str(file),'-o',str(tmp_path/'basis')],check=True,capture_output=True)
    values=subprocess.check_output([str(tmp_path/'basis')],text=True).split();new,old=map(float,values)
    assert new<.05 # half-mm witness bound includes native time rounded to .001s; no contact tolerance changed
    assert old>10
    assert 'Sub01ControllerSourceHandFrameRotation(W.GetRotation().GetNormalized())'in runtime.CHARACTER_METHODS
    assert 'Sub01ControllerSourceHandFrameRotation(W.GetRotation().GetNormalized())'in review.METHODS
