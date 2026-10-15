import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('motion',Path(__file__).parents[1]/'tools/unreal_candidate_configurable_motion.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def source():return ' UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString HandsMeshPath;',m.OLD_WALK+';\n'+m.OLD_WALK+';\n'+m.OLD_GRIP+';'
def test_owned_walk_and_controller_paths_used_with_legacy_fallback():
 h,c=m.install(*source());assert c.count(m.NEW_WALK)==2 and c.count(m.NEW_GRIP)==1 and m.FIELD in h;assert m.install(h,c)==(h,c)
def test_unrecognized_current_source_fails_closed():
 h,c=source()
 with pytest.raises(RuntimeError):m.install(h,c.replace(m.OLD_WALK,'different',1))
