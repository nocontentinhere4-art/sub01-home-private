#!/usr/bin/env python3
"""Install a per-user LaunchAgent. Defaults to read-only checks every 15 minutes."""
import argparse, json, os, plistlib, subprocess, sys
from pathlib import Path
from rewards import require
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--config',required=True);ap.add_argument('--live',action='store_true');args=ap.parse_args()
require(sys.platform=='darwin','This installer is for macOS');os.umask(0o077)
config=Path(args.config).resolve();c=json.loads(config.read_text());state=Path(c['state_dir']);state.mkdir(parents=True,exist_ok=True,mode=0o700)
if args.live:
    require(c.get('enabled') is True,'Set enabled=true only after reviewing the configuration')
    from automatic import Worker, RPC, Ledger, private_file
    Worker(c,RPC(private_file(c['rpc_file'])),Ledger(state/'live.sqlite'),True).signer()
label='live.subzerone.rewards';target=Path.home()/'Library/LaunchAgents'/f'{label}.plist';target.parent.mkdir(parents=True,exist_ok=True)
command=[sys.executable,str(Path(__file__).with_name('automatic.py').resolve()),'--config',str(config)]
if args.live:command+=['--live','--loop']
job={'Label':label,'ProgramArguments':command,'RunAtLoad':True,'StartInterval':c['interval_seconds'],
     'StandardOutPath':str(state/'worker.log'),'StandardErrorPath':str(state/'worker-error.log'),
     'ProcessType':'Background','ThrottleInterval':60,'Umask':63}
# Launchd will not run another instance of this job while the existing one runs.
# Live mode loops quickly only to reconcile pending signatures; START remains opt-in.
domain=f'gui/{os.getuid()}'
subprocess.run(['launchctl','bootout',f'{domain}/{label}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
with target.open('wb') as f:plistlib.dump(job,f)
os.chmod(target,0o600)
subprocess.run(['launchctl','bootstrap',domain,str(target)],check=True)
print('Installed '+label+(' LIVE' if args.live else ' READ-ONLY')+'; no keys printed.')
