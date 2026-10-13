#!/usr/bin/env python3
"""Confine only the two authorized CI Unix users before config.sh/run.sh.

Needs Linux Landlock ABI4; fails closed. No registration or workload is started
by this module itself. Run after switching to UID2101/2102, from a rootfs-owned
copy, with the caller's registration/run environment already allowlisted.
"""
import argparse,ctypes,os,pwd,sys
from pathlib import Path
class Ruleset(ctypes.Structure):
    _fields_=[('fs',ctypes.c_uint64),('net',ctypes.c_uint64)]
class PathRule(ctypes.Structure):
    _pack_=1
    _fields_=[('access',ctypes.c_uint64),('parent',ctypes.c_int32)]
class PortRule(ctypes.Structure):
    _fields_=[('access',ctypes.c_uint64),('port',ctypes.c_uint64)]
FS_ALL=(1<<15)-1
READ=(1<<0)|(1<<2)|(1<<3)
FILE_RW=(1<<1)|(1<<2)
CONNECT=1<<1
BIND=1<<0
PROTECTED_PORTS=frozenset({8798,8799,8803,8811,8820,8821,8888,8890,25569})

def tcp_rules(ephemeral_low,ephemeral_high):
    """Allow test listeners/rebinding without granting private service ports."""
    if not 1024<=ephemeral_low<=ephemeral_high<=65535 or any(ephemeral_low<=p<=ephemeral_high for p in PROTECTED_PORTS):
        raise RuntimeError('Unexpected ephemeral range intersects private services')
    for port in (80,443):
        yield port,CONNECT
    for port in range(8765,8770):
        yield port,BIND|CONNECT
    for port in range(ephemeral_low,ephemeral_high+1):
        # Fixtures bind zero, close the listener, then rebind its allocated port.
        yield port,BIND|CONNECT
    yield 0,BIND

lib=ctypes.CDLL(None,use_errno=True)
def checked(result,operation):
    if result<0:raise OSError(ctypes.get_errno(),operation)
    return result

def confine():
    uid=os.getuid()
    if uid not in (2101,2102):raise RuntimeError('CI isolation requires exact authorized UID')
    home=Path('/home/sub01-ci-'+str(uid-2100))
    if Path(pwd.getpwuid(uid).pw_dir)!=home:raise RuntimeError('Unexpected CI home')
    for p in [home,home/'toolcache',Path('/tmp/sub01-ci-'+str(uid))]:
        p.mkdir(exist_ok=True)
        if p.stat().st_uid!=uid:raise RuntimeError('Unexpected writable CI path owner')
        p.chmod(0o700)
    tmp=Path('/tmp/sub01-ci-'+str(uid))
    abi=checked(lib.syscall(444,0,0,1),'Landlock ABI query')
    if abi<4:raise RuntimeError('Landlock ABI4 is required')
    attr=Ruleset(FS_ALL,BIND|CONNECT)
    fd=checked(lib.syscall(444,ctypes.byref(attr),ctypes.sizeof(attr),0),'Landlock ruleset')
    def path_rule(p,access):
        if not Path(p).exists():return
        parent=os.open(p,os.O_PATH|os.O_CLOEXEC)
        try:
            rule=PathRule(access,parent)
            checked(lib.syscall(445,fd,1,ctypes.byref(rule),0),'Landlock path rule')
        finally:os.close(parent)
    try:
        path_rule('/',1<<3)  # Ancestor enumeration only; no file read/write grants.
        for p in ['/usr','/opt','/bin','/sbin','/lib','/lib64','/etc','/proc','/sys']:
            path_rule(p,READ)
        path_rule(str(home),FS_ALL);path_rule(str(tmp),FS_ALL)
        for p in ['/dev/null','/dev/zero','/dev/random','/dev/urandom']:
            path_rule(p,FILE_RW)
        # TCP: public package access and bounded fixture ports; private services denied.
        ephemeral_low,ephemeral_high=map(int,Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split())
        for port,access in tcp_rules(ephemeral_low,ephemeral_high):
            rule=PortRule(access,port)
            checked(lib.syscall(445,fd,2,ctypes.byref(rule),0),'Landlock TCP test/connect rule')
        checked(lib.prctl(38,1,0,0,0),'No new privileges')
        checked(lib.syscall(446,fd,0),'Landlock enforce')
    finally:os.close(fd)
    # Preserve only ordinary path/locale settings and explicit registration keys.
    names={'PATH','LANG','LC_ALL','CI_REGISTRATION_TOKEN','SUB01_CI_REGISTRATION_TOKEN','RUNNER_REGISTRATION_TOKEN','REGISTRATION_TOKEN','ACTIONS_RUNNER_INPUT_TOKEN'}
    env={k:v for k,v in os.environ.items() if k in names}
    env.update({'HOME':str(home),'USER':pwd.getpwuid(uid).pw_name,'LOGNAME':pwd.getpwuid(uid).pw_name,'TMPDIR':str(tmp),'RUNNER_TOOL_CACHE':str(home/'toolcache'),'AGENT_TOOLSDIRECTORY':str(home/'toolcache')})
    return env

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=args.command
    if command[:1]==['--']:command=command[1:]
    if not command:parser.error('A command is required')
    env=confine()
    os.execvpe(command[0],command,env)
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('CI_ISOLATION_FAILED='+type(e).__name__+': '+str(e),file=sys.stderr)
        raise SystemExit(125)
