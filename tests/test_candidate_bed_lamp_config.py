import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('lamp',Path(__file__).parents[1]/'tools/unreal_candidate_save_bed_lamp.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_merge_only_one_new_key_preserves_repeated_unreal_sections():
 s='[/Script/Sub01HomeLab.Sub01HomeCharacter]\nHandsMeshPath=old\n[Other]\nKey=value\n[/Script/Sub01HomeLab.Sub01HomeCharacter]\nWalkingCameraOffset=(X=1,Y=2,Z=3)\n';r=m.configured_power(s);assert r.startswith(s)and r.count('BedsideLampIntensityCandela=0.35')==1
 with pytest.raises(RuntimeError):m.configured_power(r)
