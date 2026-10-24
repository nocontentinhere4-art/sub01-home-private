#!/bin/bash
# v22 build (coordinator). Run as root: bash /tmp/sub01-share/deploy/v22/build-v22.sh ; refuses during a measurement lease.
set -u
P=/home/unreal/.sub01-private/cinematic-source-v3-final
M=$P/Sub01HomeLab/Source/Sub01HomeLab
D=/tmp/sub01-share/deploy/v22
LOG=$P/build-v22.log
[ -e /tmp/sub01-share/MEASURING ] && { echo "REFUSED: measurement lease active"; exit 3; }
FREE=$(df --output=avail -k / | tail -1); [ "$FREE" -gt 3500000 ] || { echo "REFUSED: root disk below 3.5 GB"; exit 4; }
grep -rq "SUB01_STREAMER_VISUAL_V2_V22" $M && { echo "v22 already applied"; } || {
  [ -e $P/source-backup-before-v22 ] || cp -a $M $P/source-backup-before-v22
  [ -e $P/binaries-v21-linux ] || cp -a $P/Sub01HomeLab/Binaries/Linux $P/binaries-v21-linux
  chown -R unreal:unreal $P/source-backup-before-v22 $P/binaries-v21-linux
  runuser -u unreal -- python3 $D/install_v22.py --source $M --dry-run > $D/dry-run.txt 2>&1 || { echo "DRY-RUN FAILED"; tail -20 $D/dry-run.txt; exit 5; }
  runuser -u unreal -- python3 $D/install_v22.py --source $M > $D/apply.txt 2>&1 || { echo "APPLY FAILED"; tail -20 $D/apply.txt; exit 6; }
}
echo "$(date -u '+%F %T') UTC | coordinator | build v22 started (backup: source-backup-before-v22, binaries-v21-linux) | restore both dirs" >> /tmp/sub01-share/pod-changes.log
cd $P && runuser -u unreal -- /workspace/sub01-private-recovered-engine/Engine/Build/BatchFiles/Linux/Build.sh Sub01HomeLabEditor Linux Development \
  -Project=$P/Sub01HomeLab/Sub01HomeLab.uproject -NoHotReload -NoUBTMakefiles -MaxParallelActions=6 -NoUBA \
  "-AdditionalCompilerArguments=-ivfsoverlay $P/exact-header-overlay.json" > $LOG 2>&1
RC=$?; echo "BUILD_EXIT=$RC" >> $LOG
echo "$(date -u '+%F %T') UTC | coordinator | build v22 finished BUILD_EXIT=$RC | binaries-v21-linux" >> /tmp/sub01-share/pod-changes.log
echo "BUILD_EXIT=$RC"
