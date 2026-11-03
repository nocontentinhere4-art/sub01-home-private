#!/usr/bin/env python3
"""Durable SUB-01 worker. Default: read-only preflight. Live mode is opt-in."""
import argparse, base64, fcntl, json, os, stat, time, urllib.request
from pathlib import Path
from decimal import Decimal
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.hash import Hash
from solders.message import Message
from solders.transaction import Transaction
from solders.instruction import Instruction, AccountMeta
from solders.system_program import create_account, CreateAccountParams
from rewards import (RPC, Ledger, DEV, MINT, TOKEN, TOKEN2022, SYSTEM, MEMO,
                     require, canonical, snapshot, allocate, prepare, transaction_message)

HERE=Path(__file__).resolve().parent
IDL=json.loads((HERE/'pump-instructions.json').read_text())
PUMP=IDL['pump']['address']; AMM=IDL['pump_amm']['address']
POOL='4gAj3MmDM2yk41frM7twYTUazwVsUzhjH9ZNdW81qSpp'
WSOL='So11111111111111111111111111111111111111112'
ATA='ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'
pk=Pubkey.from_string

def pda(program,*seeds):
    return str(Pubkey.find_program_address(list(seeds),pk(program))[0])
def ata(owner):return pda(ATA,bytes(pk(owner)),bytes(pk(TOKEN)),bytes(pk(WSOL)))
CURVE=pda(PUMP,b'bonding-curve',bytes(pk(MINT)))
PUMP_VAULT=pda(PUMP,b'creator-vault',bytes(pk(DEV)))
AMM_AUTH=pda(AMM,b'creator_vault',bytes(pk(DEV)))
AMM_VAULT=ata(AMM_AUTH)

def raw(account,owner):
    require(account and account['owner']==owner,'Unexpected account owner')
    return base64.b64decode(account['data'][0],validate=True)
def account(rpc,key):return rpc.call('getAccountInfo',[key,{'encoding':'base64','commitment':'finalized'}])['value']
def uint(b,start,size=8):return int.from_bytes(b[start:start+size],'little')
def pub(b,start):return str(Pubkey.from_bytes(b[start:start+32]))
def pool_fields(a):
    b=raw(a,AMM)
    require(len(b)>=243 and b[:8]==bytes([241,154,109,4,17,177,109,188]),'Unexpected pool layout')
    require(pub(b,43)==MINT and pub(b,75)==WSOL and pub(b,211)==DEV,'Pool mint/creator changed; stop')
    require(not any(b[243:245]),'Unsupported mayhem/cashback pool')
    return {'base_vault':pub(b,139),'quote_vault':pub(b,171),
            'virtual_quote':int.from_bytes(b[245:261],'little',signed=True) if len(b)>=261 else 0,
            'creator_fees':uint(b,279) if len(b)>=287 else 0}
def token_amount(a,mint,owner,program=TOKEN):
    b=raw(a,program);require(len(b)>=165 and pub(b,0)==mint and pub(b,32)==owner and b[108]==1,'Wrong token vault/state')
    return uint(b,64)
