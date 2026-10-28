# Guarded v24 build wrapper

`tools/pod/onpod/build-v24.sh` builds only; the offscreen game launch and director switch remain separate operations. This script has not been run on the native project yet.

Stage the reviewed installer and its Python imports in `/tmp/sub01-share/deploy/v24/`. Freeze `source-v23-manifest.json` as a mapping of every relative native-source filename to its SHA-256, `expected-dry-run.json` as the exact reviewed dry-run report, `installer.sha256` as the staged file checksums, and `artifact-marker.txt` as one literal log string compiled only by v24. Validate these against the final worker manifest before execution. No final native worker package is available yet.

The wrapper refuses missing STOP, MEASURING, source drift, installer drift, backup collisions or <=3.5 GiB available on the source/backup/build filesystems. Fresh source and binary backups are verified; existing v23 backups are preserved. Dry-run equality and before/after source hashes gate compilation. The real compiler status is returned; a zero compiler status with an unchanged, stale or marker-free binary returns 8. UTC stages and exit status go to the shared change log; a successful build writes an artifact hash receipt. A partial apply or failed build requires explicit coordinator recovery from backups before another attempt.

Validation uses a disposable project, real file copies and a fake engine executable. Cases cover a compiler exit 7, verified success, missing new binary, source mismatch after apply, active lease, exact disk threshold, source drift, backup collision and installer drift. There are 13 passing tests, including inherited Python optimization and a log path made unwritable after the compiler starts. Validation uses explicit exits, and a log failure preserves any compiler error; nominal compiler success with failed required logging returns 9. This verifies the wrapper, not Unreal compilation or rendering.

## Kimi review

The design was approved with fail-closed requirements for status, backups, source hashes, artifact verification and capacity. The question and answer are saved verbatim in `kimi/native-build-wrapper-design-20261024-*`. The first code review found removable Python assertions and a log-write error that could hide a compiler error. Both are fixed and have targeted regressions. The follow-up returned `COMMIT YES` and confirmed both blockers resolved with targeted regression coverage. Both review rounds are saved verbatim in `kimi/native-build-wrapper-review*-20261024-*`. Native execution still awaits final worker-package validation.
