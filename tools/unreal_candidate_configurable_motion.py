"""Honor owned retargeted clip bindings without changing legacy defaults or gates."""
OLD_WALK='LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk"))'
NEW_WALK='LoadObject<UAnimSequence>(nullptr,WalkClipPath.IsEmpty()?TEXT("/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk"):*WalkClipPath)'
OLD_GRIP='LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip"))'
NEW_GRIP='LoadObject<UAnimSequence>(nullptr,ControllerGripClipPath.IsEmpty()?TEXT("/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip"):*ControllerGripClipPath)'
FIELD=' UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString ControllerGripClipPath;'
def install(header,cpp):
 if FIELD in header:
  if OLD_WALK in cpp or OLD_GRIP in cpp or cpp.count(NEW_WALK)!=2 or cpp.count(NEW_GRIP)!=1:raise RuntimeError('Incomplete configurable motion patch')
  return header,cpp
 anchor=' UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString HandsMeshPath;'
 if header.count(anchor)!=1 or cpp.count(OLD_WALK)!=2 or cpp.count(OLD_GRIP)!=1:raise RuntimeError('Exact current private-home hand binding source required')
 return header.replace(anchor,anchor+'\n'+FIELD,1),cpp.replace(OLD_WALK,NEW_WALK).replace(OLD_GRIP,NEW_GRIP)
