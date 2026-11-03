import unittest,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recover_expired import check_source,apply_recovery

class RPC:
    def __init__(self,override=None):self.override=override or {}
    def call(self,m,p):
        defaults={'getBlockHeight':200,'isBlockhashValid':{'value':False},'getSignatureStatuses':{'value':[None]},'getTransaction':None,'getSignaturesForAddress':[{'signature':'other','blockTime':500}]}
        return self.override.get(m,defaults[m])
class RecoveryTests(unittest.TestCase):
    def test_history_and_expiry_pass(self):self.assertTrue(check_source(RPC(),'target','hash',100,1000)['signature_absent'])
    def test_evidence_failures_rejected(self):
        cases=[{'getBlockHeight':110},{'isBlockhashValid':{'value':True}},{'getSignatureStatuses':{'value':[{'err':None}]}},{'getTransaction':{'meta':{}}},{'getSignaturesForAddress':[]},{'getSignaturesForAddress':[{'signature':'target','blockTime':500}]},{'getSignaturesForAddress':[{'signature':'other','blockTime':None}]}]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ValueError):check_source(RPC(case),'target','hash',100,1000)
    def test_incomplete_repeating_history_rejected(self):
        with self.assertRaises(ValueError):check_source(RPC({'getSignaturesForAddress':[{'signature':'other','blockTime':990}]}),'target','hash',100,1000)
    def test_recovery_preserves_reservations_and_is_not_repeatable(self):
        db=sqlite3.connect(':memory:',isolation_level=None)
        db.executescript('CREATE TABLE outbox(signature,plan_id,wire,last_height,created,amount,state,kind);CREATE TABLE plans(id,status);CREATE TABLE prepared(plan_id,body);CREATE TABLE debits(plan_id,wallet,amount);')
        row=('sig','plan','wire',100,1000,55)
        db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',row+('pending','payout'))
        db.execute("INSERT INTO plans VALUES('plan','reserved')");db.execute("INSERT INTO prepared VALUES('plan','old')");db.execute("INSERT INTO debits VALUES('plan','wallet',55)")
        apply_recovery(db,row,{'verified':True})
        self.assertEqual(db.execute('SELECT state FROM outbox').fetchone()[0],'expired')
        self.assertEqual(db.execute('SELECT status FROM plans').fetchone()[0],'reserved')
        self.assertEqual(db.execute('SELECT amount FROM debits').fetchone()[0],55)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM prepared').fetchone()[0],0)
        with self.assertRaises(ValueError):apply_recovery(db,row,{'verified':True})

class ClaimRecoveryTests(unittest.TestCase):
    def test_expired_claim_does_not_create_income_or_touch_holder_reservations(self):
        db=sqlite3.connect(':memory:',isolation_level=None)
        db.executescript('CREATE TABLE outbox(signature,plan_id,wire,last_height,created,amount,state,kind);CREATE TABLE receipts(signature,amount);CREATE TABLE debits(plan_id,wallet,amount);')
        row=('claim',None,'wire',100,1000,0)
        db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',row+('pending','amm'))
        db.execute("INSERT INTO debits VALUES('other','holder',55)")
        apply_recovery(db,row,{'verified':True},'amm')
        self.assertEqual(db.execute('SELECT state FROM outbox').fetchone()[0],'expired')
        self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],0)
        self.assertEqual(db.execute('SELECT amount FROM debits').fetchone()[0],55)
    def test_already_recorded_claim_is_not_replaced(self):
        db=sqlite3.connect(':memory:',isolation_level=None)
        db.executescript('CREATE TABLE outbox(signature,plan_id,wire,last_height,created,amount,state,kind);CREATE TABLE receipts(signature,amount);')
        row=('claim',None,'wire',100,1000,0)
        db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',row+('pending','amm'))
        db.execute("INSERT INTO receipts VALUES('claim',123)")
        with self.assertRaises(ValueError):apply_recovery(db,row,{},'amm')
        self.assertEqual(db.execute('SELECT state FROM outbox').fetchone()[0],'pending')
