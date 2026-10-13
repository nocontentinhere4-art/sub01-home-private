"""Bounded native GameViewport frames of real one-pass arm-corrected source clip."""
FIELDS=r'''
 void UpdateNativeContactRecording();
 bool ContactRecordChecked=false,ContactRecordActive=false,ContactRecordPending=false;
 FString ContactRecordDir,ContactRecordPendingPath;
 double ContactRecordWarmStart=0,ContactRecordStart=0,ContactRecordPendingTime=0;
 float ContactRecordPendingPose=-1;int32 ContactRecordCount=0,ContactRecordWarmTicks=0;
 FString ContactRecordRows;
'''
METHODS=r'''
void ASub01HomeCharacter::UpdateNativeContactRecording(){
 if(!ContactRecordChecked){ContactRecordChecked=true;if(!FParse::Value(FCommandLine::Get(),TEXT("Sub01ContactRecordDir="),ContactRecordDir))return;IFileManager::Get().MakeDirectory(*ContactRecordDir,true);ContactRecordWarmStart=FPlatformTime::Seconds();}
 if(ContactRecordDir.IsEmpty())return;auto* Hands=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance());if(!Hands||Hands->ContactTimes.Num()!=301){UE_LOG(LogTemp,Error,TEXT("SUB01_RECORD_REFUSED no measured contact profile"));FPlatformMisc::RequestExit(false);return;}
 const double Now=FPlatformTime::Seconds();
 if(!ContactRecordActive){++ContactRecordWarmTicks;if(Now-ContactRecordWarmStart<45)return;ContactRecordActive=true;ContactRecordStart=Now;Hands->ContactFreezeTime=-1;++Hands->ContactRestartSerial;UE_LOG(LogTemp,Display,TEXT("SUB01_CONTACT_RECORD_START actualGameViewport genuine3to8 onepass; no separate camera; warmTicks=%d warmSeconds=%.6f warmTickHz=%.6f"),ContactRecordWarmTicks,Now-ContactRecordWarmStart,ContactRecordWarmTicks/(Now-ContactRecordWarmStart));}
 if(ContactRecordPending){if(IFileManager::Get().FileSize(*ContactRecordPendingPath)>0){if(ContactRecordCount)ContactRecordRows+=TEXT(",\n");ContactRecordRows+=FString::Printf(TEXT("{\"file\":\"frame-%04d.png\",\"wallSeconds\":%.8f,\"evaluatedClipSeconds\":%.8f}"),ContactRecordCount,ContactRecordPendingTime,ContactRecordPendingPose);++ContactRecordCount;ContactRecordPending=false;}else if(Now-ContactRecordStart>15){UE_LOG(LogTemp,Error,TEXT("SUB01_RECORD_FAILED viewport frame not written"));FPlatformMisc::RequestExit(false);}else return;}
 if(Now-ContactRecordStart>=5.5){FFileHelper::SaveStringToFile(*(TEXT("{\"kind\":\"actual GameViewport continuous source clip onepass\",\"frames\":[\n")+ContactRecordRows+TEXT("\n]}")),*FPaths::Combine(ContactRecordDir,TEXT("frames.json")));UE_LOG(LogTemp,Display,TEXT("SUB01_CONTACT_RECORD_COMPLETE frames=%d actualSeconds=%.6f"),ContactRecordCount,Now-ContactRecordStart);ContactRecordDir.Empty();if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01RecordKeepAlive")))FPlatformMisc::RequestExit(false);return;}
 ContactRecordPendingPath=FPaths::Combine(ContactRecordDir,FString::Printf(TEXT("frame-%04d.png"),ContactRecordCount));ContactRecordPendingTime=Now-ContactRecordStart;ContactRecordPendingPose=Hands->ContactEvaluatedTime;ContactRecordPending=true;FScreenshotRequest::RequestScreenshot(ContactRecordPendingPath,false,false);
}
'''
