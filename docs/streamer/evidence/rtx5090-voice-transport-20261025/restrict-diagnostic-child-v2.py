"""Child-only confinement for known offline diagnostic programs, not hostile code.
No host mount/firewall changes. AF_UNIX IPC remains available. Landlock controls
TCP ports, not bind addresses. The caller must enforce loopback argv/listeners.
"""
import argparse
import ctypes as C
import errno
import os
from pathlib import Path
import platform
import stat
import sys

LIB=C.CDLL(None,use_errno=True)
LIB.syscall.restype=C.c_long
LIB.prctl.restype=C.c_int
class Ruleset(C.Structure):
 _fields_=[('fs',C.c_uint64),('net',C.c_uint64)]
class PathRule(C.Structure):
 _pack_=1
 _fields_=[('access',C.c_uint64),('parent_fd',C.c_int32)]
class NetRule(C.Structure):
 _fields_=[('access',C.c_uint64),('port',C.c_uint64)]
class Filter(C.Structure):
 _fields_=[('code',C.c_ushort),('jt',C.c_ubyte),('jf',C.c_ubyte),('k',C.c_uint32)]
class Program(C.Structure):
 _fields_=[('length',C.c_ushort),('filters',C.POINTER(Filter))]

def checked(value,label):
 if value<0:raise OSError(C.get_errno(),label)
 return value

def validated_gpu(path):
 s=os.stat(path,follow_symlinks=False)
 if not stat.S_ISCHR(s.st_mode) or s.st_rdev!=os.makedev(195,1):
  raise ValueError('Unexpected visible GPU type/device identity')
 return path

def private_dir(path):
 p=Path(path)
 assert p.is_absolute() and p.resolve()==p and not p.is_symlink()
 s=p.stat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==1001 and stat.S_IMODE(s.st_mode)==0o700
 return p

def network_filter():
 # Classic BPF with symbolic forward labels. x86_64 and x32 checks fail closed.
 ops=[];labels={}
 def label(n):labels[n]=len(ops)
 def ins(code,k=0,jt=0,jf=0):ops.append([code,jt,jf,k])
 def jump(value,yes,no):ins(0x15,value,yes,no)
 ins(0x20,4);jump(0xc000003e,'nr','kill')
 label('nr');ins(0x20,0)
 ins(0x35,0x40000000,'deny','native')
 label('native');jump(41,'socket','uring1')
 label('uring1');jump(425,'deny','uring2')
 label('uring2');jump(426,'deny','uring3')
 label('uring3');jump(427,'deny','allow')
 label('socket');ins(0x20,16);jump(1,'allow','inet')
 label('inet');jump(2,'type','inet6')
 label('inet6');jump(10,'type','deny')
 label('type');ins(0x20,24);ins(0x54,15);jump(1,'protocol','deny')
 label('protocol');ins(0x20,32);jump(0,'allow','tcp')
 label('tcp');jump(6,'allow','deny')
 label('deny');ins(0x06,0x00050000|errno.EPERM)
 label('kill');ins(0x06,0x80000000)
 label('allow');ins(0x06,0x7fff0000)
 rows=[]
 for i,(code,jt,jf,k) in enumerate(ops):
  jt=labels[jt]-i-1 if isinstance(jt,str) else jt
  jf=labels[jf]-i-1 if isinstance(jf,str) else jf
  assert 0<=jt<=255 and 0<=jf<=255
  rows.append(Filter(code,jt,jf,k))
 array=(Filter*len(rows))(*rows);program=Program(len(rows),array)
 checked(LIB.prctl(22,2,C.byref(program),0,0),'seccomp filter')

def confine(directory,port):
 assert platform.machine()=='x86_64' and os.getuid()==1001 and os.geteuid()==1001
 assert os.getgid()==1001 and os.getegid()==1001
 status=Path('/proc/self/status').read_text().splitlines()
 for label in ('CapInh:','CapPrm:','CapEff:','CapAmb:'):
  caps=next(s.split()[1]for s in status if s.startswith(label))
  assert int(caps,16)==0,'capabilities must be dropped before wrapper'
 assert port in (8855,8856)
 isolated=private_dir(directory)
 # Close all non-stdio inherited descriptors before creating restriction FDs.
 for name in os.listdir('/proc/self/fd'):
  fd=int(name)
  if fd>2:
   try:os.close(fd)
   except OSError as e:
    if e.errno!=errno.EBADF:raise
 abi=checked(LIB.syscall(444,0,0,1),'Landlock ABI query');assert abi>=4
 # Content writes/truncation and directory entry modification denied by default.
 rights=(1<<1)|sum(1<<n for n in range(4,15))
 attr=Ruleset(rights,3)
 rules=checked(LIB.syscall(444,C.byref(attr),C.sizeof(attr),0),'create Landlock ruleset')
 def path_rule(path,allowed):
  fd=os.open(path,os.O_PATH|os.O_CLOEXEC|os.O_NOFOLLOW)
  try:
   rule=PathRule(allowed,fd)
   checked(LIB.syscall(445,rules,1,C.byref(rule),0),'Landlock path rule')
  finally:os.close(fd)
 try:
  path_rule(str(isolated),rights & ~(1<<6) & ~(1<<11))
  # CUDA device I/O is explicitly permitted; this is not hostile-code isolation.
  for path in ('/dev/null','/dev/nvidiactl','/dev/nvidia-uvm','/dev/nvidia-uvm-tools'):
   if Path(path).exists():
    s=os.stat(path,follow_symlinks=False);assert stat.S_ISCHR(s.st_mode)
    path_rule(path,1<<1)
  # Numeric own-process task subtree; permits eligible own-task writes, NOT
  # only comm. No MAKE_REG, broad proc root, or unrelated-process grant.
  task=f'/proc/{os.getpid()}/task'
  task_stat=os.stat(task,follow_symlinks=False)
  assert stat.S_ISDIR(task_stat.st_mode)
  path_rule(task,(1<<1)|(1<<14))
  gpu='/dev/nvidia1'
  path_rule(validated_gpu(gpu),1<<1)
  net=NetRule(1,port) # bind only. No TCP connect rights granted, including loopback.
  checked(LIB.syscall(445,rules,2,C.byref(net),0),'Landlock bind rule')
  checked(LIB.prctl(38,1,0,0,0),'no_new_privs')
  checked(LIB.syscall(446,rules,0),'restrict Landlock')
 finally:os.close(rules)
 network_filter()
 status=Path('/proc/self/status').read_text()
 assert '\nNoNewPrivs:\t1\n'in status and '\nSeccomp:\t2\n'in status
 return abi

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--directory',required=True)
 p.add_argument('--bind-port',type=int,required=True)
 p.add_argument('command',nargs=argparse.REMAINDER)
 a=p.parse_args();assert a.command and a.command[0]=='--';command=a.command[1:]
 assert command and Path(command[0]).is_absolute()
 confine(a.directory,a.bind_port)
 # Restriction FDs are closed; future subprocesses inherit these restrictions.
 os.execve(command[0],command,dict(os.environ))

if __name__=='__main__':main()
