#!/usr/bin/env python3
"""SUB-01 reward accounting. Builds plans; never signs or sends transactions."""
import argparse, hashlib, json, sqlite3, time, urllib.request, os, struct, base64
from decimal import Decimal, InvalidOperation
from pathlib import Path

MINT='6WCtKQfkWurd77tCCAYWuL5TwyAvuovTzworfnfupump'
DEV='HMPUiULXumamWDhuoKap6ty2hQ7V7GQwi8PZ7pGx6STQ'
TOKEN='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
TOKEN2022='TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
SYSTEM='11111111111111111111111111111111'
MEMO='MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr'
ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def require(ok, message):
    if not ok: raise ValueError(message)

def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'))
def digest(v): return hashlib.sha256(canonical(v).encode()).hexdigest()
def integer(v):
    require(type(v) is int and v >= 0, 'Expected nonnegative integer')
    return v

def address(s):
    require(isinstance(s,str) and 32 <= len(s) <= 44,'Invalid address')
    n=0
    for c in s:
        require(c in ALPHABET,'Invalid base58 address'); n=n*58+ALPHABET.index(c)
    b=b'\0'*(len(s)-len(s.lstrip('1')))+(n.to_bytes((n.bit_length()+7)//8,'big') if n else b'')
    require(len(b)==32,'Address must decode to 32 bytes')
    return b

def on_curve(s):
    b=address(s); v=int.from_bytes(b,'little'); y=v&((1<<255)-1); sign=v>>255; p=2**255-19
    if y>=p:return False
    d=(-121665*pow(121666,p-2,p))%p; den=(d*y*y+1)%p
    if not den:return False
    x2=((y*y-1)*pow(den,p-2,p))%p
    return (sign==0 if x2==0 else pow(x2,(p-1)//2,p)==1)

def money(v):
    try:d=Decimal(str(v))
    except InvalidOperation:raise ValueError('Invalid decimal')
    require(d.is_finite() and d>0,'Price must be finite and positive')
    require(len(d.as_tuple().digits)<=30 and abs(d.as_tuple().exponent)<=30,'Price precision out of range')
    return d

class RPC:
    def __init__(self,url):
        require(url.startswith('https://'),'HTTPS RPC required'); self.url=url
    def call(self,method,params):
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
        req=urllib.request.Request(self.url,data=body,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: result=json.load(r)
        except Exception:raise ValueError('RPC unavailable; endpoint details withheld') from None
        require('error' not in result,'RPC rejected request; no ledger change')
        return result['result']
    def tx(self,sig):
        require(isinstance(sig,str) and 64<=len(sig)<=90 and all(c in ALPHABET for c in sig),'Invalid transaction signature')
        tx=self.call('getTransaction',[sig,{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':0}])
        require(tx is not None and tx.get('meta') is not None and tx['meta']['err'] is None,'Transaction not successfully finalized')
        require(sig in tx['transaction']['signatures'],'Signature mismatch')
        return tx

def snapshot(rpc,price,price_source,price_at,excluded,now=None):
    now=int(time.time()) if now is None else now
    money(price); require(0<=now-integer(price_at)<=300,'Price older than 5 minutes or from future')
    require(bool(price_source),'Price source required')
    info=rpc.call('getAccountInfo',[MINT,{'encoding':'jsonParsed','commitment':'finalized'}])
    value=info['value']; require(value and value['owner'] in (TOKEN,TOKEN2022),'Unsupported token program')
    program=value['owner'];mint_info=value['data']['parsed']['info']
    require(mint_info.get('mintAuthority') is None,'Mint supply must be fixed')
    allowed={'metadataPointer','tokenMetadata'}
    require(all(x['extension'] in allowed for x in mint_info.get('extensions',[])),'Unsupported mint extensions: manual review required')
    decimals=value['data']['parsed']['info']['decimals']; integer(decimals);require(decimals<=18,'Unsupported decimals')
    result=rpc.call('getProgramAccounts',[program,{'encoding':'jsonParsed','commitment':'finalized','withContext':True,'minContextSlot':info['context']['slot'],'filters':[{'memcmp':{'offset':0,'bytes':MINT}}]}])
    balances={};seen=set()
    for row in result['value']:
        require(row['pubkey'] not in seen,'Duplicate token account');seen.add(row['pubkey'])
        require(row['account']['owner']==program,'Wrong token program')
        parsed=row['account']['data']['parsed'];require(parsed['type']=='account','Wrong account type'); data=parsed['info']
        require(data['mint']==MINT and data['tokenAmount']['decimals']==decimals,'Mint/decimals mismatch')
        owner=data['owner'];address(owner); amount=int(data['tokenAmount']['amount']);integer(amount)
        balances[owner]=balances.get(owner,0)+amount
    require(seen,'Empty RPC account response')
    require(sum(balances.values())==int(value['data']['parsed']['info']['supply']),'Incomplete snapshot or supply changed: retry; never distribute from a partial list')
    return {'mint':MINT,'token_program':program,'supply_raw':int(mint_info['supply']),'decimals':decimals,'slot':result['context']['slot'],'captured_at':now,'price_usd':str(price),'price_at':price_at,'price_source':price_source,'source':'finalized-getProgramAccounts','token_account_count':len(seen),'balances':balances,'excluded':sorted(set([DEV,SYSTEM]+excluded))}

def allocate(amount,snap,now=None):
    integer(amount);require(amount>0,'No fees to allocate');now=int(time.time()) if now is None else now
    require(snap['mint']==MINT,'Wrong mint'); decimals=integer(snap['decimals']);require(decimals<=18,'Unsupported decimals')
    for field in ('captured_at','price_at'):require(0<=now-integer(snap[field])<=300,'Stale or future snapshot/price')
    price=money(snap['price_usd']);numerator,denominator=price.as_integer_ratio()
    excluded=set(snap.get('excluded',[]))|{DEV,SYSTEM}; balances={}
    for owner,raw in snap['balances'].items():
        integer(raw);address(owner)
        if owner in excluded or not on_curve(owner):continue
        if raw*numerator >= 20*(10**decimals)*denominator:balances[owner]=raw
    require(balances,'No eligible holders: retain fees unallocated')
    # Round holder share upward, so creator never retains more than 5%.
    creator=amount*5//100;pool=amount-creator;total=sum(balances.values()); payouts={};remainders=[]
    for owner,raw in balances.items():
        payouts[owner],r=divmod(pool*raw,total);remainders.append((-r,owner))
    for _,owner in sorted(remainders)[:pool-sum(payouts.values())]:payouts[owner]+=1
    require(sum(payouts.values())+creator==amount,'Conservation failure')
    return {'creator_retained_lamports':creator,'holder_lamports':pool,'allocations':payouts,'eligible_holders':len(balances)}

SCHEMA='''
CREATE TABLE IF NOT EXISTS receipts(signature TEXT PRIMARY KEY,amount INTEGER NOT NULL,evidence TEXT NOT NULL,round_id TEXT);
CREATE TABLE IF NOT EXISTS rounds(id TEXT PRIMARY KEY,snapshot TEXT NOT NULL,result TEXT NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS credits(round_id TEXT NOT NULL,wallet TEXT NOT NULL,amount INTEGER NOT NULL,PRIMARY KEY(round_id,wallet));
CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,body TEXT NOT NULL,status TEXT NOT NULL,signature TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS prepared(plan_id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS debits(plan_id TEXT NOT NULL,wallet TEXT NOT NULL,amount INTEGER NOT NULL,PRIMARY KEY(plan_id,wallet));
'''
class Ledger:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=30,isolation_level=None);self.db.executescript(SCHEMA)
    def begin(self):self.db.execute('BEGIN IMMEDIATE')
    def receipt(self,sig,amount,evidence):
        integer(amount);require(0<amount<2**63,'Invalid receipt amount')
        self.db.execute('INSERT INTO receipts VALUES(?,?,?,NULL)',(sig,amount,canonical(evidence)))
    def round(self,snap,now=None):
        self.begin()
        try:
            rows=self.db.execute('SELECT signature,amount FROM receipts WHERE round_id IS NULL ORDER BY signature').fetchall()
            require(rows,'No unallocated receipts');result=allocate(sum(x[1] for x in rows),snap,now)
            rid=digest({'snapshot':snap,'receipts':rows})
            self.db.execute('INSERT INTO rounds VALUES(?,?,?,?)',(rid,canonical(snap),canonical(result),int(time.time())))
            self.db.executemany('INSERT INTO credits VALUES(?,?,?)',[(rid,w,a) for w,a in result['allocations'].items()])
            self.db.executemany('UPDATE receipts SET round_id=? WHERE signature=?',[(rid,x[0]) for x in rows]);self.db.commit()
            return {'round_id':rid,**result}
        except Exception:self.db.rollback();raise
    def plan(self,minimum=1000000,limit=8):
        integer(minimum);integer(limit);require(minimum>0 and 1<=limit<=8,'Invalid payout floor or batch size')
        self.begin()
        try:
            rows=self.db.execute('''SELECT wallet,SUM(amount) FROM (SELECT wallet,amount FROM credits UNION ALL SELECT wallet,-amount FROM debits) GROUP BY wallet HAVING SUM(amount)>=? ORDER BY wallet LIMIT ?''',(minimum,limit)).fetchall()
            require(rows,'No unreserved balance above payout floor')
            body={'version':1,'network':'solana-mainnet','fee_payer':DEV,'source':DEV,'mint':MINT,'transfers':[{'destination':w,'lamports':a,'program_id':SYSTEM} for w,a in rows],'network_fees':'fund separately; never deduct from holder credits','created_at':int(time.time()),'nonce':os.urandom(16).hex()}
            pid=digest(body);self.db.execute('INSERT INTO plans VALUES(?,?,?,NULL)',(pid,canonical(body),'reserved'))
            self.db.executemany('INSERT INTO debits VALUES(?,?,?)',[(pid,w,a) for w,a in rows]);self.db.commit()
            return {'plan_id':pid,'required_memo':'SUB01_REWARDS:'+pid,**body}
        except Exception:self.db.rollback();raise
    def settle(self,pid,sig,tx):
        self.begin()
        try:
            row=self.db.execute('SELECT body,status FROM plans WHERE id=?',(pid,)).fetchone();require(row and row[1]=='reserved','Unknown or already settled plan')
            verify_payout(json.loads(row[0]),sig,tx,pid)
            self.db.execute("UPDATE plans SET status='paid',signature=? WHERE id=?",(sig,pid));self.db.commit()
        except Exception:self.db.rollback();raise
    def status(self):
        return {'receipts':self.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],'rounds':self.db.execute('SELECT COUNT(*) FROM rounds').fetchone()[0],'plans':[dict(zip(('id','status','signature'),r)) for r in self.db.execute('SELECT id,status,signature FROM plans')],'unallocated_lamports':self.db.execute('SELECT COALESCE(SUM(amount),0) FROM receipts WHERE round_id IS NULL').fetchone()[0]}

def keys(tx): return [k['pubkey'] for k in tx['transaction']['message']['accountKeys']]
def receipt_amount(tx):
    ks=keys(tx);require(ks and ks[0]==DEV,'Dev must be fee payer for the manually claimed fee receipt')
    require(tx['transaction']['message']['accountKeys'][0]['signer'],'Dev must sign fee claim')
    meta=tx['meta'];require(meta['err'] is None,'Failed receipt')
    amount=meta['postBalances'][0]-meta['preBalances'][0]+meta['fee'];require(amount>0,'No incoming SOL credit')
    return amount

def verify_payout(plan,sig,tx,pid):
    require(sig in tx['transaction']['signatures'] and tx['meta']['err'] is None,'Failed/mismatched transaction')
    msg=tx['transaction']['message'];ks=keys(tx)
    require(ks[0]==DEV and msg['accountKeys'][0]['signer'],'Wrong fee payer')
    require(not tx['meta'].get('innerInstructions'),'Unexpected inner instructions')
    require(tx.get('blockTime') is not None and tx['blockTime']>=plan['created_at'],'Transaction predates reservation')
    transfers=[];memos=[]
    for ins in msg['instructions']:
        if ins['programId']=='ComputeBudget111111111111111111111111111111':continue
        if ins['programId']==MEMO:
            memos.append(ins.get('parsed'));continue
        parsed=ins.get('parsed',{});info=parsed.get('info',{})
        require(ins['programId']==SYSTEM and parsed.get('type')=='transfer' and info.get('source')==DEV,'Unexpected instruction')
        integer(info['lamports']);transfers.append((info['destination'],info['lamports']))
    require(memos==['SUB01_REWARDS:'+pid],'Missing/incorrect unique payout memo')
    expected=[(x['destination'],x['lamports']) for x in plan['transfers']]
    require(sorted(transfers)==sorted(expected),'Transfers do not exactly match reserved plan')
    require(tx['meta']['preBalances'][0]-tx['meta']['postBalances'][0]==sum(a for _,a in expected)+tx['meta']['fee'],'Unexpected wallet balance change')
    for dest,amount in expected:
        idx=ks.index(dest);require(tx['meta']['postBalances'][idx]-tx['meta']['preBalances'][idx]==amount,'Recipient balance mismatch')

def shortvec(n):
    out=bytearray()
    while True:
        byte=n&127;n>>=7;out.append(byte|(128 if n else 0))
        if not n:return bytes(out)

def transaction_message(plan,pid,blockhash):
    destinations=[x['destination'] for x in plan['transfers']]
    require(len(destinations)==len(set(destinations)) and DEV not in destinations,'Duplicate/self recipient')
    require(1<=len(destinations)<=8,'Unsupported batch size')
    addresses=[DEV]+destinations+[SYSTEM,MEMO];n=len(destinations)
    message=bytes([1,0,2])+shortvec(len(addresses))+b''.join(address(a) for a in addresses)+address(blockhash)
    instructions=[]
    for i,x in enumerate(plan['transfers']):
        amount=integer(x['lamports']);require(0<amount<2**64,'Invalid transfer amount')
        data=struct.pack('<IQ',2,amount)
        instructions.append(bytes([n+1])+shortvec(2)+bytes([0,i+1])+shortvec(len(data))+data)
    memo=('SUB01_REWARDS:'+pid).encode()
    instructions.append(bytes([n+2])+shortvec(0)+shortvec(len(memo))+memo)
    return message+shortvec(len(instructions))+b''.join(instructions)

def _prepare(ledger,rpc,pid,network_reserve=1000000):
    integer(network_reserve);require(network_reserve>=1000000,'Keep at least 0.001 SOL for network costs')
    row=ledger.db.execute('SELECT body,status FROM plans WHERE id=?',(pid,)).fetchone()
    require(row and row[1]=='reserved','Unknown or settled payout plan');plan=json.loads(row[0])
    latest=rpc.call('getLatestBlockhash',[{'commitment':'finalized'}])
    message=transaction_message(plan,pid,latest['value']['blockhash']);encoded=base64.b64encode(message).decode()
    fee=rpc.call('getFeeForMessage',[encoded,{'commitment':'finalized'}])['value'];require(type(fee)is int and fee>0,'Cannot estimate transaction fee')
    liability=ledger.db.execute("SELECT COALESCE(SUM(amount),0) FROM credits").fetchone()[0]-ledger.db.execute("SELECT COALESCE(SUM(d.amount),0) FROM debits d JOIN plans p ON p.id=d.plan_id WHERE p.status='paid'").fetchone()[0]
    unallocated=ledger.status()['unallocated_lamports'];balance=rpc.call('getBalance',[DEV,{'commitment':'finalized'}])['value']
    require(balance>=liability+unallocated+network_reserve+fee,'Wallet balance cannot cover all unpaid holder credits, unallocated fees and network reserve')
    unsigned=shortvec(1)+bytes(64)+message;require(len(unsigned)<=1232,'Transaction exceeds Solana packet size')
    return {'plan_id':pid,'unsigned_transaction_base64':base64.b64encode(unsigned).decode(),'required_signer':DEV,'last_valid_block_height':latest['value']['lastValidBlockHeight'],'blockhash':latest['value']['blockhash'],'network_fee_lamports':fee,'required_memo':'SUB01_REWARDS:'+pid,'transfers':plan['transfers'],'warning':'UNSIGNED: review, sign and submit with your wallet. Never prepare/re-sign an expired plan until any previously signed transaction is proven expired or failed. No automatic sending.'}

def prepare(ledger,rpc,pid,network_reserve=1000000):
    ledger.begin()
    try:
        row=ledger.db.execute('SELECT body FROM prepared WHERE plan_id=?',(pid,)).fetchone()
        if row:
            result=json.loads(row[0]);ledger.db.commit();return result
        result=_prepare(ledger,rpc,pid,network_reserve)
        ledger.db.execute('INSERT INTO prepared VALUES(?,?)',(pid,canonical(result)));ledger.db.commit();return result
    except Exception:ledger.db.rollback();raise

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--db',default='rewards.sqlite');ap.add_argument('--rpc-env',default='SOLANA_RPC_URL')
    sp=ap.add_subparsers(dest='command',required=True)
    s=sp.add_parser('snapshot');s.add_argument('--price-usd',required=True);s.add_argument('--price-source',required=True);s.add_argument('--price-at',required=True,type=int);s.add_argument('--exclusions',required=True);s.add_argument('--out',required=True)
    s=sp.add_parser('record-fees');s.add_argument('--signature',required=True);s.add_argument('--lamports',required=True,type=int);s.add_argument('--confirm-fee-claim-only',action='store_true',required=True)
    s=sp.add_parser('round');s.add_argument('--snapshot',required=True);s.add_argument('--confirm-exclusions-reviewed',action='store_true',required=True)
    s=sp.add_parser('plan');s.add_argument('--minimum-lamports',type=int,default=1000000);s.add_argument('--out',required=True)
    s=sp.add_parser('settle');s.add_argument('--plan-id',required=True);s.add_argument('--signature',required=True)
    s=sp.add_parser('export-plan');s.add_argument('--plan-id',required=True);s.add_argument('--out',required=True)
    s=sp.add_parser('prepare');s.add_argument('--plan-id',required=True);s.add_argument('--out',required=True)
    sp.add_parser('status');args=ap.parse_args();os.umask(0o077)
    rpc=RPC(os.environ.get(args.rpc_env,'')) if args.command in ('snapshot','record-fees','settle','prepare') else None
    ledger=Ledger(args.db)
    if args.command=='snapshot':
        exclusions=json.loads(Path(args.exclusions).read_text());require(isinstance(exclusions,list),'Exclusions must be a list')
        for w in exclusions:address(w)
        result=snapshot(rpc,args.price_usd,args.price_source,args.price_at,exclusions);Path(args.out).write_text(json.dumps(result,indent=2))
    elif args.command=='record-fees':
        tx=rpc.tx(args.signature);require(receipt_amount(tx)==args.lamports,'Declared fees differ from finalized SOL credit')
        ledger.receipt(args.signature,args.lamports,{'slot':tx['slot'],'blockTime':tx['blockTime'],'classification':'operator-attested fee claim; excludes refunds and unrelated deposits'});result={'recorded':True}
    elif args.command=='round':
        snap=json.loads(Path(args.snapshot).read_text());require(snap.get('source')=='finalized-getProgramAccounts','Unsupported snapshot source');result=ledger.round(snap)
    elif args.command=='plan':
        require(not Path(args.out).exists(),'Output exists; use a new filename')
        result=ledger.plan(args.minimum_lamports);Path(args.out).write_text(json.dumps(result,indent=2))
    elif args.command=='export-plan':
        row=ledger.db.execute('SELECT body,status FROM plans WHERE id=?',(args.plan_id,)).fetchone();require(row is not None,'Unknown plan');result={'plan_id':args.plan_id,'status':row[1],'required_memo':'SUB01_REWARDS:'+args.plan_id,**json.loads(row[0])};Path(args.out).write_text(json.dumps(result,indent=2))
    elif args.command=='prepare':
        require(not Path(args.out).exists(),'Output exists; use a new filename');result=prepare(ledger,rpc,args.plan_id);Path(args.out).write_text(json.dumps(result,indent=2))
    elif args.command=='settle':ledger.settle(args.plan_id,args.signature,rpc.tx(args.signature));result={'settled':True}
    else:result=ledger.status()
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    try:main()
    except (ValueError,sqlite3.IntegrityError,KeyError) as e:raise SystemExit('Refused: '+str(e))
