# v22 installer: the cinematic include guard (2026-10-24, coordinator)

The pod dry run refused the real sources: `native_cinematic_pc.inc` mentions "PCFrame", but only reads it back
(`GetTextureParameterValue`) before recording a website observation. Two review rounds with Kimi (kimi-k3.1-pro).

## Round 1 (question: context, include excerpt, diff narrowing the refusal to SET statements; 217 s)

- **Make the guard fail closed across statements.** It currently misses:
  ```cpp
  const FName P(TEXT("PCFrame"));
  MonitorMaterial->SetTextureParameterValue(P, Feed);
  ```
  Neither `;`-separated chunk contains both strings, so installation proceeds and reports `reads PCFrame only`, despite the unrouted write. Prefer allowlisting the validated read-back form while retaining refusal for other `PCFrame` uses; at minimum, use:
  ```python
  return 'PCFrame' in inc and 'SetTextureParameterValue' in inc
  ```
  and add the multi-statement setter as a regression test.

The excerpt’s `GetTextureParameterValue` read-back itself remains correct under the stated v22/`ShowFrame` invariant; it needs no change.

## Round 2 (applied: allowlist the read-back form, any other "PCFrame" refuses; multi-statement setter test; 240 s)

APPROVE — this remains fail-closed, not SET-only: after removing the allowlisted getter pattern, any remaining `PCFrame` occurrence still refuses, including indirect setters. The read-back is non-mutating; under v22 routing it proceeds only when `PCFrame` reads back as `GraphicalFrame`, and safely skips on getter failure or a feed/other binding.

Result: the pod dry run plans cleanly (`present, reads PCFrame only`); 15/15 v22 tests pass.
