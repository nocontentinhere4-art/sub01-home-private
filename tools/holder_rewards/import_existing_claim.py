#!/usr/bin/env python3
"""Review one verified historical creator claim; apply only when run by owner."""
import argparse, fcntl, json, os
from pathlib import Path
from automatic import RPC, private_file, AMM, AMM_AUTH, AMM_VAULT, TOKEN, WSOL, ata, claim_amount, market
from rewards import DEV, require, receipt_amount, Ledger, snapshot, allocate

SIGNATURE='mE3PxX28PRTNAT1ctpTEiSGNa2hTtmVnYwtK2FkGNtQfGZYFEwfz4K1EiZaA8JNUGYwcTzvX6zzEzmL9WfHgqrH'
AMOUNT=374246583

def verify(tx):
    require(SIGNATURE in tx['transaction']['signatures'],'Wrong historical claim')
    require(tx['meta']['err'] is None,'Failed transaction')
    destination=ata(DEV)
    instructions=tx['transaction']['message']['instructions']
    matches=[(i,x) for i,x in enumerate(instructions) if x['programId']==AMM and x.get('data')=='ToNg27JNfmT']
    require(len(matches)==1,'Expected exactly one creator claim')
    index,ins=matches[0]
    require(ins['accounts'][:6]==[WSOL,TOKEN,DEV,AMM_AUTH,AMM_VAULT,destination],'Wrong creator/vault/destination')
    groups=[g for g in tx['meta']['innerInstructions'] if g['index']==index]
    require(len(groups)==1,'Missing claim transfers')
    narrowed={'meta':{'innerInstructions':groups}}
    amount=claim_amount(narrowed,{'kind':'amm','destination':destination})
    require(amount==AMOUNT and receipt_amount(tx)==amount,'Claim amount/net SOL credit mismatch')
    require(any(x['programId']==TOKEN and x.get('parsed',{}).get('type')=='closeAccount' and x['parsed']['info']=={'account':destination,'destination':DEV,'owner':DEV} for x in instructions),'Claim not unwrapped to dev')
    return amount

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--apply',action='store_true');ap.add_argument('--out');args=ap.parse_args();os.umask(0o077)
    root=Path.home()/'Library/Application Support/SUB01Rewards';c=json.loads((root/'config.json').read_text());rpc=RPC(private_file(c['rpc_file']))
    tx=rpc.tx(SIGNATURE);amount=verify(tx)
    quote=market(rpc);snap=snapshot(rpc,quote['price'],quote['source'],quote['price_at'],c['excluded']);result=allocate(amount,snap)
    report={'claim_signature':SIGNATURE,'gross_fee_lamports':amount,'excluded_operational_deposit_lamports':20000000,'applied':False,**result}
    if args.apply:
        state=Path(c['state_dir']);lock=(state/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger=Ledger(state/'live.sqlite')
        row=ledger.db.execute('SELECT amount FROM receipts WHERE signature=?',(SIGNATURE,)).fetchone()
        if row:require(row[0]==amount,'Existing receipt differs')
        else:ledger.receipt(SIGNATURE,amount,{'source':'owner-authorized verified manual PumpSwap claim','slot':tx['slot'],'blockTime':tx['blockTime']})
        report['applied']=True;report['already_recorded']=bool(row)
        ledger.db.close()
    if args.out:Path(args.out).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='allocations'},indent=2))

if __name__=='__main__':main()
