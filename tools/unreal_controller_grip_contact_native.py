"""Native per-frame hand-skin vs socket-attached controller contact analyzer (additive install; probe only).

The controller adapter's ControllerPlayReady() needs root's NATIVE runtime proof
(private-audit/native-controller-play-runtime-proof.json, tools/unreal_controller_play_runtime.py
validate_runtime_proof). No native analyzer measured the owner's hand skin against the controller mesh; this adds one
static UFUNCTION next to the renderer's AnalyzeCapturedSeatSkin (tools/unreal_skin_contact_native.py, reused as the
template: same imported-model LBS, same weight shares) and changes nothing else:

    AnalyzeCapturedControllerGrip(Mesh, ComponentPose, BodyWorld, GripBone, GripOffset, GripRotation,
                                  ControllerLocalTriangles, BandLowCm, BandHighCm, MarginCm) -> JSON

* The controller is placed EXACTLY as the controller adapter places its prop: GripBone socket location + socket
  rotation (normalized; imported bone scale excluded) * evidence grip offset/rotation.
* Per hand ("left"/"right"), fixed bind-space sets mirroring tools/fit_controller_grip.py Hands.from_owner:
  hand = weight share of <Side>Hand + its finger joints >= .5; palm = share of <Side>Hand >= .5 AND bind normal . palm
  normal >= .5, the palm normal being cross(Middle1 - Hand, Index1 - Pinky1) oriented toward the Thumb3 side (the
  property fit_controller_grip.py asserts).
* Signed distance to the posed controller triangles: exact point-triangle distance, negative inside by the
  generalized winding number (|w| > .5; the controller has open lathe caps). MarginCm only culls far vertices
  (their distance is not needed: a far palm cannot be in a +-0.3 cm band); it never changes a pass/fail.
Output per hand: palmVertices, palmNearVertices, palmBandVertices, palmMinGapCm, handVertices, handNearVertices,
handPenetratingVertices (signed < BandLowCm), handMinSignedCm. tools/native_support_contact_evidence.py gates it.

    python3 tools/unreal_controller_grip_contact_native.py install <project>/Source/Sub01HomeLab [--dry-run]

Install AFTER root's stage (and after tools/install_native_adapters_bundle.py, which does not touch these lines):
additive only, one unique anchor (the renderer's AnalyzeCapturedSeatSkin declaration), refuses a reinstall or a
module without the renderer's seat analyzer. Nothing is compiled or run here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARKER = 'AnalyzeCapturedControllerGrip'
HEADER_ANCHOR = 'static FString AnalyzeCapturedSeatSkin('
REQUIRED_CPP = 'FString USub01HomeHandsInstance::AnalyzeCapturedSeatSkin('
SOURCE_FILES = {'hands_header': 'Sub01HomeHands.h', 'hands_cpp': 'Sub01HomeHands.cpp'}

HEADER = r'''
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static FString AnalyzeCapturedControllerGrip(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,FName GripBone,FVector GripOffset,FQuat GripRotation,const TArray<FVector>& ControllerLocalTriangles,float BandLowCm,float BandHighCm,float MarginCm);
'''

CPP = r'''
// tools/unreal_controller_grip_contact_native.py: hand skin vs the socket-attached controller (probe only).
static double Sub01SolidAngle(const FVector& P,const FVector& A,const FVector& B,const FVector& C){
 const FVector a=A-P,b=B-P,c=C-P;const double la=a.Size(),lb=b.Size(),lc=c.Size();
 const double Num=FVector::DotProduct(a,FVector::CrossProduct(b,c));
 const double Den=la*lb*lc+FVector::DotProduct(a,b)*lc+FVector::DotProduct(a,c)*lb+FVector::DotProduct(b,c)*la;
 return 2.0*FMath::Atan2(Num,Den);
}
FString USub01HomeHandsInstance::AnalyzeCapturedControllerGrip(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,FName GripBone,FVector GripOffset,FQuat GripRotation,const TArray<FVector>& ControllerLocalTriangles,float BandLowCm,float BandHighCm,float MarginCm){
#if WITH_EDITOR
 if(!Mesh)return TEXT("{\"error\":\"missing mesh\"}");
 if(ControllerLocalTriangles.Num()<3||ControllerLocalTriangles.Num()%3)return TEXT("{\"error\":\"missing controller triangles\"}");
 if(!(BandLowCm<=BandHighCm)||!(MarginCm>BandHighCm))return TEXT("{\"error\":\"invalid band\"}");
 const auto& Ref=Mesh->GetRefSkeleton();const auto& Inv=Mesh->GetRefBasesInvMatrix();auto* Model=Mesh->GetImportedModel();
 if(!Model||!Model->LODModels.Num()||ComponentPose.Num()!=Ref.GetNum()||Inv.Num()!=Ref.GetNum())return TEXT("{\"error\":\"incomplete pose or imported model\"}");
 const int32 Grip=Ref.FindBoneIndex(GripBone);if(Grip==INDEX_NONE)return TEXT("{\"error\":\"missing grip bone\"}");
 // Exactly the controller adapter's placement: socket location + normalized socket rotation * the evidence offset.
 const FTransform Socket=ComponentPose[Grip]*BodyWorld;const FQuat R=Socket.GetRotation().GetNormalized();
 const FVector CLoc=Socket.GetLocation()+R.RotateVector(GripOffset);const FQuat CRot=R*GripRotation.GetNormalized();
 TArray<FVector> Tris;Tris.Reserve(ControllerLocalTriangles.Num());FBox Box(ForceInit);
 for(const FVector& L:ControllerLocalTriangles){const FVector W=CLoc+CRot.RotateVector(L);Tris.Add(W);Box+=W;}
 const FBox Near=Box.ExpandBy(MarginCm);
 // Bind-space hand sets (fit_controller_grip.py Hands.from_owner): bones and the oriented palm normal per side.
 auto Find=[&Ref](const FString& Suffix){for(int32 B=0;B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Suffix))return B;return int32(INDEX_NONE);};
 auto BindPos=[&Inv](int32 B){return FVector(Inv[B].Inverse().GetOrigin());};
 const TCHAR* Sides[2]={TEXT("Left"),TEXT("Right")};int32 HandBone[2];FVector PalmNormal[2];
 for(int32 S=0;S<2;++S){
  const FString Side(Sides[S]);const int32 H=Find(Side+TEXT("Hand")),M=Find(Side+TEXT("HandMiddle1")),I=Find(Side+TEXT("HandIndex1")),P=Find(Side+TEXT("HandPinky1")),T=Find(Side+TEXT("HandThumb3"));
  if(H==INDEX_NONE||M==INDEX_NONE||I==INDEX_NONE||P==INDEX_NONE||T==INDEX_NONE)return TEXT("{\"error\":\"missing hand joints\"}");
  FVector N=FVector::CrossProduct(BindPos(M)-BindPos(H),BindPos(I)-BindPos(P)).GetSafeNormal();
  if(N.IsNearlyZero())return TEXT("{\"error\":\"degenerate palm frame\"}");
  if(FVector::DotProduct(BindPos(T)-BindPos(H),N)<0)N=-N;HandBone[S]=H;PalmNormal[S]=N;
 }
 struct FHand{int32 Palm=0,PalmNear=0,PalmBand=0,Hand=0,HandNear=0,HandPen=0;double PalmMin=DBL_MAX,HandMin=DBL_MAX;};FHand Out[2];int32 Invalid=0;
 auto Signed=[&](const FVector& Q){
  double D=DBL_MAX;for(int32 K=0;K+2<Tris.Num();K+=3)D=FMath::Min(D,(double)FVector::Dist(Q,FMath::ClosestPointOnTriangleToPoint(Q,Tris[K],Tris[K+1],Tris[K+2])));
  if(Box.IsInside(Q)){double W=0;for(int32 K=0;K+2<Tris.Num();K+=3)W+=Sub01SolidAngle(Q,Tris[K],Tris[K+1],Tris[K+2]);if(FMath::Abs(W/(4*PI))>.5)D=-D;}
  return D;};
 for(const auto& Section:Model->LODModels[0].Sections)for(const auto& V:Section.SoftVertices){
  uint64 Sum=0;double HandW[2]={0,0},ChainW[2]={0,0};
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;Sum+=W;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local)){++Invalid;continue;}const int32 B=Section.BoneMap[Local];if(!Ref.GetRefBoneInfo().IsValidIndex(B)){++Invalid;continue;}
   const FString Name=Ref.GetBoneName(B).ToString();
   for(int32 S=0;S<2;++S){const FString Prefix=FString(Sides[S])+TEXT("Hand");
    if(B==HandBone[S]){HandW[S]+=W;ChainW[S]+=W;}
    else if(Name.Contains(Prefix)&&(Name.EndsWith(TEXT("1"))||Name.EndsWith(TEXT("2"))||Name.EndsWith(TEXT("3"))))ChainW[S]+=W;}}
  if(!Sum)continue;int32 Side=-1;for(int32 S=0;S<2;++S)if(ChainW[S]>=.5*Sum)Side=S;if(Side<0)continue;
  const FVector3f BindNormal(V.TangentZ.X,V.TangentZ.Y,V.TangentZ.Z);
  const bool Palm=HandW[Side]>=.5*Sum&&FVector::DotProduct(FVector(BindNormal).GetSafeNormal(),PalmNormal[Side])>=.5;
  FVector P=FVector::ZeroVector;
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local))continue;const int32 B=Section.BoneMap[Local];if(!Inv.IsValidIndex(B))continue;
   P+=ComponentPose[B].TransformPosition(FVector(Inv[B].TransformPosition(V.Position)))*(double(W)/double(Sum));}
  P=BodyWorld.TransformPosition(P);auto& H=Out[Side];++H.Hand;if(Palm)++H.Palm;
  if(!Near.IsInside(P))continue;const double D=Signed(P);
  ++H.HandNear;H.HandMin=FMath::Min(H.HandMin,D);if(D<BandLowCm)++H.HandPen;
  if(Palm){++H.PalmNear;H.PalmMin=FMath::Min(H.PalmMin,D);if(D>=BandLowCm&&D<=BandHighCm)++H.PalmBand;}
 }
 FString Result=FString::Printf(TEXT("{\"invalidInfluences\":%d,\"controllerWorldLocation\":[%.8f,%.8f,%.8f],\"controllerWorldRotationXYZW\":[%.10f,%.10f,%.10f,%.10f],\"controllerTriangles\":%d,\"marginCm\":%.6f,\"hands\":["),
  Invalid,CLoc.X,CLoc.Y,CLoc.Z,CRot.X,CRot.Y,CRot.Z,CRot.W,Tris.Num()/3,MarginCm);
 for(int32 S=0;S<2;++S){const auto& H=Out[S];
  Result+=FString::Printf(TEXT("%s{\"side\":\"%s\",\"palmVertices\":%d,\"palmNearVertices\":%d,\"palmBandVertices\":%d,\"palmMinGapCm\":%.8f,\"handVertices\":%d,\"handNearVertices\":%d,\"handPenetratingVertices\":%d,\"handMinSignedCm\":%.8f}"),
   S?TEXT(","):TEXT(""),S?TEXT("right"):TEXT("left"),H.Palm,H.PalmNear,H.PalmBand,H.PalmNear?H.PalmMin:double(MarginCm),H.Hand,H.HandNear,H.HandPen,H.HandNear?H.HandMin:double(MarginCm));}
 return Result+TEXT("]}");
#else
 return TEXT("{\"error\":\"editor only\"}");
#endif
}
'''


def install(sources: dict) -> dict:
    """Additive install into {'hands_header','hands_cpp'}; refuses reinstall, a missing seat analyzer or a non-unique anchor."""
    out = dict(sources)
    if MARKER in out['hands_header'] or MARKER in out['hands_cpp']:
        raise ValueError('Controller grip contact analyzer is already installed')
    if REQUIRED_CPP not in out['hands_cpp']:
        raise ValueError("The renderer's AnalyzeCapturedSeatSkin (tools/unreal_skin_contact_native.py) is not staged")
    lines = [l for l in out['hands_header'].split('\n') if HEADER_ANCHOR in l]
    if len(lines) != 1:
        raise ValueError(f'Grip analyzer anchor not unique in hands_header: {len(lines)} lines contain {HEADER_ANCHOR!r}')
    out['hands_header'] = out['hands_header'].replace(lines[0] + '\n', lines[0] + '\n' + HEADER.lstrip('\n'), 1)
    out['hands_cpp'] = out['hands_cpp'] + CPP
    for key in SOURCE_FILES:
        assert_additive(sources[key], out[key])
    return out


def assert_additive(before: str, after: str) -> None:
    """Every original line survives, in order (the bundle's additive-only rule)."""
    it = iter(after.split('\n'))
    for line in before.split('\n'):
        if not any(line == other for other in it):
            raise ValueError(f'Install is not additive: lost {line[:60]!r}')


def install_module(module: Path, dry_run: bool = False) -> dict:
    module = Path(module)
    before = {k: (module / name).read_text() for k, name in SOURCE_FILES.items()}
    after = install(before)
    if not dry_run:
        for k, name in SOURCE_FILES.items():
            (module / name).write_text(after[k])
    return {k: {'added_lines': after[k].count('\n') - before[k].count('\n')} for k in SOURCE_FILES}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('cmd', choices=['install'])
    p.add_argument('module', type=Path)
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)
    print(install_module(a.module, a.dry_run))
    print('Grip contact analyzer ' + ('checked (dry run)' if a.dry_run else 'installed') + '; not compiled or run here.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
