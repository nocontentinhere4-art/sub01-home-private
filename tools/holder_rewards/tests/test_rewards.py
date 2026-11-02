import unittest,sys,tempfile,json,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rewards import *
A='2QUfGV4R3bDmKEDenmfCquumP5bWtRhyC94DBVQyzRuR'
B='3xEgQCqNhJGHqavQzEFpmet8Vtc6o1L43snhRFeVLE1w'
C='AgatsuC3PAazEz18dsWperLcjoSidPFGiMbwqvAsZdT5'
NOW=1700000000

def snap(balances=None):return {'mint':MINT,'decimals':6,'slot':123,'captured_at':NOW,'price_at':NOW,'price_usd':'0.01','price_source':'TEST ONLY','source':'fixture','balances':balances or {A:2000000000,B:6000000000,DEV:100000000000},'excluded':[DEV]}

def payment(plan,sig='s',pid=None):
    xs=plan['transfers'];fee=5000;total=sum(x['lamports'] for x in xs);ks=[{'pubkey':DEV,'signer':True}]+[{'pubkey':x['destination'],'signer':False} for x in xs]
    return {'blockTime':plan['created_at'],'transaction':{'signatures':[sig],'message':{'accountKeys':ks,'instructions':[{'programId':SYSTEM,'parsed':{'type':'transfer','info':{'source':DEV,'destination':x['destination'],'lamports':x['lamports']}}} for x in xs]+[{'programId':MEMO,'parsed':'SUB01_REWARDS:'+(pid or plan['plan_id'])}]}},'meta':{'err':None,'fee':fee,'preBalances':[total+fee+100]+[100]*len(xs),'postBalances':[100]+[100+x['lamports'] for x in xs],'innerInstructions':[]}}

class MathTests(unittest.TestCase):
 def test_5_95(self):
    r=allocate(1000000000,snap(),NOW);self.assertEqual(r['creator_retained_lamports'],50000000);self.assertEqual(r['allocations'],{A:237500000,B:712500000})
 def test_threshold_exact_and_below(self):
    r=allocate(1000,snap({A:2000000000,B:1999999999}),NOW);self.assertEqual(r['allocations'],{A:950})
 def test_all_excluded_fails(self):
    with self.assertRaises(ValueError):allocate(100,snap({DEV:10**14}),NOW)
 def test_stale_price_or_snapshot(self):
    for field in ['captured_at','price_at']:
      s=snap();s[field]=NOW-301
      with self.assertRaises(ValueError):allocate(100,s,NOW)
 def test_bad_prices(self):
    for p in ['NaN','Infinity','0','-1','1e1000']:
      s=snap();s['price_usd']=p
      with self.assertRaises(ValueError):allocate(100,s,NOW)
 def test_integer_conservation_many_amounts(self):
    for amount in range(1,1000):
      r=allocate(amount,snap(),NOW);self.assertEqual(sum(r['allocations'].values())+r['creator_retained_lamports'],amount)
      self.assertLessEqual(r['creator_retained_lamports']*100,amount*5)
 def test_reordering_does_not_change_rounding(self):
    a=snap({A:2000000000,B:2000000000,C:2000000000});b=snap(dict(reversed(list(a['balances'].items()))))
    self.assertEqual(allocate(101,a,NOW),allocate(101,b,NOW))
 def test_invalid_address_and_negative(self):
    for owner,amount in [('invalid',2000000000),(A,-1)]:
      with self.assertRaises(ValueError):allocate(10,snap({owner:amount}),NOW)
 def test_new_holders_next_snapshot(self):
    r1=allocate(100,snap({A:2000000000}),NOW);r2=allocate(100,snap({A:2000000000,B:2000000000}),NOW)
    self.assertNotIn(B,r1['allocations']);self.assertIn(B,r2['allocations'])

class LedgerTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'x.sqlite');self.l=Ledger(self.path)
 def tearDown(self):self.l.db.close();self.tmp.cleanup()
 def credit(self,sig='fee1',amount=1000000000):self.l.receipt(sig,amount,{'fixture':True});return self.l.round(snap(),NOW)
 def test_duplicate_receipt(self):
    self.l.receipt('same',100,{})
    with self.assertRaises(sqlite3.IntegrityError):self.l.receipt('same',100,{})
 def test_round_atomic_on_failure(self):
    self.l.receipt('fee',100,{})
    with self.assertRaises(ValueError):self.l.round(snap({DEV:10**14}),NOW)
    self.assertEqual(self.l.status()['unallocated_lamports'],100);self.assertEqual(self.l.status()['rounds'],0)
 def test_receipt_allocated_only_once(self):
    self.credit()
    with self.assertRaises(ValueError):self.l.round(snap(),NOW)
 def test_reservation_across_connections(self):
    self.credit();p=self.l.plan();other=Ledger(self.path)
    try:
      with self.assertRaises(ValueError):other.plan()
    finally:other.db.close()
 def test_dust_carries_and_not_repaid(self):
    self.credit('fee1',1000)
    with self.assertRaises(ValueError):self.l.plan(1000)
    self.credit('fee2',1000);p=self.l.plan(1000);self.assertEqual(p['transfers'][0]['lamports'],1424)
    self.l.settle(p['plan_id'],'sig1',payment(p,'sig1'))
    with self.assertRaises(ValueError):self.l.plan(1000)
 def test_exact_payment_and_duplicate_settlement(self):
    self.credit();p=self.l.plan();self.l.settle(p['plan_id'],'sig',payment(p,'sig'))
    with self.assertRaises(ValueError):self.l.settle(p['plan_id'],'sig',payment(p,'sig'))
 def test_wrong_amount_keeps_reservation(self):
    self.credit();p=self.l.plan();t=payment(p);t['transaction']['message']['instructions'][0]['parsed']['info']['lamports']+=1
    with self.assertRaises(ValueError):self.l.settle(p['plan_id'],'s',t)
    self.assertEqual(self.l.status()['plans'][0]['status'],'reserved')
 def test_wrong_memo_or_old_tx(self):
    self.credit();p=self.l.plan()
    for mode in ['memo','old']:
      t=payment(p)
      if mode=='memo':t['transaction']['message']['instructions'][-1]['parsed']='unrelated'
      else:t['blockTime']=p['created_at']-1
      with self.assertRaises(ValueError):self.l.settle(p['plan_id'],'s',t)
 def test_signature_replay(self):
    self.credit();p=self.l.plan();self.l.settle(p['plan_id'],'s',payment(p))
    self.credit('fee2');q=self.l.plan()
    with self.assertRaises(sqlite3.IntegrityError):self.l.settle(q['plan_id'],'s',payment(q))
 def test_no_send_or_sign_command(self):
    src=Path(__file__).resolve().parents[1].joinpath('rewards.py').read_text();self.assertNotIn("call('sendTransaction'",src)

