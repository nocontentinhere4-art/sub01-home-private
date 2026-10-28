# Proposal: frozen latch clears itself (DEPLOYED 2026-10-28 ~13:45 UTC with the owner's OK: "deve funzionare in continuo")

Live 2026-10-28 04:30-04:34 UTC the frozen-stream guard latched twice in 4 minutes on a static YouTube ad / still page
("an ad's still in the way"). Only a human POST /resume clears it, and the lease renewer stops while it is up, so an
unattended night ends hands-off (he keeps talking and answering chat, but cannot touch the PC).

The patch (`frozen-auto-clear-20261028.patch`, tests included, 398 pass / 5 pre-existing failures): a "frozen" latch
(not "black") clears itself 120 s after it latched, through the existing probation, at most 3 times per rolling hour,
then it waits for a human. Kimi: first proposed making the detector alert-only; GO on this bounded compromise; diff
APPROVE. The deploy was refused by this session's permission classifier as weakening a safety guard, which is right:
it is the owner's guard rail (plan step 5). Apply with `git apply` only with the owner's explicit OK.
