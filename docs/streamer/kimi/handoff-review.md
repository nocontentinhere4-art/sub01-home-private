# Kimi review of HANDOFF.md (2026-10-23)

Applied to HANDOFF.md: goal clarification (private demonstration until authorised), open questions for the owner, the ordered plan with done-criteria, last-observed state with timestamps and verification commands, disk preflight, agent held during cut-overs, deploy scoped to the pod.

## 1. Main goal — required edits

Keep the paragraph, but append:

> Until separately authorised, “streaming version” means a **private pod-only recording/local-HLS demonstration**. Completion requires proven keyboard/mouse control of the same Vagon session seen by the monitor, agent and director; safe chat execution/refusal; both cameras composed simultaneously; K07 speech with lip/head motion; and a final soak demonstrating logs, recovery and the kill switch.

Resolve these ambiguities explicitly:

- Does **60+ fps** apply to UE rendering, each camera, encoded recording, or HLS? Define duration and measurement method. `t.MaxFPS 60` is only a cap, not proof of achieved fps.
- What supplies chat, which sites/games are approved, and what observable actions satisfy “browses and plays”?
- “Looks real” needs the visual-QA matrix plus explicit owner approval as its acceptance mechanism.

These details cannot be inferred from the handoff.

## 2. Replace the plan with this order

1. **Integrate worker outputs without runtime cut-over** — Done: tests pass, required Kimi artefacts/report sections exist, deliverables are committed/pushed, and the rollback baseline is recorded.
2. **Cut over native game k→l/v20** — Done: hands/posture/cam2 and the agreed fps metric pass; k remains restorable.
3. **Cut over the director locally** — Done: recording/local HLS demonstrate both cameras, desktop layouts, NVENC fallback and the agreed fps metric.
4. **Prove Vagon input, then wire one canonical source to monitor/director/agent; keep agent held** — Done: benign before/after frames prove keyboard and mouse input, with no ambiguous 8832/8838 split.
5. **Apply the Kimi-reviewed agent-provider decision and enable safety controls** — Done: allowed/refused actions, logging, fault recovery and STOP halt/resume pass before chat or unattended operation.
6. **Run the visual-polish loop** — Done: QA findings are closed, frame reviews saved, and the owner approves.
7. **Run the final 30-minute acceptance recording** — Done: it contains activity change, accepted/refused chat, recovered error, both cameras, voice/mouth, Vagon control and measured fps; highlights are delivered.
8. **Prepare subzerone.live only upon explicit request** — Done: the requested private embed/platform test passes; publication remains separately authorised.

## 3. Operational facts

Add canonical repo/worktree paths, current/last-known-good commit hashes, exact test/build/deploy/start/stop/rollback commands, health checks, log/recording paths, test-chat injection, worker status/log locations, and secret-free pod bootstrap—including who supplies the Jupyter token.

Treat the pid, listeners, `connected=true`, hold/restart state, worker list, tuning values and free disk as **last-observed state**, with timestamps and verification commands. Remove `21:2x` and `tonight`; require a disk-space preflight. Record exposed-key rotation status without recording secrets.

## 4. Working-rule conflicts

A single final “Kimi review each” is insufficient: consultation precedes design decisions, and diff/frame review precedes **every commit**. The pending cut-over consultation makes that plan provisional. Also, the current plan restarts the agent before guardrails, while unrestricted “deploy” and the 8832/8838 “or” are unsafe ambiguities; scope deployment to the pod and HLS to local/private access.