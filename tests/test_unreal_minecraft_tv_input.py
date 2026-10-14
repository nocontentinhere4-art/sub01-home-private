from tools import unreal_minecraft_tv_input as native

def test_install_targets_character_and_real_hit_only():
 h='class World{GENERATED_BODY()};class Character{GENERATED_BODY()\n void ConfigureActualPC();};'
 c='void Begin(){ ConfigureActualPC();}\nvoid Tick(){ Super::Tick(DeltaSeconds);}\nvoid Interact(){if(TryNativeHomeDevice(Hit.GetComponent()))return;}'
 header,cpp=native.install(h,c)
 assert header.index('MinecraftInputId')>header.index('class Character')
 assert 'FocusMinecraftTV(Hit);return;' in cpp
 assert cpp.count(' ConfigureMinecraftTVInput();')==1 and cpp.count(' TickMinecraftTVInput();')==1
 assert 'PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat' in cpp
 assert 'LineTraceSingleByChannel' in cpp and 'Count==1' in cpp
 assert 'native_start_ticks' in cpp and 'chmod(TCHAR_TO_UTF8(*Temp),0600)' in cpp
 assert 'if(OK&&Response&&Response->GetResponseCode()==200)SendMinecraftTVInput' in cpp
 assert 'SetActorLocation' not in cpp and 'SetWorldLocation' not in cpp
