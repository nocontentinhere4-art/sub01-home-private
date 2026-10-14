#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Sub01HomeDeviceBridge.generated.h"
class UMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UCanvasRenderTarget2D;
class UCanvas;
class UTexture2D;
class FJsonObject;
class IInputProcessor;
UCLASS(ClassGroup=(Sub01),meta=(BlueprintSpawnableComponent))
class SUB01HOMELAB_API USub01HomeDeviceBridge:public UActorComponent{
 GENERATED_BODY()
public:
 USub01HomeDeviceBridge();
 bool Configure(FName Device,UMeshComponent* Screen,int32 Slot,UMaterialInterface* Material);
 void SetLocalPrivacy(bool Hidden);
 bool FocusHit(UActorComponent* Component);
 void ReleaseFocus();
 void PhoneAction(const FString& Action);
 void PhoneNavigate(const FString& URL);
 void PhoneOpenApp(const FString& App);
 void TVGame(const FString& Game);
 void SetPongDirection(float Direction){PongDirection=FMath::Clamp(Direction,-1.f,1.f);}
 FName GetFocusedDevice()const{return FocusedDevice;}
protected:
 void EndPlay(const EEndPlayReason::Type Reason)override;
private:
 FString Origin=TEXT("http://127.0.0.1:8798");
 FString Token,PhoneFrameId;bool Private=true,LocalPrivacy=false,Busy=false;
 uint64 Generation=0;float PongDirection=0;FName FocusedDevice;
 FTimerHandle Timer;
 TMap<UMeshComponent*,FName> Screens;
 TMap<FName,FString> ImageIdentity;
 TSet<FName> FramePending;
 UPROPERTY()TMap<FName,TObjectPtr<UMaterialInstanceDynamic>> Materials;
 UPROPERTY()TMap<FName,TObjectPtr<UTexture2D>> Images;
 UPROPERTY()TObjectPtr<UCanvasRenderTarget2D> BlankCanvas;
 UPROPERTY()TObjectPtr<UCanvasRenderTarget2D> TVCanvas;
 TSharedPtr<FJsonObject> PongState;
 TSharedPtr<IInputProcessor> Input;
 void Poll();void Clear();
 void ReadHome(TFunction<void(TSharedPtr<FJsonObject>)> Done);
 bool PublicHome(const TSharedPtr<FJsonObject>& State)const;
 void FetchFrame(FName Device,const FString& Identity,uint64 Epoch);
 void Action(FName Device,const TSharedPtr<FJsonObject>& Body);
 UFUNCTION()void DrawTV(UCanvas* Canvas,int32 Width,int32 Height);
};
