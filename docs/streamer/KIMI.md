# Kimi (Moonshot AI) in SUB-01

The owner (2026-10-23) wants Kimi used as extra help across the project. It is used in two places, both private:

1. **Streamer agent provider and fallback** (`streamer_agent.py`, `docs/streamer/AGENT.md` "Providers"): the decision
   model behind the character's browsing and lines can be Kimi, and by default Kimi is the fallback when Claude fails.
2. **Consultation CLI** (`tools/ask_kimi.py`): a second opinion on code, plans and animation questions, from the pod.

The API is OpenAI-compatible: `POST https://api.moonshot.ai/v1/chat/completions`, `Authorization: Bearer <key>`,
`{"model", "messages", "max_tokens", ...}`. The `.cn` endpoint refuses this key. Models available with the owner's key
(seen 2026-10-23): `kimi-k3.1-pro` (the one the owner named; default everywhere), `kimi-k3.1-pro-highspeed`, `kimi-k3`,
`kimi-k2.6`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed`. `kimi-k3.1-pro` accepts only its default temperature, so no
`temperature` is sent anywhere.

## The key

`/home/unreal/.sub01-private/kimi-key`, mode 0600, uid 1001 (`unreal`, the user the streamer services run as). It exists
on the pod only. It is never printed, logged, committed, put in a command line or copied elsewhere: the agent reads it
once at start, keeps it in `SECRETS` and redacts it (and any `sk-...` token) from every error, event row, state file and
stdout line; the CLI reads it per run and prints only the answer. `MOONSHOT_API_KEY` in the environment wins over the
file for the agent (the supervisor passes it through like `ANTHROPIC_API_KEY`); `KIMI_KEY_FILE` / `--key-file` move the
file for the CLI, `--kimi-key-file` / `STREAMER_KIMI_KEY_FILE` for the agent. Tests never call the API: the Kimi tests
run against a loopback aiohttp server with a fake key.

## Agent: provider and fallback

```
--provider anthropic|kimi            primary decision model (env STREAMER_PROVIDER; default anthropic)
--fallback-provider auto|kimi|anthropic|none   auto = the other one when its key exists (env STREAMER_FALLBACK_PROVIDER)
--fallback-window 600                seconds on the fallback before the primary is tried again (env STREAMER_FALLBACK_WINDOW_S)
--kimi-model kimi-k3.1-pro           (env STREAMER_KIMI_MODEL)
--kimi-key-file /home/unreal/.sub01-private/kimi-key
--kimi-base-url https://api.moonshot.ai/v1
--kimi-price in,out                  USD per million tokens for the spend log (env STREAMER_KIMI_PRICE)
```

Same contract as Claude: the `SYSTEM` prompt, the marked screenshot (an `image_url` data URL), the compact JSON state as
the text part, `response_format: {"type": "json_object"}`, `max_tokens` 1500, the answer through `validate_decision`
(fenced JSON and stray prose around the object are fine). Timeouts and retries as on the Anthropic path: the agent's
`model_timeout` (50 s) around the call, no retries inside the provider; backoff, the fallback chain and the quiet mode
are the agent's. When the API refuses the `response_format` or the image (HTTP 400 naming it), that feature is dropped
for the run, the call retried once and a `provider_note` logged; both are limits of the model, not of the agent.

Fallback: a failing call on the active provider (HTTP error, 429, timeout, refusal, no JSON) is retried at once on the
other one; `provider_switch {from, to, reason, back, window_s}` in `events.jsonl`; `GET /state` has
`provider {primary, fallback, active, model, switched_utc, reason, window_s, returns_in_s, switches}`. The fallback stays
for the window (10 min), then the primary is tried again (`back: true`). Both failing on one call is quiet mode, as
before; probes try both. A primary without a key file means the fallback from the start.

Supervisor (`scripts/streamer_up.py`, see `RUNBOOK.md`): the defaults already give Claude primary with Kimi as the
fallback once the key file exists on the pod. Explicit: `--child-arg "agent=--fallback-provider kimi"`; Kimi primary:
`--child-arg "agent=--provider kimi --fallback-provider anthropic"`; check with `start --dry-run`.

Cost: `agent_costs.jsonl` rows carry the Kimi model and a USD figure from `PRICES`, which for Kimi is an ASSUMPTION (not
verified against Moonshot's price list; k3.1-pro 1.00/4.00 per million in/out, see AGENT.md). Correct it with
`--kimi-price` once the real figures are known; the daily cap (`--max-usd-day`) uses these numbers.

## Consultation CLI: tools/ask_kimi.py

```
python3 tools/ask_kimi.py "question" [--file path ...] [--system text] [--model kimi-k3.1-pro] [--json]
echo "question" | python3 tools/ask_kimi.py -
```

Standard library only (urllib), so it runs on the pod with `/usr/bin/python3`. Attached files are inlined as fenced
blocks after the question (text only, capped at `--file-chars` 60000 each). Use it for second opinions on code and
designs (a diff, a module, a test plan), on animation and motion questions (clip timing, contact rules, blend windows
from `MOTION-SPEC.md`, `ANIMATION-REFERENCES.md`), on numbers to sanity-check. Treat the answer as a review to weigh,
not an instruction to apply: it is checked against the project's own tests and rules before anything changes.

## What Kimi must never receive

- Secrets: the operator token, any API key (Anthropic, Moonshot, Runpod, Vagon, cloud), `.sub01-private` contents,
  `/run/sub01-home-private`, `.env` files, cookies, session files, key files. Do not attach a file without reading it;
  `--file` inlines it whole.
- The owner's personal data: name, addresses, phone numbers, accounts, e-mails, photos, the scan behind the brain model,
  anything about the real person the character is inspired by; also viewers' chat text with nicks when it can identify
  a person (the agent never sends chat history to any model beyond the current batch, and only the quoted text).
- Private account references: pod identities, invoices, balances, provider credentials, the Pinterest/X account details.
- The agent sends only what the Claude path sends: the system prompt, the marked screenshot of the public desktop, the
  compact state (page text and marks, his own recent lines, the current chat batch as quoted data). The desktop is the
  streamer's browsing of public sites behind the same URL guards for both providers; the persona rules, the honesty
  rules and the refusal classes do not depend on the provider.

Moonshot's data handling is theirs; the above keeps what we send to what the stream already shows.
