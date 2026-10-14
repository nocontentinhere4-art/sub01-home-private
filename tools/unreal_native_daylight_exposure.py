"""One-stop maximum daylight EV headroom candidate; OFF until official floor proof.

Renderer owns integration/build. Install after native view settings (fixture
module may be installed before this). Review actual scale/floor formula before
NativeDaylightExposureVerified=true. Only owned volume minimum EV is changed.
"""
from pathlib import Path

POLICY = r'''#pragma once
#include <cmath>
namespace Sub01NativeDaylightExposure {
// Installed UE: PostProcessEyeAdaptation.cpp min white point / .18 average;
// EyeAdaptation USF clamps average then outputs exp2(bias) / exposure.
// With lens .78 and no bias curve, minEV -3 / bias1 caps scale at16.
inline double MaximumScale(double MinEV,double Bias,double LensAttenuation=.78){
 if(!std::isfinite(MinEV)||!std::isfinite(Bias)||!std::isfinite(LensAttenuation)||LensAttenuation<=0)return 0;
 const double LuminanceMax=.78/std::fmax(LensAttenuation,.01);
 return std::exp2(Bias-MinEV)/LuminanceMax;
}
inline bool FloorClamped(double SceneAverage,double MinEV,double LensAttenuation=.78){
 if(!std::isfinite(SceneAverage)||SceneAverage<0||!std::isfinite(MinEV)||!std::isfinite(LensAttenuation)||LensAttenuation<=0)return false;
 return SceneAverage<.18*(.78/std::fmax(LensAttenuation,.01))*std::exp2(MinEV);
}
inline double DayMin(double Hour){
 if(!std::isfinite(Hour)||Hour<0||Hour>24)return -3.;
 const double Elevation=std::fmax(0.,std::sin((Hour-6.)/12.*3.14159265358979323846));
 return -3.-Elevation;
}
}
'''
FIELDS = r'''
 UPROPERTY(Config) bool NativeDaylightExposureVerified=false;
 FString NativeDaylightExposureDiagnostic;
 bool ValidateNativeDaylightExposure();
 void ApplyNativeDaylightExposure(float Hour);
'''
INCLUDES = r'''
#include "HAL/IConsoleManager.h"
#include "Engine/PostProcessVolume.h"
#include "Sub01NativeDaylightExposurePolicy.h"
'''
METHODS = r'''
bool ASub01HomeCharacter::ValidateNativeDaylightExposure(){
 if(!NativeDaylightExposureVerified){NativeDaylightExposureDiagnostic=TEXT("Daylight EV headroom disabled pending official floor-formula proof");return true;}
 auto Refuse=[&](const FString& Error){NativeDaylightExposureDiagnostic=Error;UE_LOG(LogTemp,Error,TEXT("SUB01_DAYLIGHT_EXPOSURE_UNAVAILABLE %s"),*Error);return false;};
 const auto* Lens=IConsoleManager::Get().FindConsoleVariable(TEXT("r.EyeAdaptation.LensAttenuation"));
 const auto* Extended=IConsoleManager::Get().FindConsoleVariable(TEXT("r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange"));
 if(!Lens||!Extended||!FMath::IsFinite(Lens->GetFloat())||!FMath::IsNearlyEqual(Lens->GetFloat(),.78f,.00001f)||Extended->GetInt()!=1)return Refuse(TEXT("Actual lens attenuation/extended EV CVars differ from proved floor formula"));
 auto* Post=Cast<APostProcessVolume>(FindAuthoredSettingsActor(TEXT("SUB01_ReferencePost")));
 if(!Post||!Post->bEnabled||!Post->bUnbound||Post->BlendWeight!=1.f)return Refuse(TEXT("Unique active owned exposure volume unavailable"));
 const auto& Settings=Post->Settings;
 if(!Settings.bOverride_AutoExposureMethod||Settings.AutoExposureMethod!=EAutoExposureMethod::AEM_Histogram||!Settings.bOverride_AutoExposureMinBrightness||!Settings.bOverride_AutoExposureMaxBrightness||Settings.AutoExposureMaxBrightness!=3.f||Settings.AutoExposureBias!=1.f||Settings.AutoExposureBiasCurve)return Refuse(TEXT("Owned histogram exposure maxEV3/bias1/noCurve differs from reviewed receipt"));
 const float Expected=float(Sub01NativeDaylightExposure::DayMin(PrivateEnvironmentHour));
 if(!FMath::IsFinite(Settings.AutoExposureMinBrightness)||(Settings.AutoExposureMinBrightness!=-3.f&&!FMath::IsNearlyEqual(Settings.AutoExposureMinBrightness,Expected,.0001f)))return Refuse(TEXT("Owned minimum EV differs from baseline or prior bounded daylight value"));
 NativeDaylightExposureDiagnostic.Empty();return true;
}
void ASub01HomeCharacter::ApplyNativeDaylightExposure(float Hour){
 if(!NativeDaylightExposureVerified)return;
 auto* Post=Cast<APostProcessVolume>(FindAuthoredSettingsActor(TEXT("SUB01_ReferencePost")));
 if(Post)Post->Settings.AutoExposureMinBrightness=float(Sub01NativeDaylightExposure::DayMin(Hour));
}
'''


def stage(module):
    (Path(module)/'Sub01NativeDaylightExposurePolicy.h').write_text(POLICY)


def install(header, cpp):
    field=' void InitializePrivateViewSettings();'
    include='#include "Sub01HomeLab.h"'
    preflight=' // All fields are validated before any renderer state is changed. SUN is not an indoor lamp.'
    hour='  PrivateEnvironmentHour=float(Hour);'
    init='void ASub01HomeCharacter::InitializePrivateViewSettings(){'
    receipt='Receipt->SetStringField(TEXT("error"),Error);'
    for text, hook in ((header,field),(cpp,include),(cpp,preflight),(cpp,hour),(cpp,init),(cpp,receipt)):
        if text.count(hook)!=1:
            raise ValueError('Unique native daylight exposure integration hook required')
    if 'ValidateNativeDaylightExposure' in cpp:
        raise ValueError('Native daylight exposure already installed')
    start=cpp.index(init);end=cpp.index('\n}',start)+2
    body=cpp[start:end]
    initial_receipt='WritePrivateViewSettingsReceipt(0,true,TEXT(""));'
    if body.count(initial_receipt)!=1:
        raise ValueError('Unique initialized native settings receipt required')
    body=body.replace(initial_receipt,'if(!ValidateNativeDaylightExposure()){WritePrivateViewSettingsReceipt(0,false,NativeDaylightExposureDiagnostic);return;}\n ApplyNativeDaylightExposure(PrivateEnvironmentHour);\n '+initial_receipt,1)
    cpp=cpp[:start]+body+cpp[end:]
    cpp=cpp.replace(include,include+'\n'+INCLUDES,1)
    cpp=cpp.replace(preflight,' if(HasHour&&!ValidateNativeDaylightExposure()){WritePrivateViewSettingsReceipt(Revision,false,NativeDaylightExposureDiagnostic);return;}\n'+preflight,1)
    cpp=cpp.replace(hour,hour+'ApplyNativeDaylightExposure(PrivateEnvironmentHour);',1)
    cpp=cpp.replace(receipt,receipt+'Receipt->SetBoolField(TEXT("daylight_exposure_ready"),NativeDaylightExposureVerified&&NativeDaylightExposureDiagnostic.IsEmpty());Receipt->SetStringField(TEXT("daylight_exposure_diagnostic"),NativeDaylightExposureDiagnostic);',1)
    return header.replace(field,FIELDS+'\n'+field,1),cpp+METHODS
