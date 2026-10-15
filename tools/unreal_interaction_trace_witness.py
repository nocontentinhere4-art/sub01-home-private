"""Observe the existing physical E ray and device focus result, without rerouting it.

This adds no trace, movement, range, device action or readiness flag. It logs the
result of the one existing 200cm trace and the one existing FocusHit call.
"""
RAY = ' if(!GetWorld()->LineTraceSingleByChannel(Hit,Start,Start+ViewCamera->GetForwardVector()*200,ECC_Visibility,Query)) return;'
RAY_WITH_WITNESS = r''' const FVector InteractionEnd=Start+ViewCamera->GetForwardVector()*200;
 const bool InteractionHit=GetWorld()->LineTraceSingleByChannel(Hit,Start,InteractionEnd,ECC_Visibility,Query);
 Sub01LogPrivateInteractionRay(Hit,InteractionHit,Start,InteractionEnd);
 if(!InteractionHit)return;'''
WITNESS = r'''
static void Sub01LogPrivateInteractionRay(const FHitResult& Hit,bool DidHit,const FVector& Start,const FVector& End){
 auto* Component=Hit.GetComponent();auto* Actor=Hit.GetActor();FString Tags;
 if(Component)for(const FName Tag:Component->ComponentTags){if(!Tags.IsEmpty())Tags+=TEXT("|");Tags+=Tag.ToString();}
 const FString ActorPath=Actor?Actor->GetPathName():TEXT("none"),ComponentPath=Component?Component->GetPathName():TEXT("none");
 const FString Profile=Component?Component->GetCollisionProfileName().ToString():TEXT("none");
 UE_LOG(LogTemp,Display,TEXT("SUB01_INTERACT_RAY hit=%d start=%s end=%s rangeCm=200 actor=%s component=%s tags=%s distanceCm=%.6f point=%s normal=%s collisionEnabled=%d profile=%s"),DidHit?1:0,*Start.ToString(),*End.ToString(),*ActorPath,*ComponentPath,*Tags,Hit.Distance,*Hit.ImpactPoint.ToString(),*Hit.ImpactNormal.ToString(),Component?int32(Component->GetCollisionEnabled()):-1,*Profile);
}
'''
FOCUS = 'if(Devices->FocusHit(Component)){' 
FOCUS_WITH_WITNESS = r'''const FName FocusBefore=Devices->GetFocusedDevice();
 const bool FocusAccepted=Devices->FocusHit(Component);
 const FString ComponentPath=Component?Component->GetPathName():TEXT("none");
 UE_LOG(LogTemp,Display,TEXT("SUB01_INTERACT_DEVICE_FOCUS component=%s accepted=%d before=%s after=%s"),*ComponentPath,FocusAccepted?1:0,*FocusBefore.ToString(),*Devices->GetFocusedDevice().ToString());
 if(FocusAccepted){'''


def install(header, cpp):
    anchor='void ASub01HomeCharacter::Interact() {'
    if 'SUB01_INTERACT_RAY' in cpp or 'SUB01_INTERACT_DEVICE_FOCUS' in cpp:
        raise ValueError('Interaction witness already installed')
    if any(cpp.count(part)!=1 for part in (anchor,RAY,FOCUS)):
        raise ValueError('Exact existing interaction/focus hooks required; no routing guess')
    cpp=cpp.replace(anchor,WITNESS+'\n'+anchor,1)
    cpp=cpp.replace(RAY,RAY_WITH_WITNESS,1).replace(FOCUS,FOCUS_WITH_WITNESS,1)
    return header,cpp
