from pathlib import Path
import hashlib

# The pre-UE5.8 probe is not tracked in git, so rebuild it by undoing the UE5.8 getter change
# and check it against the SHA256 recorded when the port was made.
ORIGINAL_SHA256='a9a06d79f9e08ba9e8fac87326f2a4bbbfa1e987313b297bcdf0d263664ea9c7'
LEGACY_CALL='actor.is_hidden()'
UE58_CALL="actor.get_editor_property('hidden')"

def test_only_two_actual_ue58_hidden_getters_changed():
    root=Path(__file__).resolve().parents[1]/'tools'
    ue58=(root/'impulse_sofa_seating_probe_ue58.py').read_text()
    assert ue58.count(LEGACY_CALL)==0
    assert ue58.count(UE58_CALL)==2
    original=ue58.replace(UE58_CALL,LEGACY_CALL)
    assert hashlib.sha256(original.encode()).hexdigest()==ORIGINAL_SHA256
