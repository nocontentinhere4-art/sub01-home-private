#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Sub01GuestInputQueue.h"
#include "Sub01PCBridge.generated.h"
class UMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UCanvasRenderTarget2D;
class UTexture2D;
class UCanvas;
class FJsonObject;
class IInputProcessor;

// Actual existing private home API only. No shell emulation or embedded credential.
UCLASS(ClassGroup=(Sub01), meta=(BlueprintSpawnableComponent))
class SUB01HOMELAB_API USub01PCBridge : public UActorComponent {
 GENERATED_BODY()
public:
 USub01PCBridge();
 // Caller supplies the actual monitor-screen component, not the whole desk.
 bool Configure(UMeshComponent* Screen, int32 MaterialSlot, UMaterialInterface* ScreenMaterial);
 UFUNCTION(BlueprintCallable) void SetOperatorFocus(bool Focus);
 UFUNCTION(BlueprintCallable) void SetLocalPrivacy(bool Hidden);
 UFUNCTION(BlueprintCallable) void SetTypedLine(const FString& Line);
 UFUNCTION(BlueprintCallable) void SubmitTypedLine();
 UFUNCTION(BlueprintPure) FString GetPCStatus() const { return Status; }
 bool HasOperatorFocus() const { return Focused; }
 bool IsAcceptingNativeInput() const { return Focused&&!Private&&!LocalPrivacy; }
 bool IsGraphicalInputActive() const { return IsAcceptingNativeInput()&&GuestPS2Input; }
 void SendGraphicalKey(uint32 ScanCode,bool Shift,bool Control,bool Alt);
 void SendGraphicalMouse(float DeltaX,float DeltaY,float Wheel,bool Left,bool Middle,bool Right);
 void AppendNativeCharacter(TCHAR Character);
 void BackspaceNativeCharacter();
protected:
 virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
 // Loopback only: remote backend access needs an approved private tunnel/relay.
 FString Origin=TEXT("http://127.0.0.1:8798");
 FString OperatorToken, TerminalOutput, TypedLine, Status=TEXT("PC backend disconnected");
 bool Focused=false, Busy=false, Private=true, LocalPrivacy=false, CommandBusy=false;
 double LastSessionHeartbeat=0;
 bool PrivacyDesired=false, PrivacyAcknowledged=false, PrivacyKnown=false, PrivacyRequestPending=false;
 double LastPrivacyAttempt=-10;
 bool FrameBusy=false,GuestPS2Input=false;
 double ScreenAspect=1.7;
 TSub01GuestInputQueue<TSharedPtr<FJsonObject>> GraphicalInputs;
 FString FrameRevision;
 UPROPERTY() TObjectPtr<UTexture2D> GraphicalFrame;
 uint64 Generation=0;
 FTimerHandle PollTimer;
 TSharedPtr<IInputProcessor> NativeInputProcessor;
 UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MonitorMaterial;
 UPROPERTY() TObjectPtr<UCanvasRenderTarget2D> TerminalCanvas;

 void Poll();
 void ResetNativeModifiers();
 void ReadState(TFunction<void(TSharedPtr<FJsonObject>)> Done);
 void SendFlag(const FString& Path, bool Active, TFunction<void(bool)> Done);
 bool IsPublicState(const TSharedPtr<FJsonObject>& State) const;
 void ClearPrivateState(const FString& Reason);
 void SendGraphicalInput(const TSharedPtr<FJsonObject>& Body);
 void PumpGraphicalInput();
 void FetchGraphicalFrame(const TSharedPtr<FJsonObject>& State);
 void ApplyTerminal(const TSharedPtr<FJsonObject>& State);

 UFUNCTION() void DrawTerminal(UCanvas* Canvas, int32 Width, int32 Height);
};
