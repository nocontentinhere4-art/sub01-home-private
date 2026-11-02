import unittest, tempfile, json, sys, base64, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import automatic as a
from rewards import Ledger, DEV, TOKEN, SYSTEM
from solders.keypair import Keypair
from solders.message import Message
from solders.hash import Hash
from solders.transaction import Transaction

class FakeRPC:
    def __init__(self):self.status=None;self.height=10;self.calls=[];self.txdata=None
    def call(self,m,p):
        self.calls.append((m,p))
        if m=='getSignatureStatuses':return {'value':[self.status]}
        if m=='getBlockHeight':return self.height
        if m=='sendTransaction':return str(Transaction.from_bytes(base64.b64decode(p[0])).signatures[0])
        if m=='simulateTransaction':return {'value':{'err':None}}
        raise AssertionError(m)
    def tx(self,s):return self.txdata

class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.l=Ledger(Path(self.tmp.name)/'db.sqlite');self.rpc=FakeRPC()
        self.c={'stop_file':str(Path(self.tmp.name)/'STOP'),'enabled':False,'daily_limit_lamports':1000}
        self.w=a.Worker(self.c,self.rpc,self.l,True)
        self.k=Keypair();self.msg=Message.new_with_blockhash([],self.k.pubkey(),Hash.default());self.tx=Transaction([self.k],self.msg,Hash.default());self.sig=str(self.tx.signatures[0]);self.wire=base64.b64encode(bytes(self.tx)).decode()
    def tearDown(self):self.l.db.close();self.tmp.cleanup()
    def pending(self,kind='amm',info=None):
        self.l.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?,?)',(self.sig,kind,None,self.wire,20,json.dumps(info or {'kind':'amm','destination':'temp'}),'pending',int(time.time()),0))
    def test_same_wire_retransmitted_after_lost_response(self):
        self.pending();self.w.reconcile();self.w.reconcile()
        sent=[p[0] for m,p in self.rpc.calls if m=='sendTransaction'];self.assertEqual(sent,[self.wire,self.wire])
    def test_confirmed_never_replaced_or_paid(self):
        self.pending();self.rpc.status={'confirmationStatus':'confirmed','err':None};self.rpc.height=999
        self.assertTrue(self.w.reconcile());self.assertFalse(any(m=='sendTransaction' for m,p in self.rpc.calls))
        self.assertEqual(self.l.status()['receipts'],0)
    def test_unknown_expired_stays_reserved(self):
        self.pending();self.rpc.height=21
        with self.assertRaisesRegex(ValueError,'uncertain'):self.w.reconcile()
        self.assertEqual(self.l.db.execute('SELECT state FROM outbox').fetchone()[0],'pending')
        self.assertFalse(any(m=='sendTransaction' for m,p in self.rpc.calls))
    def test_stop_prevents_rebroadcast(self):
        self.pending();Path(self.c['stop_file']).touch()
        with self.assertRaisesRegex(ValueError,'STOP'):self.w.reconcile()
        self.assertFalse(any(m=='sendTransaction' for m,p in self.rpc.calls))
    def test_live_disabled_does_not_load_key(self):
        with self.assertRaisesRegex(ValueError,'disabled'):self.w.signer()
    def test_failed_claim_not_credited(self):
        self.pending();self.rpc.status={'confirmationStatus':'finalized','err':{'InstructionError':[0,'x']}}
        with self.assertRaises(ValueError):self.w.reconcile()
        self.assertEqual(self.l.status()['receipts'],0)
    def claim(self):
        return {'transaction':{'signatures':[self.sig]},'slot':1,'meta':{'innerInstructions':[{'instructions':[
            {'programId':TOKEN,'parsed':{'type':'transfer','info':{'source':a.AMM_VAULT,'destination':'temp','amount':'1234'}}},
            {'programId':SYSTEM,'parsed':{'type':'transfer','info':{'source':'unrelated','destination':DEV,'lamports':999999}}},
            {'programId':TOKEN,'parsed':{'type':'closeAccount','info':{'account':'temp','destination':DEV}}}
        ]}]}}
    def test_only_fee_vault_transfer_counted_not_rent_or_deposits(self):
        self.assertEqual(a.claim_amount(self.claim(),{'kind':'amm','destination':'temp'}),1234)
        with self.assertRaises(ValueError):a.claim_amount(self.claim(),{'kind':'amm','destination':'other'})
    def test_crash_after_receipt_before_outbox_ack_is_idempotent(self):
        self.pending();self.rpc.status={'confirmationStatus':'finalized','err':None};self.rpc.txdata=self.claim()
        self.l.receipt(self.sig,1234,{})
        self.assertFalse(self.w.reconcile());self.assertEqual(self.l.status()['receipts'],1)
        self.assertEqual(self.l.status()['unallocated_lamports'],1234)
    def test_signed_bytes_saved_before_any_network_send(self):
        with patch.object(self.w,'signer',return_value=self.k):
            self.w.enqueue('amm',None,self.msg,[],{'kind':'amm'},20,0)
        self.assertIsNotNone(self.l.db.execute('SELECT wire FROM outbox').fetchone())
        self.assertFalse(any(m=='sendTransaction' for m,p in self.rpc.calls))
    def test_daily_cap_prevents_sign_and_send(self):
        with patch.object(self.w,'signer',return_value=self.k):
            with self.assertRaisesRegex(ValueError,'limit'):self.w.enqueue('payout','pid',self.msg,[],{},20,1001)
        self.assertEqual(self.l.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
    def test_stale_or_future_price_rejected(self):
        for ts in (1000-121,1001):
            with patch.object(a,'http_json',return_value={'solana':{'usd':100,'last_updated_at':ts}}):
                with self.assertRaisesRegex(ValueError,'Stale'):a.sol_price(1000)
    def test_current_price(self):
        with patch.object(a,'http_json',return_value={'solana':{'usd':91.5,'last_updated_at':999}}):
            self.assertEqual(str(a.sol_price(1000)[0]),'91.5')
    def test_negative_virtual_reserves_preserved(self):
        b=bytearray(287);b[:8]=bytes([241,154,109,4,17,177,109,188]);b[43:75]=bytes(a.pk(a.MINT));b[75:107]=bytes(a.pk(a.WSOL));b[211:243]=bytes(a.pk(DEV));b[245:261]=(-100).to_bytes(16,'little',signed=True)
        v={'owner':a.AMM,'data':[base64.b64encode(b).decode(),'base64']}
        self.assertEqual(a.pool_fields(v)['virtual_quote'],-100)
        b[211:243]=bytes(a.pk(SYSTEM));v['data'][0]=base64.b64encode(b).decode()
        with self.assertRaisesRegex(ValueError,'creator'):a.pool_fields(v)

if __name__=='__main__':unittest.main()
