#!/bin/bash
# Coordinator only. Stage the reviewed installer and frozen manifests in deploy/v24 first.
# This builds only: no game, supervisor, director, agent or Vagon restart.
set -euo pipefail
P=/home/unreal/.sub01-private/cinematic-source-v3-final
M=$P/Sub01HomeLab/Source/Sub01HomeLab
B=$P/Sub01HomeLab/Binaries/Linux
D=/tmp/sub01-share/deploy/v24
SO=$B/libUnrealEditor-Sub01HomeLab.so
LOG=$P/build-v24.log
CHANGES=/tmp/sub01-share/pod-changes.log
STARTED=$(date -u '+%F %T')
START_EPOCH=$(date +%s)
STATE=preflight
BUILD_EXIT=not_started
finish() {
  rc=$?; trap - EXIT
  printf '%s UTC | coordinator | v24 build wrapper exit=%s state=%s BUILD_EXIT=%s started=%s | source-backup-before-v24, binaries-backup-before-v24\n' \
    "$(date -u '+%F %T')" "$rc" "$STATE" "$BUILD_EXIT" "$STARTED" >> "$CHANGES" || true
  exit "$rc"
}
trap finish EXIT
preflight() {
  [ ! -e /tmp/sub01-share/MEASURING ] || { echo 'REFUSED: measurement lease active'; exit 3; }
  [ -e /home/unreal/.sub01-private/streamer/STOP ] || { echo 'REFUSED: agent STOP missing'; exit 3; }
  # 3.5 GiB, checked on every filesystem used for backups or build output.
  for path in / "$P" "$M" "$B"; do
    free=$(df -PB1 "$path" | awk 'END {print $4}')
    [ "$free" -gt 3758096384 ] || { echo "REFUSED: <=3.5 GiB available at $path"; exit 4; }
  done
}
verify_sources() {
  python3 - "$1" "$D/source-v23-manifest.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
paths = list(root.rglob('*'))
if any(p.is_symlink() for p in paths): raise SystemExit('source symlinks require explicit review')
actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
if actual != json.loads(Path(sys.argv[2]).read_text()): raise SystemExit('source tree differs from frozen v23 manifest')
PY
}
[ "$(id -u)" = 0 ] || { echo 'REFUSED: coordinator must run as root'; exit 2; }
preflight
for file in source-v23-manifest.json expected-dry-run.json installer.sha256 artifact-marker.txt; do
  [ -s "$D/$file" ] || { echo "REFUSED: missing frozen $file"; exit 2; }
done
[ ! -e "$P/source-backup-before-v24" ] && [ ! -e "$P/binaries-backup-before-v24" ] || {
  echo 'REFUSED: existing v24 backup needs explicit verification/recovery'; exit 2;
}
(cd "$D" && sha256sum -c installer.sha256)
verify_sources "$M"
BEFORE_SHA=$(sha256sum "$SO" | awk '{print $1}')
MARKER=$(cat "$D/artifact-marker.txt")
[[ ${#MARKER} -ge 8 && "$MARKER" != *$'\n'* ]] || { echo 'REFUSED: invalid artifact marker'; exit 2; }
STATE=dry_run
runuser -u unreal -- python3 "$D/install_v24.py" --source "$M" --dry-run > "$D/dry-run.txt" 2>&1
python3 - "$D/expected-dry-run.json" "$D/dry-run.txt" <<'PY'
import json, sys
expected, actual = [json.load(open(p)) for p in sys.argv[1:]]
if actual != expected or actual.get('status') != 'planned': raise SystemExit('dry-run change set differs from frozen plan')
PY
preflight
verify_sources "$M"
STATE=backups
printf '%s UTC | coordinator | v24 source/binary backup and apply start | restore source-backup-before-v24 and binaries-backup-before-v24\n' \
  "$(date -u '+%F %T')" >> "$CHANGES"
cp -a "$M" "$P/source-backup-before-v24"
cp -a "$B" "$P/binaries-backup-before-v24"
verify_sources "$P/source-backup-before-v24"
diff -qr "$B" "$P/binaries-backup-before-v24"
STATE=apply
verify_sources "$M"
runuser -u unreal -- python3 "$D/install_v24.py" --source "$M" > "$D/apply.txt" 2>&1
python3 - "$M" "$D/source-v23-manifest.json" "$D/expected-dry-run.json" "$D/apply.txt" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
before, planned, applied = [json.load(open(p)) for p in sys.argv[2:]]
files = planned.get('files')
if not isinstance(files, dict) or not files or applied.get('status') != 'applied': raise SystemExit('invalid apply report')
if applied.get('files') != files: raise SystemExit('applied change set differs from frozen plan')
expected = dict(before)
expected.update({name: meta['after_sha256'] for name, meta in files.items()})
paths = list(root.rglob('*'))
if any(p.is_symlink() for p in paths): raise SystemExit('unexpected source symlink after apply')
actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
if actual != expected: raise SystemExit('applied source tree does not match frozen after hashes')
PY
preflight
STATE=build
printf '%s UTC | coordinator | native v24 compilation started | build-v24.log, source-backup-before-v24, binaries-backup-before-v24\n' \
  "$(date -u '+%F %T')" >> "$CHANGES"
cd "$P"
if runuser -u unreal -- /workspace/sub01-private-recovered-engine/Engine/Build/BatchFiles/Linux/Build.sh \
  Sub01HomeLabEditor Linux Development -Project="$P/Sub01HomeLab/Sub01HomeLab.uproject" \
  -NoHotReload -NoUBTMakefiles -MaxParallelActions=6 -NoUBA \
  "-AdditionalCompilerArguments=-ivfsoverlay $P/exact-header-overlay.json" > "$LOG" 2>&1; then
  BUILD_EXIT=0
else
  BUILD_EXIT=$?
fi
LOG_RC=0
printf 'BUILD_EXIT=%s\n' "$BUILD_EXIT" >> "$LOG" || LOG_RC=$?
[ "$BUILD_EXIT" -eq 0 ] || exit "$BUILD_EXIT"
[ "$LOG_RC" -eq 0 ] || { echo 'BUILD_EXIT=0 but required build logging failed'; exit 9; }
STATE=verify_artifact
AFTER_SHA=$(sha256sum "$SO" | awk '{print $1}')
[ "$AFTER_SHA" != "$BEFORE_SHA" ] && [ "$(stat -c %Y "$SO")" -ge "$START_EPOCH" ] && grep -aFq -- "$MARKER" "$SO" || {
  echo 'BUILD_EXIT=0 but artifact verification failed'; exit 8;
}
printf 'before_sha256=%s\nafter_sha256=%s\nartifact=%s\n' "$BEFORE_SHA" "$AFTER_SHA" "$SO" > "$D/artifact-receipt.txt"
STATE=complete
printf 'BUILD_EXIT=0 artifact_sha256=%s\n' "$AFTER_SHA"
exit 0
