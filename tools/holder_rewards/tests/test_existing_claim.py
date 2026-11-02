import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import import_existing_claim as m

class ExistingClaimTests(unittest.TestCase):
    def fixture(self):
        dest=m.ata(m.DEV);fee=11736
        return {'transaction':{'signatures':[m.SIGNATURE],'message':{
            'accountKeys':[{'pubkey':m.DEV,'signer':True}],
            'instructions':[{'programId':m.AMM,'data':'ToNg27JNfmT','accounts':[m.WSOL,m.TOKEN,m.DEV,m.AMM_AUTH,m.AMM_VAULT,dest]},
                {'programId':m.TOKEN,'parsed':{'type':'closeAccount','info':{'account':dest,'destination':m.DEV,'owner':m.DEV}}}]}},
            'meta':{'err':None,'fee':fee,'preBalances':[20000000],'postBalances':[20000000+m.AMOUNT-fee],
                'innerInstructions':[{'index':0,'instructions':[{'programId':m.TOKEN,'parsed':{'type':'transferChecked','info':{'source':m.AMM_VAULT,'destination':dest,'tokenAmount':{'amount':str(m.AMOUNT)}}}}]}]}}
    def test_verified_amount(self):self.assertEqual(m.verify(self.fixture()),m.AMOUNT)
    def test_unrelated_deposit_cannot_increase_receipt(self):
        tx=self.fixture();tx['meta']['postBalances'][0]+=20000000
        with self.assertRaises(ValueError):m.verify(tx)
    def test_wrong_vault_rejected(self):
        tx=self.fixture();tx['transaction']['message']['instructions'][0]['accounts'][4]=m.DEV
        with self.assertRaises(ValueError):m.verify(tx)
    def test_duplicate_claim_rejected(self):
        tx=self.fixture();tx['transaction']['message']['instructions'].append(copy.deepcopy(tx['transaction']['message']['instructions'][0]))
        with self.assertRaises(ValueError):m.verify(tx)
    def test_unwrap_required(self):
        tx=self.fixture();tx['transaction']['message']['instructions'].pop()
        with self.assertRaises(ValueError):m.verify(tx)
