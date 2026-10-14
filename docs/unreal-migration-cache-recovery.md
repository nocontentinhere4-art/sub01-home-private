The 14 October migration exposed a real installed-engine discovery failure. The official `ReplicationActionEntry.h` and `ConcertSyncSettings.h` matched the source archive CRC, but the transferred project `Makefile.bin` retained an incomplete reflected-header list from partial extraction. Quarantining the actual project makefile, source metadata cache and UHT manifest fixed discovery: ConcertSyncCore went from eight reflected headers without the defining header to 35 with it. UHT then completed in 21.08 seconds. No official header or plugin was modified.

The frozen native source on that target was `cdc9a2c`. At the fixed 01:37:44 UTC stop, the last observed build output had compiled four of nine actions. Final compilation success and a new rendered frame were not verified. This recovery is not animation, physical seating, privacy or device acceptance.

`tools/quarantine_unreal_project_cache.py` preserves that fix as a narrowly scoped operator tool. It defaults to dry-run and touches only these project files on explicit application:

- `Intermediate/Build/Linux/x64/Sub01HomeLabEditor/Development/Makefile.bin`
- `Intermediate/Build/SourceFileCache.bin`
- `Intermediate/Build/Linux/Sub01HomeLabEditor/Sub01HomeLabEditor.uhtmanifest`

Each existing file is preserved under a unique sibling `.quarantined-<UTC>-<UUID>` name before its original name is removed. Other targets, Engine, Content, Config, Binaries and the project descriptor are untouched. Symlinked cache files or parent directories are refused. Missing files are reported and left alone; this does not clear all Intermediate output or regenerate the project.

Run this only after migration extraction has finished, with no project build running. Do not quarantine caches during an active compiler or extractor job. A complete source engine is a prerequisite: removing caches while extraction remains partial can immediately recreate the same defective discovery.

Dry-run requires only the actual project root:

```sh
python3 tools/quarantine_unreal_project_cache.py --project /workspace/sub01-home-private/project/Sub01HomeLab
```

Application requires an explicit complete-engine extraction attestation and the corresponding engine root:

```sh
python3 tools/quarantine_unreal_project_cache.py --project /workspace/sub01-home-private/project/Sub01HomeLab --engine-root /workspace/sub01-unreal/UE --readiness /private/path/verified-engine-readiness.json --apply
```

The readiness JSON contract is `schema: sub01.unreal-engine-readiness.v1`, `engine_version: 5.8.3`, canonical absolute `engine_root`, the actual lowercase `archive_sha256`, and boolean `archive_sha256_verified`, `all_selected_members_crc_verified`, `original_critical_mtimes_restored`, all exactly true. Positive integer `expected_selected_members` and `crc_verified_selected_members` must match. These fields must come from the trusted migration verifier's completed SHA/CRC/mtime evidence. A compiler-only prefix marker, a file-presence check or a hand-written assertion is insufficient. The helper validates the attestation's scope and completion; it does **not** rehash or authenticate the engine itself. The previous server's marker files are not silently interpreted as this new schema; any adapter must use their actual validated contents.

After recovery, use the official `-NoUBTMakefiles` build flag for the first discovery pass and inspect the new UHT manifest and compiler exit. A fresh header list alone is not a successful build. The helper never starts a pod, Unreal, a compiler or a renderer and grants no additional compute authorization.
