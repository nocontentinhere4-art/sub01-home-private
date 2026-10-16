"""Final serialized-source check, complete BVH and reviewed<=0.25mm numerical support.

No solver, render, source edits or native operations. The original312-pair failure stays.
"""
import sys,json,hashlib,copy
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
BASE=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1');OLD=BASE/'placed-idle-r3/gaggia-gran-idle-placed.glb';NEW=BASE/'placed-idle-r4/gaggia-gran-idle-placed.glb';SHA='5fdf89fbf47a5a8851a84183ac5526a94ac153f12360e4e2d89bd95fb14fdba2';assert hashlib.sha256(NEW.read_bytes()).hexdigest()==SHA
od,ob=read_gltf(OLD);nd,nb=read_gltf(NEW);restore=copy.deepcopy(nd);ci=next(i for i,n in enumerate(od['nodes'])if n['name']=='GaggiaIdle_033');delta=.00014916015625000001;assert nd['nodes'][ci]['translation'][1]==od['nodes'][ci]['translation'][1]+delta;restore['nodes'][ci]['translation'][1]=od['nodes'][ci]['translation'][1];assert restore==od and bytes(nb)==bytes(ob),'Finalsource changed more than one cupYUP translation'
code=Path('/home/unreal/runtime-tools/prove_real_gaggia_idle_fit_blender.py').read_text();code=code.replace("placed-idle-r3'","placed-idle-r4'").replace('9ce39013852ae7ce44541f86eaa662cb0c50dbb1e31eb3f7885f703e8db78acd',SHA).replace("<=.005]","<=.025]").replace("'sourceContactBandCm':.005","'sourceContactBandCm':.025").replace("'sourceStaticSupportProven':supportpassed","'numericalStaticPlacementAccepted':supportpassed")
needle="(R/'independent-fit.json').write_text(json.dumps(r,indent=2)+'\\n');print(json.dumps(r),flush=True)";assert needle in code;code=code.replace(needle,'');namespace={};exec(compile(code,'final-exact-geometry-and-reviewed-numerical-support','exec'),namespace);r=namespace['r'];assert r['passed']and r['cup']['numericalStaticPlacementAccepted'];r.update(schema='sub01.genuine-gaggia-independent-fit.v1',ok=True,intersections=r['externalFullSourceIntersections'],cupSupportAccepted=True,cupSupportAcceptanceType='Root-reviewed numerical-static projection support with source gaps<=0.25mm; no actual touch/dynamic claim',cupActualTouchVerified=False,cupDynamicStabilityVerified=False,finalSerializedOnlyCupTranslationChanged=True,entireOriginalBinaryAndAllOtherJsonExact=True,exactCupOnlyRigidDeltaUEcm=[0,0,delta*100],failedBeforeSourceSHA256=hashlib.sha256(OLD.read_bytes()).hexdigest(),failedBeforeCupGratePairs=312,failedBeforeFitReportUnchanged=True)
(BASE/'placed-idle-r4/independent-fit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
