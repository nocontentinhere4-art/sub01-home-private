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
