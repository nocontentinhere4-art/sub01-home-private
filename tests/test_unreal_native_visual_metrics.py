from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_native_visual_metrics import install,METHODS

def test_installs_one_actual_tick_with_identity_prerequisite():
 h=' private: UPROPERTY() TObjectPtr<UCameraComponent> ViewCamera;'
 c='#include "Sub01HomeLab.h"\nvoid PrivateSettingsStartTicks();\n Super::Tick(DeltaSeconds);'
 oh,oc=install(h,c)
 assert oh.count('void PublishPrivateVisualMetrics();')==1
 assert oc.startswith('#include "Sub01HomeLab.h"')
 assert oc.count(' PublishPrivateVisualMetrics();')==1
 assert 'PrivateSettingsStartTicks()' in oc

def test_reports_last_completed_metering_without_render_or_writes():
 assert 'GetLastEyeAdaptationExposure()' in METHODS
 assert 'last_completed_metering_available' in METHODS
 assert 'FinalPostProcessSettings' in METHODS
 assert 'Now-PrivateVisualMetricsAt<1.0' in METHODS
 for forbidden in ('SetIntensity(', 'SetScalarParameterValue(', 'SetVectorParameterValue(', 'SetActorLocation(', 'BeginRenderingViewFamily(', 'Draw('):
  assert forbidden not in METHODS
 assert 'Nodes[]={66,126,127,129,198,199}' in METHODS
 assert 'M->GetAllScalarParameterInfo' in METHODS
