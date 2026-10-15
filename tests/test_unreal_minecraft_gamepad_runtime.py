"""The real manualMinecraft lane keeps timing, focus and autonomy boundaries."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from stage_unreal_home_runtime import stage
from unreal_minecraft_gamepad_runtime import install

def test_actual_generated_tv_input_hook_is_cadenced_and_does_not_touch_autonomy(tmp_path):
 (tmp_path/'Config').mkdir();(tmp_path/'Sub01HomeLab.uproject').write_text('{}');stage(tmp_path);root=tmp_path/'Source/Sub01HomeLab';h=(root/'Sub01HomeLab.h').read_text();c=(root/'Sub01HomeLab.cpp').read_text();h,c=install(h,c)
 tick=c.split('void ASub01HomeCharacter::TickMinecraftTVInput(){',1)[1].split('void ASub01HomeCharacter::ReleaseMinecraftTVInput(){',1)[0]
 assert tick.index('!PublishMinecraftTVReceipt()')<tick.index('Now-MinecraftLastSend<.1')<tick.index('ApplyManualMinecraftGamepad()')
 assert 'Frame!=MinecraftFrame' in c and 'Ticks!=MinecraftStartTicks' in c and 'Consumer!=MinecraftConsumerId' in c
 assert 'Event!=MinecraftFocusEvent' in c and 'UTC-Stamp>.25' in c
 assert 'MinecraftKeyboardKeys.Add(K,false);A->MinecraftKeys.Add(K,A->MinecraftPadKeys.FindRef(K))' in c
 assert 'ReleaseManualMinecraftGamepad();MinecraftKeyboardKeys.Empty();'in c
 assert 'if(Mining)SendMinecraftTVInput(TEXT("cancel"))'in c
 assert 'PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat' in c
 assert 'seat_verified'not in c.split('void ASub01HomeCharacter::ApplyManualMinecraftGamepad(){',1)[1]
 assert 'XTest'not in c.split('void ASub01HomeCharacter::ApplyManualMinecraftGamepad(){',1)[1]
