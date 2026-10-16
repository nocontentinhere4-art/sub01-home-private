#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Commandlets/Commandlet.h"
#include "Sub01WholeClipWitness.generated.h"
UCLASS()
class SUB01WHOLECLIPWITNESS_API USub01WholeClipWitnessLibrary:public UBlueprintFunctionLibrary {
 GENERATED_BODY()
 public:
 UFUNCTION(BlueprintCallable,Category="SUB01|OfflineDiagnostics") static FString Capture(const FString& Manifest,const FString& Output);
};
UCLASS()
class SUB01WHOLECLIPWITNESS_API USub01WholeClipWitnessCommandlet:public UCommandlet {
 GENERATED_BODY()
 public:
 USub01WholeClipWitnessCommandlet();
 virtual int32 Main(const FString& Params) override;
};
