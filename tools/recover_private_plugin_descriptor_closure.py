"""Resolve prior runtime plugins by their authenticated descriptors, not folder guesses."""
from pathlib import Path
import concurrent.futures
import json
import os
import shutil
import time
import urllib.request
import zlib

BASE = Path('/workspace/sub01-unreal')
DEST = Path('/workspace/sub01-private-recovered-engine')
DEADLINE = 1792017655


def descriptor_json(text):
    # Unreal descriptors permit comments and trailing commas. Preserve strings;
    # this is data parsing only, with no expression evaluation.
    out = []
    i = 0
    quoted = escaped = False
    while i < len(text):
        c = text[i]
        if quoted:
            out.append(c)
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
            i += 1
            continue
        if c == '"':
            quoted = True
        elif text[i:i + 2] == '//':
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
            continue
        elif text[i:i + 2] == '/*':
            end = text.find('*/', i + 2)
            assert end >= 0
            i = end + 2
            continue
        out.append(c)
        i += 1
    clean = ''.join(out)
    out = []
    quoted = escaped = False
    for i, c in enumerate(clean):
        if quoted:
            out.append(c)
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
            continue
        if c == '"':
            quoted = True
        if c == ',' and clean[i + 1:].lstrip().startswith(('}', ']')):
            continue
        out.append(c)
    return json.loads(''.join(out))


def crc(p):
    size = value = 0
    with p.open('rb') as f:
        while b := f.read(1024 * 1024):
            value = zlib.crc32(b, value)
            size += len(b)
    return size, value & 0xffffffff


def run():
    window = json.loads(Path('/run/sub01-home-private/runtime-window.json').read_text())
    assert window['pod'] == 'kjsxms1gk4rmv6' and window['deadline_epoch'] == DEADLINE
    assert window['stop_guards_authenticated'] and time.time() + 600 < DEADLINE
    receipt = json.loads((DEST / 'private-runtime-recovery-receipt.json').read_text())
    entries = {}
    for line in (BASE / 'engine-runtime-manifest.jsonl').open():
        e = json.loads(line)
        n = e['name']
        if n.endswith(('.debug', '.sym', '.pdb')) or any('/Binaries/' + a + '/' in n
                for a in ('Win64', 'Mac', 'Android', 'IOS', 'LinuxArm64')):
            continue
        entries[n] = e
    descriptors = {}
    descriptor_parents = []
    ordered = sorted(entries.items(), key=lambda item: (len(Path(item[0]).parts), item[0]))
    for name, e in ordered:
        if name.startswith('Engine/Plugins/') and name.endswith('.uplugin') and not any(x in name for x in ('/Source/', '/Intermediate/')):
            parent = str(Path(name).parent)
            if any(parent.startswith(old + '/') for old in descriptor_parents):
                continue
            descriptor_parents.append(parent)
            p = DEST / name
            assert crc(p) == (e['size'], e['crc'])
            key = p.stem.lower()
            assert key not in descriptors, 'Ambiguous plugin descriptor'
            descriptors[key] = (name, descriptor_json(p.read_text(encoding='utf-8-sig')))
    required = {n.lower() for n in receipt['plugins']}
    project = Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/Sub01HomeLab.uproject')
    for p in json.loads(project.read_text()).get('Plugins', []):
        if p.get('Enabled') is True:
            required.add(p['Name'].lower())
    # Default-enabled, Linux-supported descriptors are actual startup requirements.
    for key, (_, d) in descriptors.items():
        platforms = d.get('SupportedTargetPlatforms')
        if d.get('EnabledByDefault') is True and (not platforms or 'Linux' in platforms):
            required.add(key)
    pending = list(required)
    while pending:
        key = pending.pop()
        assert key in descriptors, 'Prior plugin descriptor absent: ' + key
        for p in descriptors[key][1].get('Plugins', []):
            if p.get('Enabled') is not True or ('PlatformAllowList' in p and 'Linux' not in p['PlatformAllowList']) or 'Linux' in p.get('PlatformDenyList', []):
                continue
            dependency = p['Name'].lower()
            if dependency not in required:
                required.add(dependency)
                pending.append(dependency)
    prefixes = [str(Path(descriptors[k][0]).parent) + '/' for k in sorted(required)]
    selected = []
    for n, e in entries.items():
        if any(n.startswith(p) for p in prefixes) and not any(x in n for x in
                ('/Source/', '/Intermediate/', '/Documentation/', '/Extras/')):
            selected.append(e)
    missing = [e for e in selected if not (DEST / e['name']).is_file()]
    bytes_needed = sum(e['size'] for e in missing)
    assert bytes_needed <= 1500000000, 'Descriptor closure exceeds bounded recovery'
    print('DESCRIPTOR_CLOSURE_BEGIN', len(required), len(selected), len(missing), bytes_needed, flush=True)
    cfg = json.loads(Path('/root/.sub01-home-private/office-source-fetch.json').read_text())
    token = cfg['source_token']
    source_base = cfg['source_base'].rstrip('/')
    assert source_base == 'https://5ldnm4vax9kelh-8888.proxy.runpod.net'

    def recover(e):
        assert time.time() < DEADLINE - 120
        name = e['name']
        dst = DEST / name
        if dst.is_file():
            assert crc(dst) == (e['size'], e['crc'])
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = BASE / 'UE' / name
        if src.is_file() and src.stat().st_size == e['size'] and crc(src) == (e['size'], e['crc']):
            os.link(src, dst)
            return
        url = source_base + '/files/workspace/sub01-unreal/UE/' + name
        req = urllib.request.Request(url, headers={'Authorization': 'token ' + token,
                                                   'User-Agent': 'Mozilla/5.0'})
        temp = dst.with_name(dst.name + '.owned-descriptor-recovery')
        with urllib.request.urlopen(req, timeout=45) as response, temp.open('wb') as f:
            while b := response.read(4 * 1024 * 1024):
                f.write(b)
        assert crc(temp) == (e['size'], e['crc'])
        temp.chmod((e.get('mode', 0) & 0o777) or 0o644)
        temp.replace(dst)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, _ in enumerate(pool.map(recover, selected), 1):
            if i % 5000 == 0:
                print('DESCRIPTOR_CLOSURE_CRC_PROGRESS', i, flush=True)
    output = {'pod': window['pod'], 'engine_root': str(DEST), 'deadline_epoch': DEADLINE,
              'required_plugins': sorted(required), 'descriptor_prefixes': prefixes,
              'selected_entries': len(selected), 'initial_missing_count': len(missing),
              'initial_missing_bytes': bytes_needed, 'all_selected_crc_verified': True,
              'source_unchanged': True, 'compiler_complete': False}
    (DEST / 'private-plugin-descriptor-recovery-receipt.json').write_text(json.dumps(output, indent=2))
    print('DESCRIPTOR_CLOSURE_PASS', len(required), len(selected), bytes_needed, flush=True)


if __name__ == '__main__':
    run()
