"""Compiler-closure check of the native adapters bundle on freshly staged sources (source only; private; no engine).

Root runs this before the next native build:

    python3 tools/check_native_adapters_compile_closure.py [--staging-ref origin/main] [--json PATH] [--keep DIR]

1. Stages a scratch project exactly as root does (tools/stage_unreal_home_runtime.stage(), the same call the bundle
   tests use; with --staging-ref the staging inputs -- tools/ and the root-level *.py -- are taken from that git ref,
   and the report says whether that ref's staged module is byte-identical to this checkout's), then installs the full
   bundle (tools/install_native_adapters_bundle.py: seat -> life -> bed -> controller) and, after it, the controller
   grip contact analyzer (tools/unreal_controller_grip_contact_native.py), in memory and then into the scratch copy.
2. Static closure over what the install added: every anchor unique; every #include resolves to a staged file, a
   *.generated.h of a staged header, a UE header the freshly staged (pre-install) module already includes (the
   allowlist is derived, not hand-written) or a C++ standard header; every insertion and every added top-level item
   is brace-balanced; no definition is duplicated anywhere in the module (and no file-static helper repeats across
   .cpp files, which a unity build would merge); every method an adapter declares is defined exactly once and every
   one it defines is declared; every Sub01* name the added code uses is defined in the module; no inserted statement
   redeclares a local of the root function it lands in; UFUNCTION/UPROPERTY types added are ones root already uses
   in reflected declarations (UnrealHeaderTool is not run: other types are reported, not failed).
3. Compiles with a stub UE shim (tools/native_adapters_ue_shim.py), g++ and clang++ (when present), -std=c++20
   -fsyntax-only -Wall -Werror -Wshadow (clang with UE's Linux warning set): the two adapter headers with every
   engine-free staged header; the whole installed Sub01HomeLab.h class plus every top-level item the adapters append
   to Sub01HomeLab.cpp, plus each statement block they insert into a root function compiled as a probe member with
   that function's parameters and the locals it uses (#line keeps diagnostics on the staged file's lines); the whole
   installed Sub01HomeHands.h, the whole FSub01HandsProxy (root's struct with the inserted lines) and the appended
   grip analyzer, with WITH_EDITOR 0 and 1. Root's own function bodies are not compiled (only the lines inserted into
   them), and engine APIs are checked only against the stub signatures.

Exit 0 when everything passes, 1 on any failure, 2 when the bundle refuses to install. Nothing is written outside a
temporary directory (or --keep DIR); no evidence, receipt or readiness file is produced for the real project.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import install_native_adapters_bundle as bundle  # noqa: E402
import native_adapters_ue_shim as shim  # noqa: E402
import unreal_controller_grip_contact_native as grip  # noqa: E402

CLASS = 'ASub01HomeCharacter'
CPP, HEADER, HANDS_H, HANDS_CPP = 'Sub01HomeLab.cpp', 'Sub01HomeLab.h', 'Sub01HomeHands.h', 'Sub01HomeHands.cpp'
PROXY = 'struct FSub01HandsProxy'
ADAPTER_HEADERS = ('Sub01SeatTransition.h', 'Sub01LifeClips.h')
# UE's Linux clang warning set (ClangToolChain): -Wall -Werror with these relaxations, and shadowing as an error.
CLANG_FLAGS = ['-Wall', '-Werror', '-Wshadow', '-Wundef', '-Wdelete-non-virtual-dtor', '-Wenum-conversion',
               '-Wno-switch', '-Wno-tautological-compare', '-Wno-unknown-pragmas', '-Wno-unused-function',
               '-Wno-unused-lambda-capture', '-Wno-unused-local-typedef', '-Wno-unused-private-field',
               '-Wno-unused-variable', '-Wno-invalid-offsetof', '-Wno-inconsistent-missing-override']
GCC_FLAGS = ['-Wall', '-Werror', '-Wshadow', '-Werror=shadow', '-Wundef', '-Wno-switch', '-Wno-unknown-pragmas',
             '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-local-typedefs',
             '-Wno-misleading-indentation', '-Wno-sign-compare']  # clang's -Wall has neither
DECL_TYPES = r'(?:bool|int|int32|uint32|int64|uint64|uint8|float|double|FString|FName|FVector|FVector2D|FRotator|FQuat|FTransform|FBox|auto)'


class Refused(Exception):
    pass


# ---------------------------------------------------------------------------------------------- C++ text helpers
def strip(text: str) -> str:
    """Comments and string/char literal contents become spaces (newlines kept), so braces and names can be scanned."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                out[i] = ' '
                i += 1
        elif c == '/' and i + 1 < n and text[i + 1] == '*':
            end = text.find('*/', i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                if text[k] != '\n':
                    out[k] = ' '
            i = end
        elif c == 'R' and i + 1 < n and text[i + 1] == '"' and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == '_')):
            open_paren = text.find('(', i + 2)
            delim = text[i + 2:open_paren]
            end = text.find(')' + delim + '"', open_paren)
            end = n if end < 0 else end + len(delim) + 2
            for k in range(i + 1, end):
                if text[k] != '\n':
                    out[k] = ' '
            i = end
        elif c in '"\'':
            k = i + 1
            while k < n and text[k] != c:
                if text[k] == '\\':
                    out[k] = ' '
                    k += 1
                if k < n and text[k] != '\n':
                    out[k] = ' '
                k += 1
            i = k + 1
        else:
            i += 1
    return ''.join(out)


