from pathlib import Path
import hashlib

def test_only_two_actual_ue58_hidden_getters_changed():
    root=Path(__file__).resolve().parents[1]/'tools'
    source=(root/'impulse_sofa_seating_probe.py').read_text()
    assert hashlib.sha256(source.encode()).hexdigest()=='a9a06d79f9e08ba9e8fac87326f2a4bbbfa1e987313b297bcdf0d263664ea9c7'
    assert source.count('actor.is_hidden()')==2
    assert (root/'impulse_sofa_seating_probe_ue58.py').read_text()==source.replace('actor.is_hidden()',"actor.get_editor_property('hidden')")
