"""Synthetic demonstration only. No network, no wallets, no real funds."""
import json,tempfile,time
from pathlib import Path
from rewards import Ledger,DEV,MINT
A='2QUfGV4R3bDmKEDenmfCquumP5bWtRhyC94DBVQyzRuR'
B='3xEgQCqNhJGHqavQzEFpmet8Vtc6o1L43snhRFeVLE1w'
C='AgatsuC3PAazEz18dsWperLcjoSidPFGiMbwqvAsZdT5'
now=int(time.time())
s={'mint':MINT,'decimals':6,'slot':0,'captured_at':now,'price_at':now,'price_usd':'0.01','price_source':'SYNTHETIC EXAMPLE — not current market price','source':'fixture','balances':{A:2000000000,B:6000000000,C:1999999999,DEV:100000000000},'excluded':[DEV]}
with tempfile.TemporaryDirectory() as d:
 l=Ledger(str(Path(d)/'demo.sqlite'));l.receipt('SYNTHETIC-NOT-A-REAL-TRANSACTION',1000000000,{'demo':True});r=l.round(s);p=l.plan()
 print(json.dumps({'simulation_only':True,'fees_SOL':'1.000000000','creator_retained_SOL':'0.050000000','holder_pool_SOL':'0.950000000','example_holdings_USD':{'holder_A':'20','holder_B':'60','holder_C':'19.99999999'},'allocation':r,'unsigned_instruction_plan':p},indent=2));l.db.close()