def http_json(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SUB01Rewards/1.0'}),timeout=20) as r:return json.load(r)
    except Exception:raise ValueError('Public price service unavailable') from None

def sol_price(now=None):
    now=int(time.time()) if now is None else now
    response=http_json('https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_last_updated_at=true')
    p=response['solana'];price=Decimal(str(p['usd']));ts=p['last_updated_at']
    require(price.is_finite() and price>0,'Invalid SOL/USD price')
    require(type(ts) is int and 0<=now-ts<=120,'Stale SOL/USD quote')
    return price,ts

def market(rpc):
    fields=pool_fields(account(rpc,POOL))
    result=rpc.call('getMultipleAccounts',[[POOL,fields['base_vault'],fields['quote_vault']],{'encoding':'base64','commitment':'finalized'}])
    pool,base,quote=result['value'];current=pool_fields(pool)
    require(current['base_vault']==fields['base_vault'] and current['quote_vault']==fields['quote_vault'],'Pool vaults changed')
    b=token_amount(base,MINT,POOL,TOKEN2022);q=token_amount(quote,WSOL,POOL)+current['virtual_quote']
    require(b>0 and q>0,'Empty pool reserves')
    blocktime=rpc.call('getBlockTime',[result['context']['slot']]);now=int(time.time())
    require(blocktime is not None and 0<=now-blocktime<=120,'Stale finalized RPC state')
    sol,ts=sol_price(now);price=(Decimal(q)*sol/(Decimal(b)*1000)).quantize(Decimal('0.000000000000000001'))
    # Cross-check against a second public service; never use its retrieval time as an oracle timestamp.
    rows=http_json('https://api.dexscreener.com/latest/dex/tokens/'+MINT)['pairs']
    pair=next((x for x in rows if x['pairAddress']==POOL and x['chainId']=='solana'),None)
    require(pair is not None,'Missing independent pool quote')
    other=Decimal(pair['priceUsd']);require(other>0 and abs(price-other)/price<=Decimal('0.10'),'Independent prices differ by >10%')
    return {'price':str(price),'price_at':min(ts,blocktime),'slot':result['context']['slot'],'pool':current,
            'source':'finalized PumpSwap effective reserves + CoinGecko SOL/USD; Dexscreener cross-check'}

def instruction(program,name,accounts):
    spec=IDL[program]['instructions'][name]
    return Instruction(pk(IDL[program]['address']),bytes(spec['discriminator']),[
        AccountMeta(pk(accounts[a['name']]),a.get('signer',False),a.get('writable',False)) for a in spec['accounts']])
def claim_instructions(rpc,kind):
    pool=pool_fields(account(rpc,POOL))
    common={'payer':DEV,'creator':DEV,'coin_creator':DEV,'base_mint':MINT,'quote_mint':WSOL,
            'quote_token_program':TOKEN,'associated_token_program':ATA,'system_program':SYSTEM}
    if kind=='pump':
        curve=raw(account(rpc,CURVE),PUMP)
        require(len(curve)>=81 and curve[:8]==bytes([23,183,248,55,96,216,172,96]) and pub(curve,49)==DEV,'Curve creator changed')
        v=account(rpc,PUMP_VAULT)
        require(v is None or v['owner']==SYSTEM,'Unexpected Pump vault owner')
        minimum=rpc.call('getMinimumBalanceForRentExemption',[0])
        expected=max(0,(v or {}).get('lamports',0)-minimum)+(uint(curve,125) if len(curve)>=133 else 0)
        a={**common,'program':PUMP,'event_authority':pda(PUMP,b'__event_authority'),'global':pda(PUMP,b'global'),
           'bonding_curve':CURVE,'associated_quote_bonding_curve':ata(CURVE),'recipient':PUMP_VAULT,
           'associated_quote_recipient':ata(PUMP_VAULT),'creator_vault':PUMP_VAULT,
           'creator_vault_token_account':ata(PUMP_VAULT),'creator_token_account':ata(DEV)}
        return [instruction('pump','sweep_creator_fee',a),instruction('pump','collect_creator_fee_v2',a)],[],{'kind':kind,'expected':expected}
    require(kind=='amm','Unknown claim kind')
    v=account(rpc,AMM_VAULT)
    expected=(token_amount(v,WSOL,AMM_AUTH) if v else 0)+pool['creator_fees']
    temporary=Keypair();dest=str(temporary.pubkey())
    rent=rpc.call('getMinimumBalanceForRentExemption',[165])
    a={**common,'program':AMM,'event_authority':pda(AMM,b'__event_authority'),'global_config':pda(AMM,b'global_config'),
       'pool':POOL,'pool_quote_token_account':pool['quote_vault'],'recipient':AMM_AUTH,'recipient_token_account':AMM_VAULT,
       'coin_creator_vault_authority':AMM_AUTH,'coin_creator_vault_ata':AMM_VAULT,'coin_creator_token_account':dest}
    create=create_account(CreateAccountParams(from_pubkey=pk(DEV),to_pubkey=temporary.pubkey(),lamports=rent,space=165,owner=pk(TOKEN)))
    initialize=Instruction(pk(TOKEN),bytes([18])+bytes(pk(DEV)),[AccountMeta(pk(dest),False,True),AccountMeta(pk(WSOL),False,False)])
    close=Instruction(pk(TOKEN),bytes([9]),[AccountMeta(pk(dest),False,True),AccountMeta(pk(DEV),False,True),AccountMeta(pk(DEV),True,False)])
    return [create,initialize,instruction('pump_amm','sweep_creator_fee',a),instruction('pump_amm','collect_coin_creator_fee',a),close],[temporary],{'kind':kind,'destination':dest,'expected':expected}

def claim_amount(tx,info):
    amount=0
    for group in tx['meta'].get('innerInstructions') or []:
        for ins in group['instructions']:
            parsed=ins.get('parsed',{});p=parsed.get('info',{})
            if info['kind']=='pump' and ins['programId']==SYSTEM and parsed.get('type')=='transfer' and p.get('source')==PUMP_VAULT and p.get('destination')==DEV:
                amount+=p['lamports']
            if info['kind']=='amm' and ins['programId']==TOKEN and parsed.get('type') in ('transfer','transferChecked') and p.get('source')==AMM_VAULT and p.get('destination')==info['destination']:
                amount+=int(p.get('amount',p.get('tokenAmount',{}).get('amount','0')))
    require(type(amount) is int and amount>0,'No attributable creator fee transfer; inspect finalized claim')
    return amount

OUTBOX='''CREATE TABLE IF NOT EXISTS outbox(signature TEXT PRIMARY KEY,kind TEXT NOT NULL,plan_id TEXT,wire TEXT NOT NULL,last_height INTEGER NOT NULL,info TEXT NOT NULL,state TEXT NOT NULL,created INTEGER NOT NULL,amount INTEGER NOT NULL);'''
def private_file(path):
    p=Path(path);s=p.stat();require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode&0o077,'Private file must be owned by this user with mode 0600');return p.read_text().strip()