def line_depths(text: str) -> list:
    """Brace depth at the start of each line (on stripped text)."""
    depths, depth = [], 0
    for line in strip(text).split('\n'):
        depths.append(depth)
        depth += line.count('{') - line.count('}')
    return depths


def brace_walk(stripped: str):
    """(final depth, minimum depth reached) of a code fragment."""
    depth = low = 0
    for c in stripped:
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            low = min(low, depth)
    return depth, low


def top_level_items(text: str, base_line: int = 1) -> list:
    """Split text at depth 0 into items: preprocessor lines, declarations ending in ';', definitions ending in '}'."""
    s = strip(text)
    items, depth, start, i, n = [], 0, 0, 0, len(s)
    while i < n:
        c = s[i]
        if depth == 0 and c == '#' and s[start:i].strip() == '':
            end = s.find('\n', i)
            end = n if end < 0 else end
            items.append(_item(text, s, i, end, base_line, 'preprocessor'))
            start = i = end
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                rest = s[end:]
                if rest.lstrip(' \t').startswith(';'):
                    end += len(rest) - len(rest.lstrip(' \t')) + 1
                items.append(_item(text, s, start, end, base_line, 'definition'))
                start = i = end
                continue
            if depth < 0:
                items.append(_item(text, s, start, i + 1, base_line, 'unbalanced'))
                depth, start = 0, i + 1
        elif c == ';' and depth == 0:
            items.append(_item(text, s, start, i + 1, base_line, 'declaration'))
            start = i + 1
        i += 1
    if s[start:].strip():
        items.append(_item(text, s, start, n, base_line, 'unterminated' if depth else 'trailing'))
    return items


def _item(text, s, start, end, base_line, kind):
    while start < end and s[start] in ' \t\n':
        start += 1
    head = s[start:end].split('{', 1)[0]
    name = None
    if kind == 'definition':
        m = re.search(r'([A-Za-z_]\w*(?:::~?[A-Za-z_]\w*)*)\s*\(([^{]*)\)\s*(?:const\s*)?(?:override\s*)?$', head.strip())
        if m and '=' not in head.split('(')[0]:
            name = m.group(1)
        else:
            m = re.search(r'\b(?:struct|class)\s+(?:\w+_API\s+)?(\w+)', head)
            name = m.group(1) if m else None
    return {'kind': kind, 'start': start, 'end': end, 'line': base_line + text.count('\n', 0, start),
            'end_line': base_line + text.count('\n', 0, end), 'text': text[start:end], 'head': ' '.join(head.split()),
            'name': name, 'params': _params(head) if kind == 'definition' and name and '(' in head else None}


def _params(head: str) -> str:
    inner = head[head.index('(') + 1:head.rindex(')')] if ')' in head else ''
    return ' '.join(inner.split())


def split_params(params: str) -> list:
    """[(type, name)] of a parameter list (defaults dropped)."""
    out, depth, cur = [], 0, ''
    for c in params:
        if c in '<(':
            depth += 1
        elif c in '>)':
            depth -= 1
        if c == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += c
    if cur.strip():
        out.append(cur)
    result = []
    for p in out:
        p = p.split('=')[0].strip()
        m = re.match(r'(.*?)(\w+)\s*(\[\d*\])?$', p)
        if m and m.group(1).strip():
            result.append((m.group(1).strip(), m.group(2)))
    return result


def identifiers(text: str) -> set:
    return set(re.findall(r'\b[A-Za-z_]\w*\b', strip(text)))


