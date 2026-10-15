import importlib.util
import os
from pathlib import Path
import struct
import pytest

P=Path(__file__).resolve().parents[1]/'tools/anyps5_home_adapter.py'
spec=importlib.util.spec_from_file_location('anyps5_home_adapter',P);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def elf(path,kind=2,machine=62):
 raw=bytearray(64);raw[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',raw,16,kind,machine);path.write_bytes(raw);return path

def evidence():
 common={'product':'anyps5','upstream_commit':a.COMMIT,'privacy':False,'captured_utc':100.,'native_pid':7,'native_start_ticks':8,'title_pid':9,'title_start_ticks':10,'frame_id':'a'*24}
 return ({**common,'schema':'sub01.anyps5-native-tv-focus.v1','mode':'manual','focused':True,'surface_tag':'SUB01Device:tv','surface_unique':True,'ray_distance_cm':120}, {**common,'painted_on_native_tv':True})

def test_real_elf_header_and_required_bundle_layout(tmp_path):
 source=elf(tmp_path/'input.elf');(tmp_path/'sce_module').mkdir();elf(tmp_path/'sce_module/test.elf',3)
 runtime=tmp_path/'runtime';(runtime/'libs').mkdir(parents=True);elf(runtime/'libs/test.prx',3);elf(runtime/'app.elf');(runtime/'app0').mkdir();(runtime/'app0/eboot.bin').write_bytes(b'original')
 result=a.inspect_title(source,runtime,a.REQUIRED_CPU)
 assert result['prerequisites_pass'] and result['bundled_modules'][0]['machine']=='x86_64'
 assert result['native_ready']is False and result['title_execution_verified']is False

@pytest.mark.parametrize('magic',[b'SELF',b'\x4f\x15\x3d\x1d',b'MZ',b'\x7fELF\x01\x01'])
def test_encrypted_or_wrong_binary_cannot_become_clean_elf(tmp_path,magic):
 p=tmp_path/'eboot.bin';p.write_bytes(magic+b'\0'*64)
 with pytest.raises(ValueError):a.elf_kind(p)


def test_incomplete_bundle_reports_blockers_without_ready_claim(tmp_path):
 p=elf(tmp_path/'input.elf');row=a.inspect_title(p)
 assert not row['prerequisites_pass'] and len(row['blockers'])==3 and not row['native_ready']

@pytest.mark.parametrize('which,key,value',[(0,'product','minecraft'),(1,'product','minecraft'),(0,'privacy',True),(1,'privacy',None),(0,'captured_utc',98),(1,'captured_utc',float('nan')),(0,'mode','live'),(0,'focused',False),(0,'native_pid',999),(1,'title_pid',999),(0,'surface_unique',False),(0,'ray_distance_cm',201),(1,'painted_on_native_tv',False),(1,'frame_id','b'*24),(0,'upstream_commit','wrong')])
def test_native_actual_focus_privacy_frame_identity_are_strict(which,key,value):
 pair=list(evidence());pair[which][key]=value
 with pytest.raises(ValueError):a.validate_focus(*pair,(7,8),(9,10),100.1)


def test_actual_fresh_manual_focus_qualifies_only_receipt_not_gameplay():
 a.validate_focus(*evidence(),(7,8),(9,10),100.1)
 assert a.encode_pulse(12,'cross',200,(255,0),(128,128))==b'12 16384 200 255 0 128 128\n'

@pytest.mark.parametrize('kwargs',[{'hold_ms':501},{'hold_ms':True},{'left':(0,256)},{'right':(True,128)},{'button':'exec'},{'sequence':0}])
def test_unbounded_or_arbitrary_pad_commands_refused(kwargs):
 with pytest.raises(ValueError):a.encode_pulse(**{'sequence':1,**kwargs})


def test_atomic_owner_only_command_monotonic_sequence_and_neutral_release(tmp_path,monkeypatch):
 tmp_path.chmod(0o700);monkeypatch.setattr(a,'_window_live',lambda now:None);monkeypatch.setattr(a,'_processes_live',lambda *args:None)
 r,f=evidence();first=a.write_pulse(tmp_path,r,f,(7,8),(9,10),button='cross',hold_ms=200,now=100.1)
 second=a.write_pulse(tmp_path,r,f,(7,8),(9,10),now=100.1)
 assert second['queued_sequence']>first['queued_sequence']
 assert (tmp_path/'anyps5-pad-command').read_text().split()[1:]==['0','1','128','128','128','128']
 assert (tmp_path/'anyps5-pad-command').stat().st_mode&0o777==0o600
 assert not second['execution_acknowledged'] and not second['native_ready']
 tmp_path.chmod(0o755)
 with pytest.raises(ValueError):a.write_pulse(tmp_path,r,f,(7,8),(9,10),now=100.1)


def test_symlink_command_cannot_redirect_writes(tmp_path,monkeypatch):
 tmp_path.chmod(0o700);monkeypatch.setattr(a,'_window_live',lambda now:None);monkeypatch.setattr(a,'_processes_live',lambda *args:None)
 outside=tmp_path/'other';outside.write_text('unchanged');(tmp_path/'anyps5-pad-command').symlink_to(outside)
 with pytest.raises(ValueError):a.write_pulse(tmp_path,*evidence(),(7,8),(9,10),now=100.1)
 assert outside.read_text()=='unchanged'


def test_intent_translation_does_not_infer_or_send_brain_actions():
 assert a.pulse_for_intent({'button':'cross','left_stick':[128,0]})=={'button':'cross','hold_ms':250,'left':(128,0),'right':(128,128)}
 with pytest.raises(ValueError):a.pulse_for_intent({'command':'run arbitrary code'})


def test_runtime_placeholders_cannot_qualify_real_layout(tmp_path):
 source=elf(tmp_path/'input.elf');(tmp_path/'prx').mkdir();runtime=tmp_path/'runtime';(runtime/'libs').mkdir(parents=True);(runtime/'libs/fake.prx').write_bytes(b'placeholder');(runtime/'app0').mkdir();(runtime/'app0/eboot.bin').write_bytes(b'original')
 result=a.inspect_title(source,runtime,a.REQUIRED_CPU)
 assert not result['runtime_layout_present'] and not result['prerequisites_pass']
