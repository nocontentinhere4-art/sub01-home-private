"""Source-pinned AnyPS5 preflight and opt-in local pad-file adapter.

This does not launch titles, acquire TV focus, grant native readiness, or provide
PS5 game files. Its frame/focus receipt must come from a future genuine capture
adapter; today's Minecraft receipt cannot qualify. No network listener is added.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import time

UPSTREAM = 'https://github.com/boykopovar/AnyPS5'
COMMIT = '2e5dd5aa144af1bf90a214a6341bf3e1b4e6d47a'
BUTTONS = {'l3':2,'r3':4,'options':8,'up':16,'right':32,'down':64,'left':128,
           'l2':256,'r2':512,'l1':1024,'r1':2048,'triangle':4096,'circle':8192,
           'cross':16384,'square':32768,'touchpad':1048576,'release':0}
REQUIRED_CPU = frozenset(('avx2','fma','f16c','bmi1','bmi2','lzcnt','movbe'))
MAX_PULSE_MS = 500  # Upstream accepts 5000; house lease intentionally shorter.


def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def elf_kind(path):
    """Reject encrypted/SELF/PE inputs; inspect actual ELF identity, not suffix."""
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('Regular non-symlink ELF required')
    with path.open('rb') as stream:header=stream.read(64)
    if len(header)<64 or header[:6]!=b'\x7fELF\x02\x01':raise ValueError('Clean little-endian ELF64 required; SELF is not accepted')
    kind,machine=struct.unpack_from('<HH',header,16)
    if machine!=62 or kind not in (2,3,0xfe00,0xfe10,0xfe18):raise ValueError('x86-64 executable or bundled ELF module required')
    return {'machine':'x86_64','elf_type':kind,'bytes':path.stat().st_size}


def inspect_title(source, runtime=None, cpu_flags=()):
    """Read-only readiness inventory; conversion/launch success stays unclaimed."""
    source=Path(source);errors=[];modules=[]
    try:identity=elf_kind(source)
    except (OSError,ValueError) as error:identity=None;errors.append(str(error))
    parent=source.parent
    dirs=[name for name in ('sce_module','sce_modules','prx') if (parent/name).is_dir()]
    if not dirs or {'sce_module','sce_modules'}<=set(dirs):errors.append('Exactly one sce_module/sce_modules directory, optionally prx, or prx alone required')
    for name in dirs:
        for f in sorted((parent/name).iterdir()):
            if f.is_file():
                try:modules.append({'relative':str(f.relative_to(parent)),**elf_kind(f)})
                except ValueError as error:errors.append(f'{name}/{f.name}: {error}')
    flags=set(cpu_flags)
    if 'abm' in flags:flags.add('lzcnt')  # Linux names CPUID ABM/LZCNT this way.
    missing=sorted(REQUIRED_CPU-flags)
    if missing:errors.append('Host CPU extensions not verified: '+','.join(missing))
    runtime_ok=False
    if runtime is not None:
        runtime=Path(runtime);libs=runtime/'libs';libraries=sorted(libs.glob('*.prx')) if libs.is_dir() else []
        runtime_errors=[]
        try:
            if elf_kind(runtime/'app.elf')['elf_type'] not in (2,3):raise ValueError('Converted Linux executable required')
        except (OSError,ValueError) as error:runtime_errors.append(str(error))
        if not libraries or len(libraries)>1024:runtime_errors.append('Bounded built Linux libs/*.prx required')
        for library in libraries[:1024]:
            try:
                if elf_kind(library)['elf_type']!=3:raise ValueError('Built Linux shared PRX required')
            except (OSError,ValueError) as error:runtime_errors.append(str(error))
        if not (runtime/'app0/eboot.bin').is_file():runtime_errors.append('Original app0/eboot.bin/resources required')
        runtime_ok=not runtime_errors;errors.extend(runtime_errors)
    else:errors.append('No converted title runtime supplied')
    return {'schema':'sub01.anyps5-source-preflight.v1','upstream':UPSTREAM,'commit':COMMIT,
            'source_elf':identity,'bundled_modules':modules,'runtime_layout_present':runtime_ok,
            'blockers':errors,'prerequisites_pass':not errors,'title_execution_verified':False,
            'tv_current_frame_verified':False,'native_ready':False,'physical_controller_contact_accepted':False}


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def validate_focus(receipt, frame, native_identity, title_identity, now):
    """Never accepts Minecraft frames, stale focus, guessed PIDs, or Live poses."""
    if not finite(now):raise ValueError('Finite clock required')
    if not isinstance(receipt,dict) or not isinstance(frame,dict):raise ValueError('Actual frame and focus required')
    for row in (receipt,frame):
        if row.get('product')!='anyps5' or row.get('upstream_commit')!=COMMIT:raise ValueError('Exact genuine AnyPS5 product required')
        if row.get('privacy') is not False:raise ValueError('Fresh public privacy required')
        captured=row.get('captured_utc')
        if not finite(captured) or not -.25<=now-captured<=.5:raise ValueError('Fresh actual frame/focus required')
        if [row.get('native_pid'),row.get('native_start_ticks')]!=list(native_identity):raise ValueError('Exact native identity required')
        if [row.get('title_pid'),row.get('title_start_ticks')]!=list(title_identity):raise ValueError('Exact title identity required')
    if receipt.get('schema')!='sub01.anyps5-native-tv-focus.v1' or receipt.get('mode')!='manual' or receipt.get('focused') is not True:raise ValueError('Genuine Manual physical TV focus required; Live is not enabled')
    if receipt.get('surface_tag')!='SUB01Device:tv' or receipt.get('surface_unique') is not True:raise ValueError('Unique actual TV ray required')
    ray=receipt.get('ray_distance_cm')
    if not finite(ray) or not 0<ray<=200:raise ValueError('Actual TV ray within existing range required')
    frame_id=frame.get('frame_id')
    if not isinstance(frame_id,str) or not re.fullmatch('[0-9a-f]{24,64}',frame_id) or receipt.get('frame_id')!=frame_id:raise ValueError('Current painted title frame correlation required')
    if frame.get('painted_on_native_tv') is not True:raise ValueError('Actual painted TV frame required')


def encode_pulse(sequence, button='release', hold_ms=1, left=(128,128), right=(128,128)):
    """Exact seven-integer upstream InputCommandFile format, no shell strings."""
    if type(sequence)is not int or not 1<=sequence<2**64:raise ValueError('Positive uint64 sequence required')
    if button not in BUTTONS:raise ValueError('Known pad button required')
    if type(hold_ms)is not int or not 1<=hold_ms<=MAX_PULSE_MS:raise ValueError('Bounded 1..500 ms pulse required')
    axes=tuple(left)+tuple(right)
    if len(axes)!=4 or any(type(x)is not int or not 0<=x<=255 for x in axes):raise ValueError('Four integer stick axes 0..255 required')
    return (f'{sequence} {BUTTONS[button]} {hold_ms} '+' '.join(map(str,axes))+'\n').encode('ascii')


def _processes_live(native_identity, title_identity):
    if tuple(native_identity)==tuple(title_identity):raise ValueError('Separate actual title process required')
    for role,identity in (('native',native_identity),('title',title_identity)):
        if len(identity)!=2 or any(type(x)is not int or x<=0 for x in identity):raise ValueError('Positive process identity required')
        proc=Path('/proc')/str(identity[0]);fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
        if fields[0]=='Z' or int(fields[19])!=identity[1] or proc.stat().st_uid!=os.geteuid():raise ValueError('Live owned exact process identity required')
        exe=os.readlink(proc/'exe')
        native='/workspace/sub01-private-recovered-engine/Engine/Binaries/Linux/UnrealEditor-Cmd'
        if (role=='native')!=(exe==native):raise ValueError('Actual separate native/title executable required')


def _window_live(now):
    path=Path('/run/sub01-home-private/runtime-window.json');info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Trusted runtime window required')
    row=json.loads(path.read_text())
    if row.get('pod')!='dgtgepkz7h1zy5' or row.get('stop_guards_authenticated')is not True or not finite(row.get('deadline_epoch')) or now>=row['deadline_epoch'] or not finite(row.get('total_cap')) or not 0<row['total_cap']<=100:raise ValueError('Live authenticated budget window required')


def pulse_for_intent(intent):
    """Pure bounded translation only; does not infer or generate brain actions."""
    if not isinstance(intent,dict) or set(intent)-{'button','hold_ms','left_stick','right_stick'}:raise ValueError('Bounded explicit pad intent required')
    button=intent.get('button','release');hold=intent.get('hold_ms',250);left=intent.get('left_stick',(128,128));right=intent.get('right_stick',(128,128))
    encode_pulse(1,button,hold,left,right)
    return {'button':button,'hold_ms':hold,'left':tuple(left),'right':tuple(right)}


def write_pulse(private_dir, receipt, frame, native_identity, title_identity, *, button='release',hold_ms=1,left=(128,128),right=(128,128),now=None):
    """Owner-only, atomic, serialized local file; caller must pin live process identities.

    No default input file is enabled in production. Current budget window and
    both kernel process identities are independently checked before each pulse.
    """
    import fcntl
    now=time.time() if now is None else now
    validate_focus(receipt,frame,native_identity,title_identity,now)
    _window_live(now);_processes_live(native_identity,title_identity)
    root=Path(private_dir);info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:raise ValueError('Owner-only private directory required')
    path=root/'anyps5-pad-command';lock=root/'anyps5-pad.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'a+b') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            previous=0
            if path.exists() or path.is_symlink():
                s=path.lstat()
                if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode&0o077:raise ValueError('Owned non-symlink command file required')
                if s.st_size>128:raise ValueError('Bounded command file required')
                raw=path.read_bytes()
                if len(raw)>128:raise ValueError('Bounded command file required')
                parts=raw.split()
                if parts:previous=int(parts[0])
            seq=max(time.monotonic_ns(),previous+1);raw=encode_pulse(seq,button,hold_ms,left,right)
            tmp=None
            try:
                with tempfile.NamedTemporaryFile(dir=root,delete=False) as out:
                    tmp=Path(out.name);os.fchmod(out.fileno(),0o600);out.write(raw);out.flush();os.fsync(out.fileno())
                os.replace(tmp,path)
            finally:
                if tmp is not None:tmp.unlink(missing_ok=True)
    except BaseException:raise
    return {'queued_sequence':seq,'expires_after_read_ms':hold_ms,'execution_acknowledged':False,'native_ready':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source_elf',type=Path);parser.add_argument('--runtime',type=Path);parser.add_argument('--cpu-flags',default='')
    args=parser.parse_args();print(json.dumps(inspect_title(args.source_elf,args.runtime,args.cpu_flags.split()),indent=2))


if __name__=='__main__':main()