def includes(text: str) -> list:
    return [(m.group(1), m.group(2)) for m in re.finditer(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', text, re.M)]


# ---------------------------------------------------------------------------------------------- staging + install
def stage_project(project: Path, staging_ref=None) -> dict:
    """Stage project/Source/Sub01HomeLab as root does; with staging_ref, from that git ref's staging inputs."""
    project = Path(project)
    (project / 'Config').mkdir(parents=True, exist_ok=True)
    (project / 'Sub01HomeLab.uproject').write_text('{}')
    info = {'staging': 'this checkout (tools/stage_unreal_home_runtime.stage)'}
    if staging_ref is None:
        from stage_unreal_home_runtime import stage
        stage(project)
        return info
    with tempfile.TemporaryDirectory(prefix='sub01-staging-ref-') as tmp:
        names = subprocess.run(['git', '-C', str(REPO), 'ls-tree', '--name-only', staging_ref], capture_output=True, text=True)
        if names.returncode:
            raise Refused(f'staging ref {staging_ref!r} not found: {names.stderr.strip()}')
        roots = [n for n in names.stdout.split() if n.endswith('.py')] + ['tools']
        archive = subprocess.run(['git', '-C', str(REPO), 'archive', staging_ref, *roots], capture_output=True)
        if archive.returncode:
            raise Refused(f'git archive {staging_ref} failed: {archive.stderr.decode()[:300]}')
        subprocess.run(['tar', '-x', '-C', tmp], input=archive.stdout, check=True)
        code = ('import sys;sys.path[:0]=[sys.argv[1]+"/tools",sys.argv[1]];'
                'from stage_unreal_home_runtime import stage;stage(sys.argv[2])')
        run = subprocess.run([sys.executable, '-c', code, tmp, str(project)], capture_output=True, text=True, cwd=tmp)
        if run.returncode:
            raise Refused(f'staging from {staging_ref} failed: {run.stderr[-500:]}')
    commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', staging_ref], capture_output=True, text=True).stdout.strip()
    info = {'staging': f'{staging_ref} ({commit[:12]}) staging inputs', 'staging_commit': commit}
    with tempfile.TemporaryDirectory(prefix='sub01-staging-local-') as tmp:
        local = Path(tmp)
        (local / 'Config').mkdir()
        (local / 'Sub01HomeLab.uproject').write_text('{}')
        from stage_unreal_home_runtime import stage
        stage(local)
        a, b = project / 'Source/Sub01HomeLab', local / 'Source/Sub01HomeLab'
        names_a = sorted(p.name for p in a.iterdir())
        info['identical_to_checkout_staging'] = names_a == sorted(p.name for p in b.iterdir()) and all(
            (a / n).read_bytes() == (b / n).read_bytes() for n in names_a)
    return info


def install(module: Path) -> dict:
    """Bundle (seat -> life -> bed -> controller) then the grip analyzer, into module; returns before/after texts."""
    module = Path(module)
    fresh = {p.name: p.read_text() for p in module.iterdir() if p.is_file()}
    try:
        result = bundle.plan(module)
        bundle.apply(result, module.parent / '.closure-receipt.json')
    except bundle.Refused as error:
        raise Refused(f'bundle refused: {error}') from None
    hands = {k: (module / name).read_text() for k, name in grip.SOURCE_FILES.items()}
    grip_anchor = sum(1 for line in hands['hands_header'].split('\n') if grip.HEADER_ANCHOR in line)
    try:
        after_grip = grip.install(hands)
    except ValueError as error:
        raise Refused(f'grip analyzer refused: {error}') from None
    for key, name in grip.SOURCE_FILES.items():
        (module / name).write_text(after_grip[key])
    (module.parent / '.closure-receipt.json').unlink(missing_ok=True)
    after = {p.name: p.read_text() for p in module.iterdir() if p.is_file()}
    anchors = [dict(a, adapter=s['adapter']) for s in result['steps'] for a in s['anchors']]
    anchors.append({'adapter': 'grip', 'file': HANDS_H, 'anchor': grip.HEADER_ANCHOR, 'count': grip_anchor})
    anchors.append({'adapter': 'grip', 'file': HANDS_CPP, 'anchor': grip.REQUIRED_CPP + ' (required, renderer)',
                    'count': hands['hands_cpp'].count(grip.REQUIRED_CPP)})
    return {'fresh': fresh, 'after': after, 'anchors': anchors, 'selected': result['selected'] + ['grip']}


def hunks(before: str, after: str) -> list:
    """Inserted line blocks: {'old_index', 'first' (1-based line in after), 'lines'}. The install is additive only."""
    old, new = before.split('\n'), after.split('\n')
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'insert':
            raise Refused(f'install is not additive ({tag} at old line {i1 + 1})')
        out.append({'old_index': i1, 'first': j1 + 1, 'lines': new[j1:j2]})
    return out


# ---------------------------------------------------------------------------------------------- classification
def classify(name: str, after: str, block_list: list) -> list:
    """Attach a host to each hunk: top-level (depth 0), or the top-level item (function/struct) it lands inside."""
    depths = line_depths(after)
    items = top_level_items(after)
    for h in block_list:
        h['depth'] = depths[h['first'] - 1]
        h['text'] = '\n'.join(h['lines'])
        h['stripped'] = strip(h['text'])
        h['net'], h['low'] = brace_walk(h['stripped'])
        if h['depth'] == 0:
            h['host'] = None
            h['items'] = top_level_items(h['text'], h['first'])
            continue
        host = next((it for it in items if it['line'] <= h['first'] and it['end_line'] >= h['first'] + len(h['lines']) - 1), None)
        h['host'] = host
        h['items'] = []
    return block_list


# ---------------------------------------------------------------------------------------------- static checks
def static_checks(fresh: dict, after: dict, added: dict, anchors: list) -> dict:
    problems, notes = [], []
    module_files = set(after)
    # anchors
    for a in anchors:
        if a['count'] != 1:
            problems.append(f"anchor not unique ({a['count']}x) for {a['adapter']} in {a['file']}: {a['anchor'][:80]}")
    # include allowlist derived from the freshly staged module
    fresh_ue = {name for text in fresh.values() for kind, name in includes(text) if kind == '"' and name not in fresh and not name.endswith('.generated.h')}
    fresh_std = {name for text in fresh.values() for kind, name in includes(text) if kind == '<'}
    include_report = []
    for fname, blocks in added.items():
        for h in blocks:
            for kind, name in includes(h['text']):
                if kind == '"' and name in module_files:
                    why = 'staged module file'
                elif kind == '"' and name.endswith('.generated.h') and name[:-len('.generated.h')] + '.h' == fname:
                    why = 'UHT output of this header'
                elif kind == '"' and name in fresh_ue:
                    why = 'UE header already included by the fresh staged module'
                elif kind == '<' and name in fresh_std:
                    why = 'C++ standard header already used by the fresh staged module'
                elif kind == '<' and re.fullmatch(r'[a-z_]+', name):
                    why = 'C++ standard header (new to the module)'
                    notes.append(f'{fname}:{h["first"]}: <{name}> is new to the module (standard header)')
                else:
                    why = None
                    problems.append(f'{fname}:{h["first"]}: #include {kind}{name} resolves to nothing staged and is not an allowlisted UE header')
                include_report.append({'file': fname, 'line': h['first'], 'include': name, 'resolved': why})
    # brace balance of every insertion and every added top-level item
    for fname, blocks in added.items():
        for h in blocks:
            if h['net'] != 0 or h['low'] < 0:
                problems.append(f'{fname}:{h["first"]}: inserted block is not brace-balanced (net {h["net"]}, low {h["low"]})')
            for it in h['items']:
                if it['kind'] in ('unbalanced', 'unterminated'):
                    problems.append(f'{fname}:{it["line"]}: added top-level item is {it["kind"]}: {it["head"][:80]}')
    for fname, text in after.items():
        if fname.endswith(('.h', '.cpp')):
            depth, low = brace_walk(strip(text))
            if depth or low < 0:
                problems.append(f'{fname}: whole file not brace-balanced after install (net {depth}, low {low})')
    # definitions across the module (unity builds merge every .cpp)
    defs = {}
    for fname, text in after.items():
        if not fname.endswith(('.h', '.cpp')):
            continue
        for it in top_level_items(text):
            if it['kind'] == 'definition' and it['name'] and it['params'] is not None:
                static = bool(re.match(r'\s*static\b', it['head']))
                key = (it['name'], re.sub(r'\b\w+\s*(,|$)', r'\1', it['params']).replace(' ', ''))
                defs.setdefault(key, []).append((fname, it['line'], static))
    for (name, sig), where in sorted(defs.items()):
        files = {w[0] for w in where}
        if len(where) > 1 and not all(f.endswith('.h') for f in files):
            problems.append(f'{name}({sig}) defined {len(where)}x: ' + ', '.join(f'{f}:{l}' for f, l, _ in sorted(where)))
    # adapter-declared class methods: defined exactly once; adapter-defined methods: declared
    declared = class_methods(after[HEADER], CLASS)
    added_decls = set()
    for h in added.get(HEADER, []):
        added_decls |= declared_functions(h['text'])
    hands_declared = class_methods(after[HANDS_H], 'USub01HomeHandsInstance')
    for h in added.get(HANDS_H, []):
        added_decls |= {f'USub01HomeHandsInstance::{n}' for n in declared_functions(h['text'])}
    defined = {}
    for (name, _), where in defs.items():
        defined.setdefault(name, []).extend(where)
    for method in sorted(added_decls):
        qualified = method if '::' in method else f'{CLASS}::{method}'
        if len(defined.get(qualified, [])) != 1:
            problems.append(f'{qualified} is declared by an adapter but defined {len(defined.get(qualified, []))} times')
    for fname, blocks in added.items():
        for h in blocks:
            for it in h['items']:
                if it['name'] and '::' in it['name']:
                    cls, method = it['name'].split('::', 1)
                    table = declared if cls == CLASS else hands_declared if cls == 'USub01HomeHandsInstance' else None
                    if table is not None and method not in table:
                        problems.append(f'{fname}:{it["line"]}: {it["name"]} is defined but not declared in its class')
    # Sub01* names used by the added code are defined in the module
    module_names = set()
    for text in after.values():
        module_names |= set(re.findall(r'\b(?:struct|class|enum\s+class|enum)\s+(?:\w+_API\s+)?(\w+)', strip(text)))
        for it in top_level_items(text):
            if it['kind'] in ('definition', 'declaration') and it['name']:
                module_names.add(it['name'].split('::')[-1])
            elif it['kind'] == 'declaration':
                module_names |= declared_functions(it['text'])
        module_names |= set(re.findall(r'\bnamespace\s+(\w+)', strip(text)))
        module_names |= set(re.findall(r'\b(?:constexpr|const)\s+[\w:<>]+\s+(\w+)\s*=', strip(text)))
    for fname, blocks in added.items():
        for h in blocks:
            for name in sorted(n for n in identifiers(h['text']) if re.match(r'[EFTUA]?Sub01', n)):
                if name not in module_names:
                    problems.append(f'{fname}:{h["first"]}: {name} is used but not defined in the staged module')
    # reflected types added by adapters are already used by root's reflected declarations
    root_reflected = reflected_types('\n'.join(t for n, t in fresh.items() if n.endswith('.h')))
    for fname, blocks in added.items():
        for h in blocks:
            for t in sorted(reflected_types(h['text']) - root_reflected):
                notes.append(f'{fname}:{h["first"]}: reflected type {t} is not used by any root UFUNCTION/UPROPERTY (UHT not run)')
    return {'problems': problems, 'notes': notes, 'includes': include_report, 'ue_allowlist': sorted(fresh_ue),
            'definitions_checked': sum(len(v) for v in defs.values())}


def declared_functions(text: str) -> set:
    """Names of functions declared (not called) in class-body text: reflection macros and initialisers removed."""
    names = set()
    s = re.sub(r'\b(?:UFUNCTION|UPROPERTY|UCLASS|USTRUCT)\s*\([^)]*\)', ' ', strip(text))
    for statement in s.split(';'):
        depth, cut = 0, len(statement)
        for i, c in enumerate(statement):
            depth += c == '('
            depth -= c == ')'
            if c == '=' and depth == 0:
                cut = i
                break
        m = re.search(r'[\w>*&]\s+[*&]?(\w+)\s*\([^()]*(?:\([^()]*\))?[^()]*\)\s*(?:const\s*)?(?:override\s*)?$', statement[:cut].strip())
        if m and not m.group(1).isupper():
            names.add(m.group(1))
    return names


def class_methods(header: str, cls: str) -> set:
    s = strip(header)
    m = re.search(r'class\s+\w+_API\s+' + cls + r'\b[^{]*\{', s)
    if not m:
        return set()
    depth, i = 1, m.end()
    while depth and i < len(s):
        depth += {'{': 1, '}': -1}.get(s[i], 0)
        i += 1
    return set(re.findall(r'\b(\w+)\s*\(', s[m.end():i]))


def reflected_types(text: str) -> set:
    found = set()
    for m in re.finditer(r'\bUFUNCTION\s*\([^)]*\)\s*([^;{]*\))', text):
        found |= set(re.findall(r'\b([FUTAE][A-Z]\w*)\b', m.group(1)))
    for m in re.finditer(r'\bUPROPERTY\s*\([^)]*\)\s*([^;=]*)', text):
        found |= set(re.findall(r'\b([FUTAE][A-Z]\w*)\b', m.group(1)))
    return found - {'UFUNCTION', 'UPROPERTY'}


# ---------------------------------------------------------------------------------------------- probes
def host_declarations(host: dict, upto_line: int) -> dict:
    """{name: type} of the host's parameters and of simple local declarations before upto_line."""
    decls = dict((n, t) for t, n in split_params(host['params'] or ''))
    lines = host['text'].split('\n')[:max(0, upto_line - host['line'])]
    body = strip('\n'.join(lines))
    body = body.split('{', 1)[1] if '{' in body else ''
    for m in re.finditer(r'auto\s*\*\s*(\w+)\s*=\s*Cast<(\w+)>', body):
        decls[m.group(1)] = m.group(2) + '*'
    for m in re.finditer(r'(?:^|[;{}(])\s*((?:const\s+)?' + DECL_TYPES + r'\s*[*&]?)\s+(\w+)\s*(=[^;]*)?;', body, re.M):
        base = m.group(1).strip()
        if base.endswith('&') or base.startswith('auto'):
            continue
        decls[m.group(2)] = base
        tail = m.group(3) or ''
        depth, cur = 0, ''
        for c in tail:
            depth += c in '(<{'
            depth -= c in ')>}'
            if c == ',' and depth == 0:
                more = re.match(r'\s*(\w+)\s*=', tail[tail.index(cur) + len(cur) + 1:]) if cur else None
                if more:
                    decls[more.group(1)] = base
            cur += c
    return decls


def probes(blocks: list) -> list:
    out = []
    for n, h in enumerate(blocks, 1):
        host = h['host']
        if host is None or host['name'] is None or not host['name'].startswith(CLASS + '::'):
            continue
        decls = host_declarations(host, h['first'])
        used = identifiers(h['text'])
        params = [(decls[name], name) for name in sorted(used & set(decls))]
        head = host['head']
        ret = head.split(CLASS + '::', 1)[0].strip() or 'void'
        const = ' const' if re.search(r'\)\s*const\s*$', head) else ''
        sig = ','.join(f'{t} {name}' for t, name in params)
        redeclared = sorted(set(re.findall(r'(?:^|[;{}(])\s*(?:const\s+)?' + DECL_TYPES + r'\s*[*&]?\s+(\w+)\s*[=;(]', h['stripped'], re.M)) & set(decls))
        out.append({'name': f'Sub01ClosureProbe{n}', 'host': host['name'], 'first': h['first'], 'ret': ret, 'const': const,
                    'sig': sig, 'text': h['text'], 'lines': len(h['lines']), 'redeclared': redeclared})
    return out


# ---------------------------------------------------------------------------------------------- compile
def compilers() -> list:
    found = []
    for name, flags in (('g++', GCC_FLAGS), ('clang++', CLANG_FLAGS)):
        path = shutil.which(name)
        if path:
            found.append((name, path, flags))
    return found


def build_units(work: Path, module: Path, fresh: dict, after: dict, added: dict) -> tuple:
    """Write translation units under work; return (units, coverage)."""
    tu_dir, shim_dir = work / 'tu', work / 'shim'
    tu_dir.mkdir(parents=True, exist_ok=True)
    ue = {name for text in list(fresh.values()) + list(after.values()) for kind, name in includes(text)
          if kind == '"' and name not in after and not name.endswith('.generated.h')}
    generated = {n[:-2] + '.generated.h' for n in after if n.endswith('.h')}
    shim.write(shim_dir, ue, generated)
    units, coverage = [], []
    pure = [n for n, t in sorted(after.items()) if n.endswith('.h') and not any(k == '"' for k, _ in includes(t))]
    text = ''.join(f'#include "{n}"\n' for n in [*ADAPTER_HEADERS, *[p for p in pure if p not in ADAPTER_HEADERS]])
    (tu_dir / 'engine_free_headers.cpp').write_text(text)
    units.append({'name': 'engine_free_headers', 'path': tu_dir / 'engine_free_headers.cpp', 'shim': False, 'defines': [[]]})
    coverage += [{'part': f'{n} (whole header)', 'unit': 'engine_free_headers'} for n in ADAPTER_HEADERS]

    # character: the installed class (probe members injected on its closing line), every appended top-level item,
    # every inserted statement block as a probe member.
    probe_list = probes(added.get(CPP, []))
    header = after[HEADER]
    close = re.search(r'\n\};', header[header.index(f'class SUB01HOMELAB_API {CLASS}'):])
    pos = header.index(f'class SUB01HOMELAB_API {CLASS}') + close.start() + 1
    decls = ''.join(f' {p["ret"]} {p["name"]}({p["sig"]}){p["const"]};' for p in probe_list)
    (tu_dir / HEADER).write_text(f'#line 1 "{module / HEADER}"\n' + header[:pos] + decls + header[pos:])
    body = [f'#include "{HEADER}"']
    for kind, name in includes(after[CPP]):
        if name != HEADER:
            body.append(f'#include {"<" if kind == "<" else chr(34)}{name}{">" if kind == "<" else chr(34)}')
    for h in added.get(CPP, []):
        if h['host'] is None:
            body.append(f'#line {h["first"]} "{module / CPP}"\n{h["text"]}')
            for it in h['items']:
                if it['kind'] == 'definition':
                    coverage.append({'part': f'{CPP}:{it["line"]} {it["name"]}', 'unit': 'character'})
    for p in probe_list:
        body.append(f'{p["ret"]} {CLASS}::{p["name"]}({p["sig"]}){p["const"]}{{\n#line {p["first"]} "{module / CPP}"\n{p["text"]}\n}}')
        coverage.append({'part': f'{CPP}:{p["first"]} +{p["lines"]} line(s) inserted into {p["host"]} (probe; host params/locals: {p["sig"] or "none"})',
                         'unit': 'character'})
    for h in added.get(CPP, []):
        if h['host'] is not None and not any(p['first'] == h['first'] for p in probe_list):
            coverage.append({'part': f'{CPP}:{h["first"]} inserted into {h["host"]["name"]}', 'unit': None})
    (tu_dir / 'character.cpp').write_text('\n'.join(body) + '\n')
    units.append({'name': 'character', 'path': tu_dir / 'character.cpp', 'shim': True, 'defines': [['-DWITH_EDITOR=1']]})
    coverage.append({'part': f'{HEADER} (whole installed header, incl. {", ".join(ADAPTER_HEADERS)})', 'unit': 'character'})

    # hands: whole header, the whole FSub01HandsProxy (root struct + inserted lines), appended top-level items.
    hands_after = after[HANDS_CPP]
    proxy = next((it for it in top_level_items(hands_after) if it['kind'] == 'definition' and it['head'].startswith(PROXY)), None)
    body = [f'#include "{HANDS_H}"']
    for kind, name in includes(hands_after):
        if name != HANDS_H:
            body.append(f'#include {"<" if kind == "<" else chr(34)}{name}{">" if kind == "<" else chr(34)}')
    if proxy:
        body.append(f'#line {proxy["line"]} "{module / HANDS_CPP}"\n{proxy["text"]}')
    for h in added.get(HANDS_CPP, []):
        if h['host'] is None:
            body.append(f'#line {h["first"]} "{module / HANDS_CPP}"\n{h["text"]}')
            for it in h['items']:
                if it['kind'] == 'definition':
                    coverage.append({'part': f'{HANDS_CPP}:{it["line"]} {it["name"]}', 'unit': 'hands'})
        elif proxy and h['host'] and h['host']['line'] == proxy['line']:
            coverage.append({'part': f'{HANDS_CPP}:{h["first"]} +{len(h["lines"])} line(s) inside FSub01HandsProxy (whole struct compiled)', 'unit': 'hands'})
        else:
            coverage.append({'part': f'{HANDS_CPP}:{h["first"]} inserted into {(h["host"] or {}).get("name")}', 'unit': None})
    (tu_dir / 'hands.cpp').write_text('\n'.join(body) + '\n')
    units.append({'name': 'hands', 'path': tu_dir / 'hands.cpp', 'shim': True, 'defines': [['-DWITH_EDITOR=0'], ['-DWITH_EDITOR=1']]})
    coverage.append({'part': f'{HANDS_H} (whole installed header)', 'unit': 'hands'})
    return units, coverage, probe_list, shim_dir, tu_dir


def compile_units(units, module: Path, shim_dir: Path, tu_dir: Path) -> list:
    results = []
    for name, path, flags in compilers():
        for unit in units:
            for defines in unit['defines']:
                cmd = [path, '-std=c++20', '-fsyntax-only', *flags, *defines, f'-I{tu_dir}', f'-I{module}']
                if unit['shim']:
                    cmd += ['-isystem', str(shim_dir)]
                cmd.append(str(unit['path']))
                run = subprocess.run(cmd, capture_output=True, text=True)
                results.append({'compiler': name, 'unit': unit['name'], 'defines': defines, 'ok': run.returncode == 0,
                                'diagnostics': run.stderr.strip()})
    return results


# ---------------------------------------------------------------------------------------------- driver
def check(work: Path, staging_ref=None) -> dict:
    work = Path(work)
    project = work / 'project'
    staging = stage_project(project, staging_ref)
    module = project / 'Source/Sub01HomeLab'
    installed = install(module)
    fresh, after = installed['fresh'], installed['after']
    added = {}
    for name in sorted(after):
        if name in fresh and fresh[name] != after[name]:
            added[name] = classify(name, after[name], hunks(fresh[name], after[name]))
        elif name not in fresh:
            added[name] = classify(name, after[name], hunks('', after[name]))
    static = static_checks(fresh, after, added, installed['anchors'])
    units, coverage, probe_list, shim_dir, tu_dir = build_units(work, module, fresh, after, added)
    for p in probe_list:
        if p['redeclared']:
            static['problems'].append(f'{CPP}:{p["first"]}: inserted lines redeclare {p["redeclared"]} already declared in {p["host"]}')
    results = compile_units(units, module, shim_dir, tu_dir)
    failures = static['problems'] + [f'{r["compiler"]} {r["unit"]} {" ".join(r["defines"])}: compile failed' for r in results if not r['ok']]
    return {'schema': 'sub01.native-adapters-compile-closure.v1', 'staging': staging, 'installed': installed['selected'],
            'anchors': installed['anchors'], 'added_lines': {n: sum(len(h['lines']) for h in b) for n, b in added.items()},
            'static': static, 'coverage': coverage, 'compiles': results,
            'not_compiled': ['root function bodies that host inserted lines (only the inserted lines, as probes)',
                             'engine API semantics: calls are checked against stub signatures only',
                             'UnrealHeaderTool (reflection) and linking'],
            'compilers': [c[0] for c in compilers()], 'ok': not failures, 'failures': failures}


def summary(report: dict) -> str:
    out = [f"native adapters compile closure: {' -> '.join(report['installed'])}; staged from {report['staging']['staging']}"]
    if 'identical_to_checkout_staging' in report['staging']:
        out.append(f"  staged module identical to this checkout's staging: {report['staging']['identical_to_checkout_staging']}")
    out.append(f"  added lines: {report['added_lines']}")
    out.append(f"  anchors: {len(report['anchors'])}, all unique: {all(a['count'] == 1 for a in report['anchors'])}")
    out.append(f"  includes added: {len(report['static']['includes'])}; definitions scanned: {report['static']['definitions_checked']}")
    out.append('  compiled (stub UE shim):')
    for c in report['coverage']:
        if c['unit']:
            out.append(f"    [{c['unit']}] {c['part']}")
    missing = [c['part'] for c in report['coverage'] if not c['unit']]
    out.append('  statically checked only: ' + ('; '.join(missing) if missing else 'none of the added code') +
               '; not compiled: ' + '; '.join(report['not_compiled']))
    for r in report['compiles']:
        out.append(f"  {r['compiler']:8} {r['unit']:20} {' '.join(r['defines']):16} {'OK' if r['ok'] else 'FAILED'}")
        if not r['ok']:
            out.extend('      ' + line for line in r['diagnostics'].split('\n')[:40])
    for note in report['static']['notes']:
        out.append(f'  note: {note}')
    for problem in report['static']['problems']:
        out.append(f'  PROBLEM: {problem}')
    out.append('closure: ' + ('PASS' if report['ok'] else f"FAIL ({len(report['failures'])})"))
    return '\n'.join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--staging-ref', help='git ref whose staging inputs stage the module (e.g. origin/main)')
    parser.add_argument('--json', type=Path, help='write the full report here')
    parser.add_argument('--keep', type=Path, help='keep the scratch project and translation units here')
    args = parser.parse_args(argv)
    try:
        if args.keep:
            if args.keep.exists():
                shutil.rmtree(args.keep)
            args.keep.mkdir(parents=True)
            report = check(args.keep, args.staging_ref)
        else:
            with tempfile.TemporaryDirectory(prefix='sub01-closure-') as tmp:
                report = check(Path(tmp), args.staging_ref)
    except Refused as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 2
    print(summary(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str) + '\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
