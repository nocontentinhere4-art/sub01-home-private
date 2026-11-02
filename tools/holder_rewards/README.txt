SUB-01 REWARDS — operator-assisted version, 2 November 2026

STATUS
Implemented and tested locally. Real Helius snapshot verified, but no funds
claimed, signed, sent or redistributed. No Pump.fun fee split was changed.
This is NOT an unattended payment service. Wallet signing and fee classification
remain with the operator. A production price feed/scheduler and wallet signing
interface are not included. Do not advertise automated live payouts yet.

CONFIRMED POLICY
Mint: 6WCtKQfkWurd77tCCAYWuL5TwyAvuovTzworfnfupump
Dev / funding / fee-payer wallet:
HMPUiULXumamWDhuoKap6ty2hQ7V7GQwi8PZ7pGx6STQ
5% remains in that wallet; 95% accrues to eligible holders, pro rata by token
balance at each new snapshot. Eligibility: balance worth >= USD20 at the supplied
USD quote. The dev wallet, the observed PumpSwap pool and off-curve program-owned
addresses are excluded. Other custodial/exchange/program accounts require review:
on-curve does not prove an address belongs to an individual. exclusions.json
must be reviewed before each real round. The owner confirmed no other owned
wallets to exclude.
The threshold is per wallet; it does not establish distinct human identities.

Integer lamport allocation: creator share rounded down, remaining lamports go to
holders using largest remainders and deterministic address tie-breaks. Thus
creator share is never greater than 5%. Payments below 0.001 SOL accumulate.
Credits already earned remain owed even if the holder later sells; future rounds
use the new balances and eligibility. No eligible holders means the entire fee
receipt remains unallocated, including the 5%, until a valid round is possible.
Network costs are paid separately by the dev wallet, never deducted from holder
credits. 5% is gross retention before the dev's network expenses.

WHAT IS IMPLEMENTED
- Finalized account enumeration with owner aggregation and fixed-supply equality
  check. Classic SPL and the actual SUB-01 Token-2022 metadata extensions supported.
  Unknown mint extensions fail closed. No paginated top-holders approximation.
- Exact decimal price threshold, 5-minute snapshot/quote age limit.
- SQLite transactional journal: receipt signatures cannot be credited twice;
  allocations immutable; concurrent workers cannot reserve the same credits twice.
- Batches of up to 8 native SOL transfers plus a unique plan memo.
- Unsigned legacy Solana transactions; no private keys and no sendTransaction call.
- Balance check covers all outstanding holder liabilities and unallocated fees,
  plus fee estimate and a 0.001 SOL network reserve.
- One prepared transaction per plan, persisted byte-for-byte. Repeated preparation
  returns the SAME transaction, preventing a fresh-blockhash duplicate payment.
- Settlement checks successful finalized transaction, exact recipients/amounts,
  memo, signer, account balance changes and unique signature.
- Failed settlement never frees a reservation. Ambiguous plans remain reserved.

LIMITATIONS / BEFORE FIRST REAL PAYMENT
1. This prototype does NOT prove a transaction is a Pump creator-fee claim.
   record-fees verifies finalized incoming native SOL and requires your explicit
   attestation that it contains only a fee claim (no rent refunds/trades/deposits).
   Use a new, separately claimed receipt; never re-credit old already-distributed
   income. It must have the dev wallet as fee payer. Review gross credit carefully.
2. Snapshot completeness compares mint supply and accounts from nearby finalized
   slots. A burn between reads causes rejection: capture again, never bypass it.
3. Price is operator-supplied with a source/time; it is not a tamper-proof oracle.
   Dexscreener was accessible in Chrome but rejected direct requests in this local
   environment. The live demonstration uses an observed quote of $0.00001593;
   this is NOT a price to reuse for later payments. Future production automation
   needs an independently validated, current quote feed. Retrieval time alone
   cannot prove market data freshness. Thin-market prices may be manipulated.
4. Expired/ambiguous transactions have no automatic release/replacement command.
   Reconcile them on chain before implementing an audited recovery flow. Do not
   delete SQLite rows or sign another freshly built transaction for the same plan.
5. A wallet integration to review, sign and submit the prepared transaction is
   still required. This package exports unsigned data; it is not a Phantom app.
6. No automatic fee claiming, timer, remote deployment or indefinite custody.
   No audit by an independent security reviewer. Kimi was waived by the owner.

RUN
Python 3.10+; standard library only.
  python3 -m unittest discover -s tests -v
  python3 demo.py
The demo uses an isolated temporary ledger, synthetic balances and NO network.

Keep a private operational directory, SQLite database and backups separate from
source control. The RPC URL belongs in SOLANA_RPC_URL in your process environment;
never commit it or put it in command-line arguments. The current local private
configuration is outside this deliverable, in work/holder-rewards/rpc-private.txt.
Do not print it. Example commands below use relative paths in this package.

1. After YOU claim new creator fees on Pump.fun, inspect that transaction:
  python3 rewards.py --db /PRIVATE/rewards.sqlite record-fees \
    --signature REAL_FINALIZED_CLAIM_SIGNATURE --lamports EXACT_GROSS_LAMPORTS \
    --confirm-fee-claim-only
2. Obtain a current independent USD quote and record its actual observation time:
  python3 rewards.py --db /PRIVATE/rewards.sqlite snapshot \
    --price-usd CURRENT_PRICE --price-source VERIFIED_QUOTE_URL \
    --price-at UNIX_TIMESTAMP --exclusions exclusions.json --out /PRIVATE/snapshot.json
3. Review exclusions and calculate while snapshot AND quote are <5 minutes old:
  python3 rewards.py --db /PRIVATE/rewards.sqlite round \
    --snapshot /PRIVATE/snapshot.json --confirm-exclusions-reviewed
4. Reserve the next batch; this is accounting only:
  python3 rewards.py --db /PRIVATE/rewards.sqlite plan --out /PRIVATE/plan-001.json
5. Prepare unsigned bytes and estimate the network fee:
  python3 rewards.py --db /PRIVATE/rewards.sqlite prepare \
    --plan-id PLAN_ID --out /PRIVATE/unsigned-001.json
6. Review/sign/submit externally with your wallet. Do not sign expired data.
7. Reconcile the actual finalized signature:
  python3 rewards.py --db /PRIVATE/rewards.sqlite settle \
    --plan-id PLAN_ID --signature REAL_PAYMENT_SIGNATURE
8. Repeat steps 4-7 for remaining batches. Check state:
  python3 rewards.py --db /PRIVATE/rewards.sqlite status
If writing a plan file failed after reservation, recover without duplicating it:
  python3 rewards.py --db /PRIVATE/rewards.sqlite export-plan \
    --plan-id PLAN_ID --out /PRIVATE/recovered-plan.json

REAL DATA VALIDATION
See live-simulation.json: 2,897 accounts / 2,896 owners at finalized slot 464606377;
raw balance sum equals supply 972462067129584. Fifty eligible wallets at the
observed quote after exclusions. Example budget 1 SOL, NOT actual fees collected.
RPC accepted the unsigned message and estimated 5,000 lamports for that sample.
All these numbers describe one snapshot, not future eligibility or guaranteed fees.

Sources inspected:
https://pump.fun/coin/6WCtKQfkWurd77tCCAYWuL5TwyAvuovTzworfnfupump
https://pump.fun/holder-rewards
https://api.dexscreener.com/latest/dex/tokens/6WCtKQfkWurd77tCCAYWuL5TwyAvuovTzworfnfupump
Solana JSON-RPC getAccountInfo/getProgramAccounts/getFeeForMessage via Helius.
