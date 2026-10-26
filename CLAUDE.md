# SUB-01 (private): working rules for every agent

## Highest priority: RunPod request discipline (owner, 2026-10-26)

Avoiding another RunPod API rate-limit block takes precedence over speed and parallel work.
Use one designated provider caller and an explicit bounded request plan. No automatic provider
polling, retries, fallback endpoints, or duplicate calls by other agents. On a rate-limit response,
record Retry-After and stop provider requests; do not test the block repeatedly. A timeout or
ambiguous mutation is not permission to retry. Prefer the already working direct pod shell for
application work, using bounded sessions and no blind retries. Keep a request ledger.
Do not install or restart any automatic pod-stop guard. Historical guard/deadline instructions
below are obsolete and must not be used. No top-ups or credential changes. Preserve original
resume20/21 state; missing state does not authorize a historical or empty replacement.


**Read `HANDOFF.md` first**: main goal, ordered plan, last-observed runtime state. Update it at every milestone.

- **Work together with Kimi** (owner's rule, 2026-10-23): every agent, the coordinator included, consults Kimi
  (`kimi-k3.1-pro`, via `tools/ask_kimi.py` on the pod) before design decisions and has its diff or frames reviewed by
  Kimi before a commit. Details and the CLI: `docs/streamer/KIMI.md`. Consultations are saved in `docs/streamer/kimi/`.
- Never publish, deploy, start a public stream, buy services or change credentials without the owner's explicit request.
- Secrets (API keys, tokens, the pod's Jupyter password) stay out of git, logs and chat; Kimi never receives them.
- Heavy work runs on the GPU pod; commits carry no model names except the attribution trailers.