class SnapshotTests(unittest.TestCase):
 def test_account_aggregation(self):
    class Fake:
      def call(self,method,args):
        if method=='getAccountInfo':return {'context':{'slot':1},'value':{'owner':TOKEN,'data':{'parsed':{'info':{'decimals':6,'supply':'2000000000'}}}}}
        return {'context':{'slot':2},'value':[{'pubkey':str(i),'account':{'owner':TOKEN,'data':{'parsed':{'type':'account','info':{'owner':A,'mint':MINT,'tokenAmount':{'decimals':6,'amount':'1000000000'}}}}}} for i in range(2)]}
    s=snapshot(Fake(),'0.01','test',NOW,[],NOW);self.assertEqual(s['balances'][A],2000000000);self.assertEqual(s['slot'],2)


class MessageTests(unittest.TestCase):
 def test_message_structure(self):
    plan={'transfers':[{'destination':A,'lamports':123}]}
    msg=transaction_message(plan,'abc',SYSTEM)
    self.assertEqual(msg[:4],bytes([1,0,2,4]))
    self.assertIn(struct.pack('<IQ',2,123),msg)
    self.assertTrue(msg.endswith(b'SUB01_REWARDS:abc'))
 def test_maximum_batch_fits_packet(self):
    # Use distinct valid pubkeys from deterministic seed byte arrays.
    def encode(b):
      n=int.from_bytes(b,'big');out=''
      while n:n,r=divmod(n,58);out=ALPHABET[r]+out
      return '1'*(len(b)-len(b.lstrip(bytes([0]))))+out
    p={'transfers':[{'destination':encode(bytes([i])*32),'lamports':2**32} for i in range(1,9)]}
    self.assertLessEqual(65+len(transaction_message(p,'a'*64,SYSTEM)),1232)
 def test_insufficient_funds_refused(self):
    l=Ledger(':memory:');l.receipt('x',1000000000,{});l.round(snap(),NOW);p=l.plan()
    class Fake:
      def call(self,m,a):
        if m=='getLatestBlockhash':return {'value':{'blockhash':SYSTEM,'lastValidBlockHeight':42}}
        if m=='getFeeForMessage':return {'value':5000}
        return {'value':1}
    with self.assertRaises(ValueError):prepare(l,Fake(),p['plan_id'])
    l.db.close()


class PreparationTests(unittest.TestCase):
 def test_preparation_reuses_exact_bytes(self):
    l=Ledger(':memory:');l.receipt('x',1000000000,{});l.round(snap(),NOW);p=l.plan()
    class Fake:
      def __init__(self):self.calls=0
      def call(self,m,a):
        self.calls+=1
        if m=='getLatestBlockhash':return {'value':{'blockhash':SYSTEM,'lastValidBlockHeight':42}}
        if m=='getFeeForMessage':return {'value':5000}
        return {'value':2000000000}
    f=Fake();first=prepare(l,f,p['plan_id']);calls=f.calls;second=prepare(l,f,p['plan_id'])
    self.assertEqual(first,second);self.assertEqual(f.calls,calls);l.db.close()
 def test_token2022_metadata_supported_and_supply_incomplete_rejected(self):
    class Fake:
      supply='2000000000'
      extensions=[{'extension':'metadataPointer'},{'extension':'tokenMetadata'}]
      def call(self,m,a):
        if m=='getAccountInfo':return {'context':{'slot':1},'value':{'owner':TOKEN2022,'data':{'parsed':{'info':{'decimals':6,'supply':self.supply,'extensions':self.extensions,'mintAuthority':None}}}}}
        return {'context':{'slot':2},'value':[{'pubkey':'account','account':{'owner':TOKEN2022,'data':{'parsed':{'type':'account','info':{'owner':A,'mint':MINT,'tokenAmount':{'decimals':6,'amount':'2000000000'}}}}}}]}
    f=Fake();self.assertEqual(snapshot(f,'1','test',NOW,[],NOW)['token_program'],TOKEN2022)
    f.supply='3000000000'
    with self.assertRaises(ValueError):snapshot(f,'1','test',NOW,[],NOW)
    f.supply='2000000000';f.extensions=[{'extension':'transferFeeConfig'}]
    with self.assertRaises(ValueError):snapshot(f,'1','test',NOW,[],NOW)

if __name__=='__main__':unittest.main()
