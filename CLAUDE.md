# SUB-01 (private): working rules for every agent

- **Work together with Kimi** (owner's rule, 2026-10-23): every agent, the coordinator included, consults Kimi
  (`kimi-k3.1-pro`, via `tools/ask_kimi.py` on the pod) before design decisions and has its diff or frames reviewed by
  Kimi before a commit. Details and the CLI: `docs/streamer/KIMI.md`. Consultations are saved in `docs/streamer/kimi/`.
- Never publish, deploy, start a public stream, buy services or change credentials without the owner's explicit request.
- Secrets (API keys, tokens, the pod's Jupyter password) stay out of git, logs and chat; Kimi never receives them.
- Heavy work runs on the GPU pod; commits carry no model names except the attribution trailers.
