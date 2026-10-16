import importlib.util, pathlib, os, time, hashlib, pytest
spec=importlib.util.spec_from_file_location('coherent',pathlib.Path(__file__).parents[1]/'tools/coherent_atomic_snapshot.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_rename_during_copy_keeps_pinned_saved_bytes(tmp_path,monkeypatch):
    source=tmp_path/'state';source.write_bytes(b'A'*(2*1024*1024));dest=tmp_path/'copy';real=hashlib.sha256;changed=False
    class Digest:
        def __init__(self,data=b''):self.inner=real(data)
        def update(self,data):
            nonlocal changed
            self.inner.update(data)
            if not changed:
                changed=True
                newer=tmp_path/'new';newer.write_bytes(b'B'*(2*1024*1024));newer.replace(source)
        def hexdigest(self):return self.inner.hexdigest()
    monkeypatch.setattr(m.hashlib,'sha256',Digest)
    result=m.copy_snapshot(source,dest,time.time())
    assert result['pathname_replaced_after_open'] and result['source_fd_unchanged_through_copy']
    assert dest.read_bytes()==b'A'*(2*1024*1024) and source.read_bytes()==b'B'*(2*1024*1024)
def test_in_place_mutation_refuses(tmp_path,monkeypatch):
    source=tmp_path/'state';source.write_bytes(b'A'*(2*1024*1024));real=os.fstat;calls=0
    def stat(fd):
        nonlocal calls
        calls+=1
        if calls==2:
            with source.open('r+b')as f:f.write(b'Z')
        return real(fd)
    monkeypatch.setattr(m.os,'fstat',stat)
    with pytest.raises(AssertionError,match='mutated in place'):m.copy_snapshot(source,tmp_path/'copy',time.time())
