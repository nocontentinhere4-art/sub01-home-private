"""Recover the previously loaded private Editor runtime without altering migration files."""
from pathlib import Path
import concurrent.futures
import json
import os
import re
import stat
import threading
import time
import zipfile
import zlib

BASE = Path('/workspace/sub01-unreal')
SOURCE = BASE / 'UE'
DEST = Path('/workspace/sub01-private-recovered-engine')
PROJECT = Path('/workspace/sub01-home-private/project/Sub01HomeLab')
DEADLINE = 1792017655
FINAL_SOURCE_UPPER = 135441143860
QUOTA = 150000000000
RESERVE = 10000000000
MAX_RECOVERED = QUOTA - RESERVE - FINAL_SOURCE_UPPER
lock = threading.Lock()
counts = {'linked': 0, 'recovered': 0, 'recovered_bytes': 0, 'verified': 0}
local = threading.local()


def guard():
    p = Path('/run/sub01-home-private/runtime-window.json')
    s = p.stat()
    d = json.loads(p.read_text())
    assert s.st_uid == 0 and not s.st_mode & 0o022 and not p.is_symlink()
    assert d['pod'] == 'kjsxms1gk4rmv6' and d['deadline_epoch'] == DEADLINE
    assert d['total_cap'] <= 100 and d['conservative_total_upper'] <= 76
    assert d['stop_guards_authenticated'] and all(d[k] > 0 for k in
        ('root_guard_pid', 'external_guard_pid', 'second_external_guard_pid'))
    assert time.time() < DEADLINE - 120
    os.kill(d['root_guard_pid'], 0)


def crc_file(p):
    crc = size = 0
    with p.open('rb') as f:
        while data := f.read(1024 * 1024):
            crc = zlib.crc32(data, crc)
            size += len(data)
    return size, crc & 0xffffffff


def run():
    guard()
    plugins = set()
    logs = sorted((PROJECT / 'Saved/Logs').glob('*.log'),
                  key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    for p in logs:
        for line in p.open(errors='replace'):
            m = re.search(r'Mounting (?:Engine|Project) plugin (\S+)', line)
            if m:
                plugins.add(m.group(1))
    assert len(plugins) >= 200, 'Actual previous plugin evidence unavailable'
    manifest = {}
    for line in (BASE / 'engine-runtime-manifest.jsonl').open():
        e = json.loads(line)
        manifest[e['name']] = e
    archive = BASE / 'engine-compile-safe.zip'
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
    for e in entries:
        n = e.filename
        assert not Path(n).is_absolute() and '..' not in Path(n).parts
        assert n in manifest and e.CRC == manifest[n]['crc']
        assert e.file_size == manifest[n]['size']

    def scope(n):
        # Installed runtime startup reads this authored cache before compiling
        # global shaders. It is vendor data, not an optional compiler package.
        if n == 'Engine/DerivedDataCache/Compressed.ddp':
            return True
        if n.startswith(('Engine/Binaries/', 'Engine/Build/', 'Engine/Config/',
                         'Engine/Shaders/', 'Engine/Content/')):
            return '/Source/' not in n
        if n.startswith('Engine/Platforms/Linux/'):
            return '/Source/' not in n and '/Intermediate/' not in n
        if n.startswith('Engine/Plugins/'):
            if any(x in n for x in ('/Source/', '/Intermediate/', '/Documentation/', '/Extras/')):
                return False
            return n.endswith('.uplugin') or any('/' + p + '/' in n for p in plugins)
        return False

    selected = [e for e in entries if scope(e.filename)]
    absent_bytes = sum(e.file_size for e in selected
                       if not (SOURCE / e.filename).exists())
    assert absent_bytes <= MAX_RECOVERED, 'Quota reserve refuses runtime recovery'
    DEST.mkdir(mode=0o755, exist_ok=True)
    print('RUNTIME_OVERLAY_BEGIN', len(selected), absent_bytes, MAX_RECOVERED, flush=True)

    def recover(e):
        guard()
        src, dst = SOURCE / e.filename, DEST / e.filename
        mode = e.external_attr >> 16
        dst.parent.mkdir(parents=True, exist_ok=True)
        if e.is_dir():
            dst.mkdir(exist_ok=True)
            return
        symlink = stat.S_ISLNK(mode)
        if dst.exists() or dst.is_symlink():
            actual = (len(os.readlink(dst).encode()), zlib.crc32(os.readlink(dst).encode()) & 0xffffffff) if symlink and dst.is_symlink() else crc_file(dst)
            assert actual == (e.file_size, e.CRC), 'Owned partial recovery needs explicit review'
            with lock:
                counts['verified'] += 1
            return
        matched = False
        if symlink and src.is_symlink():
            data = os.readlink(src).encode()
            matched = (len(data), zlib.crc32(data) & 0xffffffff) == (e.file_size, e.CRC)
        elif not symlink and src.is_file() and src.stat().st_size == e.file_size:
            matched = crc_file(src) == (e.file_size, e.CRC)
        if matched:
            os.link(src, dst, follow_symlinks=False)
            with lock:
                counts['linked'] += 1
                counts['verified'] += 1
        else:
            with lock:
                assert counts['recovered_bytes'] + e.file_size <= MAX_RECOVERED
                counts['recovered_bytes'] += e.file_size
            if not hasattr(local, 'archive'):
                local.archive = zipfile.ZipFile(archive)
            if symlink:
                target = local.archive.read(e).decode()
                assert not Path(target).is_absolute()
                assert os.path.commonpath([str(DEST), str((dst.parent / target).resolve())]) == str(DEST)
                dst.symlink_to(target)
            else:
                temp = dst.with_name(dst.name + '.owned-recovery-part')
                with local.archive.open(e) as f, temp.open('wb') as out:
                    while data := f.read(1024 * 1024):
                        out.write(data)
                assert crc_file(temp) == (e.file_size, e.CRC)
                temp.chmod((mode & 0o777) or 0o644)
                temp.replace(dst)
            with lock:
                counts['recovered'] += 1
                counts['verified'] += 1
        with lock:
            if counts['verified'] % 2000 == 0:
                print('RUNTIME_OVERLAY_PROGRESS', json.dumps(counts), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for _ in pool.map(recover, selected):
            pass
    guard()
    assert counts['verified'] == sum(not e.is_dir() for e in selected)
    receipt = {'pod': 'kjsxms1gk4rmv6', 'engine_root': str(DEST),
               'deadline_epoch': DEADLINE, 'source_unchanged': True,
               'scope': 'actual-previously-mounted-editor-runtime',
               'compiler_complete': False, 'counts': counts,
               'final_source_upper_bytes': FINAL_SOURCE_UPPER,
               'quota_bytes': QUOTA, 'reserve_bytes': RESERVE,
               'selected_entries': len(selected), 'plugins': sorted(plugins),
               'all_selected_runtime_crc_verified': True}
    (DEST / 'private-runtime-recovery-receipt.json').write_text(json.dumps(receipt, indent=2))
    print('RUNTIME_OVERLAY_PASS', json.dumps(receipt), flush=True)


if __name__ == '__main__':
    run()