class Worker:
    def __init__(self,config,rpc,ledger,live=False):
        self.c=config;self.rpc=rpc;self.l=ledger;self.live=live
        ledger.db.executescript(OUTBOX);ledger.db.execute('PRAGMA synchronous=FULL')
    def stopped(self):return Path(self.c['stop_file']).exists()
    def guard(self):require(not self.stopped(),'STOP file present')
    def signer(self):
        self.guard();require(self.live and self.c.get('enabled') is True,'Live payments disabled')
        key=Keypair.from_json(private_file(self.c['keypair_file']))
        require(str(key.pubkey())==DEV,'Signer is not the confirmed dev wallet');return key
    def simulate(self,tx):
        result=self.rpc.call('simulateTransaction',[base64.b64encode(bytes(tx)).decode(),{'encoding':'base64','sigVerify':False,'commitment':'finalized'}])['value']
        require(result['err'] is None,'Transaction simulation failed; nothing sent')
        return result.get('unitsConsumed')
    def enqueue(self,kind,plan_id,msg,extra,info,height,amount):
        self.guard();key=self.signer()
        if kind=='payout':
            used=self.l.db.execute("SELECT COALESCE(SUM(amount),0) FROM outbox WHERE kind='payout' AND state NOT IN ('failed','expired') AND created>=?",(int(time.time())-86400,)).fetchone()[0]
            require(used+amount<=self.c['daily_limit_lamports'],'Rolling 24-hour payout limit reached')
        tx=Transaction([key]+extra,msg,msg.recent_blockhash)
        require(len(bytes(tx))<=1232,'Transaction too large');self.simulate(tx)
        sig=str(tx.signatures[0]);wire=base64.b64encode(bytes(tx)).decode()
        # Commit signed bytes BEFORE the first network submission. Retries always reuse them.
        self.l.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?, ?,?)',(sig,kind,plan_id,wire,height,canonical(info),'pending',int(time.time()),amount))
        return sig
    def reconcile(self):
        pending=self.l.db.execute("SELECT signature,kind,plan_id,wire,last_height,info FROM outbox WHERE state='pending'").fetchall()
        for sig,kind,pid,wire,height,info in pending:
            status=self.rpc.call('getSignatureStatuses',[[sig],{'searchTransactionHistory':True}])['value'][0]
            if status and status.get('confirmationStatus')=='finalized':
                if status['err'] is not None:
                    self.l.db.execute("UPDATE outbox SET state='failed' WHERE signature=?",(sig,))
                    # Keep reservations: explicit operator review required after on-chain failure.
                    raise ValueError('Finalized transaction failed; reservation retained for review')
                tx=self.rpc.tx(sig)
                original=Transaction.from_bytes(base64.b64decode(wire))
                require(tx['transaction']['signatures']==[str(s) for s in original.signatures],'Finalized signature mismatch')
                if kind=='payout':
                    row=self.l.db.execute('SELECT status,signature FROM plans WHERE id=?',(pid,)).fetchone()
                    if row[0]!='paid':self.l.settle(pid,sig,tx)
                    else:require(row[1]==sig,'Plan settled by a different transaction')
                else:
                    amount=claim_amount(tx,json.loads(info))
                    row=self.l.db.execute('SELECT amount FROM receipts WHERE signature=?',(sig,)).fetchone()
                    if row:require(row[0]==amount,'Claim amount changed')
                    else:self.l.receipt(sig,amount,{'source':'worker-signed official Pump claim','slot':tx['slot'],'kind':kind})
                self.l.db.execute("UPDATE outbox SET state='done' WHERE signature=?",(sig,));continue
            if status:continue # Processed/confirmed is not enough to replace or settle.
            finalized_height=self.rpc.call('getBlockHeight',[{'commitment':'finalized'}])
            if finalized_height>height:
                # A null RPC history result is not proof of non-inclusion. Never replace automatically.
                raise ValueError('Expired transaction has uncertain history; STOP and reconcile before replacement')
            self.guard()
            if self.live:
                result=self.rpc.call('sendTransaction',[wire,{'encoding':'base64','skipPreflight':False,'preflightCommitment':'finalized','maxRetries':3}])
                require(result==sig,'RPC returned unexpected signature')
        return bool(self.l.db.execute("SELECT 1 FROM outbox WHERE state='pending'").fetchone())
    def cycle(self):
        self.guard()
        if self.reconcile():return {'state':'awaiting_finalization'}
        require(not self.l.db.execute("SELECT 1 FROM outbox WHERE state='failed'").fetchone(),'Failed transaction requires operator review')
        quote=market(self.rpc)
        snap=snapshot(self.rpc,quote['price'],quote['source'],quote['price_at'],self.c['excluded'])
        check=allocate(1000000000,snap)
        if not self.live:
            claims=[]
            for kind in ('pump','amm'):
                ixs,extra,info=claim_instructions(self.rpc,kind)
                if info['expected']>=self.c['minimum_claim_lamports']:
                    latest=self.rpc.call('getLatestBlockhash',[{'commitment':'finalized'}])['value']
                    msg=Message.new_with_blockhash(ixs,pk(DEV),Hash.from_string(latest['blockhash']))
                    try:info['simulation_units']=self.simulate(Transaction.new_unsigned(msg))
                    except ValueError:info['simulation_error']='Claim simulation failed; check working capital or changed program state'
                claims.append(info)
            return {'state':'read_only','claims_ready':all('simulation_error' not in x for x in claims),'dev_balance_lamports':self.rpc.call('getBalance',[DEV,{'commitment':'finalized'}])['value'],'price_usd':quote['price'],'eligible_holders':check['eligible_holders'],'accounts':snap['token_account_count'],'claims':claims,'no_transactions_sent':True}
        require(self.c.get('sole_creator_token_confirmed') is True,'Creator attribution not confirmed')
        if self.l.status()['unallocated_lamports']:self.l.round(snap)
        reserved=self.l.db.execute("SELECT id FROM plans WHERE status='reserved' ORDER BY id LIMIT 1").fetchone()
        if not reserved:
            unpaid=self.l.db.execute('SELECT MAX(total) FROM (SELECT SUM(amount) total FROM (SELECT wallet,amount FROM credits UNION ALL SELECT wallet,-amount FROM debits) GROUP BY wallet)').fetchone()[0]
            if unpaid and unpaid>=self.c['minimum_payout_lamports']:reserved=(self.l.plan(self.c['minimum_payout_lamports'])['plan_id'],)
        if reserved:
            pid=reserved[0];require(not self.l.db.execute("SELECT 1 FROM outbox WHERE plan_id=? AND state!='expired'",(pid,)).fetchone(),'Existing payout attempt requires reconciliation')
            prepared=prepare(self.l,self.rpc,pid,self.c['network_reserve_lamports'])
            require(self.rpc.call('getBlockHeight',[{'commitment':'finalized'}])<=prepared['last_valid_block_height'],'Prepared payout expired; review required')
            body=json.loads(self.l.db.execute('SELECT body FROM plans WHERE id=?',(pid,)).fetchone()[0])
            msg=Message.from_bytes(transaction_message(body,pid,prepared['blockhash']))
            self.enqueue('payout',pid,msg,[],{},prepared['last_valid_block_height'],sum(x['lamports'] for x in body['transfers']))
            self.reconcile();return {'state':'payout_pending','plan':pid}
        for kind in ('pump','amm'):
            ixs,extra,info=claim_instructions(self.rpc,kind)
            if info['expected']<self.c['minimum_claim_lamports']:continue
            balance=self.rpc.call('getBalance',[DEV,{'commitment':'finalized'}])['value']
            # Require separate working capital for ATA rent / instruction fees.
            credits=self.l.db.execute("SELECT COALESCE(SUM(amount),0) FROM credits").fetchone()[0]
            paid=self.l.db.execute("SELECT COALESCE(SUM(d.amount),0) FROM debits d JOIN plans p ON p.id=d.plan_id WHERE p.status='paid'").fetchone()[0]
            require(balance>=credits-paid+self.c['network_reserve_lamports']+10000000,'Insufficient separate claim working capital')
            latest=self.rpc.call('getLatestBlockhash',[{'commitment':'finalized'}])['value']
            msg=Message.new_with_blockhash(ixs,pk(DEV),Hash.from_string(latest['blockhash']))
            self.enqueue(kind,None,msg,extra,info,latest['lastValidBlockHeight'],0)
            self.reconcile();return {'state':'claim_pending','kind':kind}
        return {'state':'waiting_for_fees'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--config',required=True);ap.add_argument('--live',action='store_true');ap.add_argument('--loop',action='store_true');args=ap.parse_args();os.umask(0o077)
    c=json.loads(Path(args.config).read_text());state=Path(c['state_dir']);state.mkdir(mode=0o700,parents=True,exist_ok=True)
    require(not state.stat().st_mode&0o077,'State directory must have mode 0700')
    require(type(c['interval_seconds']) is int and c['interval_seconds']>=60,'Interval must be >=60 seconds')
    for field in ('daily_limit_lamports','minimum_claim_lamports','minimum_payout_lamports','network_reserve_lamports'):
        require(type(c[field]) is int and c[field]>0,'Invalid positive integer configuration')
    lock=(state/'worker.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ledger=Ledger(state/('live.sqlite' if args.live else 'preflight.sqlite'))
    worker=Worker(c,RPC(private_file(c['rpc_file'])),ledger,args.live)
    if args.live:worker.signer() # Validate key and explicit enable before any live ledger changes.
    while True:
        try:
            result=worker.cycle();result['checked_at']=int(time.time())
            tmp=state/'status.tmp';tmp.write_text(json.dumps(result,indent=2));tmp.replace(state/'status.json')
            print(json.dumps(result),flush=True)
        except Exception as e:
            # Do not print arbitrary RPC/config exceptions; they can contain credentials.
            failure={'state':'blocked','checked_at':int(time.time()),'error_type':type(e).__name__,'message':str(e) if isinstance(e,ValueError) else 'Operation failed; no new payment authorized'}
            tmp=state/'status.tmp';tmp.write_text(json.dumps(failure,indent=2));tmp.replace(state/'status.json')
            print(json.dumps(failure),flush=True)
            raise SystemExit(1)
        if not args.loop:break
        delay=20 if result['state'] in ('claim_pending','payout_pending','awaiting_finalization') else c['interval_seconds']
        for _ in range(delay):
            if worker.stopped():raise SystemExit('STOP file present')
            time.sleep(1)
if __name__=='__main__':main()
