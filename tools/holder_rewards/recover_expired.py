#!/usr/bin/env python3
"""Read-only expired-transaction reconciliation; --apply is an owner-run recovery step."""
import argparse, base64, fcntl, json, os, sqlite3, time
from pathlib import Path
from solders.transaction import Transaction
from rewards import DEV, RPC, require, canonical
from automatic import private_file

PUBLIC_RPC='https://api.mainnet-beta.solana.com'

def check_source(rpc,sig,blockhash,last_height,created):
    height=rpc.call('getBlockHeight',[{'commitment':'finalized'}])
    require(height>last_height+32,'Finalized chain has not passed expiry with margin')
    require(rpc.call('isBlockhashValid',[blockhash,{'commitment':'finalized'}])['value'] is False,'Old blockhash still valid')
    status=rpc.call('getSignatureStatuses',[[sig],{'searchTransactionHistory':True}])['value'][0]
    require(status is None,'Signature exists: reconcile its actual outcome, do not replace')
    tx=rpc.call('getTransaction',[sig,{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':0}])
    require(tx is None,'Transaction exists: do not replace')
    before=None;seen=set();scanned=0
    # Fee payer must appear in the canonical address history if this transaction landed.
    # Go back beyond the signed transaction's creation time, not merely its expiry.
    for _ in range(20):
        opts={'limit':100,'commitment':'finalized'}
        if before:opts['before']=before
        rows=rpc.call('getSignaturesForAddress',[DEV,opts])
        require(rows,'History does not cover the relevant period')
        for row in rows:
            require(row['signature']!=sig,'Signature found in address history')
            require(row['signature'] not in seen,'RPC repeated history entries')
            seen.add(row['signature']);scanned+=1
            require(type(row.get('blockTime')) is int,'History entry missing timestamp')
        if rows[-1]['blockTime']<created-300:
            return {'finalized_height':height,'oldest_history_time':rows[-1]['blockTime'],'history_entries_scanned':scanned,'signature_absent':True,'blockhash_expired':True}
        before=rows[-1]['signature']
    raise ValueError('History coverage limit reached; no recovery applied')

def proof(rpcs,row):
    sig,pid,wire,height,created,amount=row
    tx=Transaction.from_bytes(base64.b64decode(wire))
    require(str(tx.signatures[0])==sig and str(tx.message.account_keys[0])==DEV,'Journal/signature/fee payer mismatch')
    require(len(rpcs)==2,'Two RPC sources required')
    results=[check_source(rpc,sig,str(tx.message.recent_blockhash),height,created) for rpc in rpcs]
    return {'signature':sig,'plan_id':pid,'amount_lamports':amount,'checked_at':int(time.time()),'sources':results,'basis':'Expired blockhash; signature absent from transaction and signature endpoints and finalized dev address history on configured and public RPCs.'}

def apply_recovery(db,row,evidence,kind="payout"):
    sig,pid,wire,height,created,amount=row
    db.execute('BEGIN IMMEDIATE')
    try:
        current=db.execute("SELECT signature,plan_id,wire,last_height,created,amount FROM outbox WHERE state='pending' AND kind=?",(kind,)).fetchall()
        require(current==[tuple(row)],'Pending state changed; recheck')
        require(kind in ('payout','amm','pump'),'Unsupported transaction kind')
        if kind=='payout':
            require(db.execute('SELECT status FROM plans WHERE id=?',(pid,)).fetchone()==('reserved',),'Plan is not reserved')
        else:
            require(pid is None,'Claim unexpectedly refers to a payout plan')
            require(db.execute('SELECT 1 FROM receipts WHERE signature=?',(sig,)).fetchone() is None,'Claim already recorded; reconcile instead')
        db.execute('CREATE TABLE IF NOT EXISTS recovery_audit(signature TEXT PRIMARY KEY,evidence TEXT NOT NULL)')
        db.execute('INSERT INTO recovery_audit VALUES(?,?)',(sig,canonical(evidence)))
        db.execute("UPDATE outbox SET state='expired' WHERE signature=? AND state='pending'",(sig,))
        if kind=='payout':db.execute('DELETE FROM prepared WHERE plan_id=?',(pid,))
        # Keep every original debit/reservation: the same plan will be prepared again.
        db.commit()
    except Exception:db.rollback();raise

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--apply',action='store_true');ap.add_argument('--out');args=ap.parse_args();os.umask(0o077)
    root=Path.home()/'Library/Application Support/SUB01Rewards';c=json.loads((root/'config.json').read_text());state=Path(c['state_dir'])
    lock=None
    if args.apply:
        lock=(state/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    path=state/'live.sqlite'
    db=sqlite3.connect(path if args.apply else path.as_uri()+'?mode=ro',uri=not args.apply,isolation_level=None)
    pending=db.execute("SELECT kind,signature,plan_id,wire,last_height,created,amount FROM outbox WHERE state='pending'").fetchall()
    require(len(pending)==1,'Expected exactly one pending transaction; no changes made')
    kind=pending[0][0];require(kind in ('payout','amm','pump'),'Unsupported pending kind')
    rows=[pending[0][1:]]
    require(len(rows)==1,'Expected exactly one pending payout; no changes made')
    url=private_file(c['rpc_file']);require(url.rstrip('/')!=PUBLIC_RPC,'Independent RPC required')
    evidence=proof([RPC(url),RPC(PUBLIC_RPC)],rows[0]);evidence['applied']=False;evidence['kind']=kind
    if args.apply:apply_recovery(db,rows[0],evidence,kind);evidence['applied']=True
    if args.out:Path(args.out).write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Recovery refused or unavailable. No new transaction sent. Keep the worker stopped and request review.')
