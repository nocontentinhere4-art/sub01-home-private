#!/bin/bash
# swap_game.sh BUILD_DIR TAG: put a built native game into the live project and restart the game with the SAME argv,
# environment and cwd as the running one (saved beforehand as unreal in <private>/relaunch-<TAG>/{argv,environ,cwd}),
# pinned to cores 0-7, log owner-stack/logs/native-<TAG>.log, then the CPU partition. Everything that can fail is staged
# BEFORE the game stops (new Binaries/Source copied beside the live ones); the swap itself is two renames. On any
# failure after the stop the previous Binaries/Source are renamed back and the game is relaunched. Run as root. The
# agent, director and voice keep running (the stream shows the placeholder while the game loads, ~2.5 min).
set -euo pipefail
BUILD=$1; TAG=$2
P=/home/unreal/.sub01-private; LIVE=$P/owner-stack-20261026/project/Sub01HomeLab; L=$P/relaunch-$TAG
TS=$(date -u +%Y%m%dT%H%M%S); BIN=$LIVE/Binaries/Linux; SRC=$LIVE/Source/Sub01HomeLab
OLD=$(cat $P/streamer/game.pid)
LOG=$P/owner-stack-20261026/logs/native-$TAG.log
[ -s $L/argv ] && [ -s $L/environ ] && [ -s $L/cwd ] || { echo "missing $L/{argv,environ,cwd}"; exit 1; }
[ -s $BUILD/Sub01HomeLab/Binaries/Linux/libUnrealEditor-Sub01HomeLab.so ] || { echo "no built library"; exit 1; }
[ "$(df --output=avail -k / | tail -1)" -gt 3000000 ] || { echo "disk < 3 GB"; exit 1; }
kill -0 $OLD || { echo "game $OLD not running"; exit 1; }

# stage (the running game keeps its files: nothing live is overwritten)
cp -a $BUILD/Sub01HomeLab/Binaries/Linux $BIN.new-$TS
cp -a $BUILD/Sub01HomeLab/Source/Sub01HomeLab $SRC.new-$TS
# the launcher runs as unreal and reads the environment from the file: nothing secret on a command line; it prints the
# game's pid (taskset execs the game, so the child pid is the game)
cat > $L/launch.py <<'PY'
import os, subprocess, sys
L, log = sys.argv[1], sys.argv[2]
env = dict(kv.split("=", 1) for kv in open(f"{L}/environ", "rb").read().decode().split("\0") if "=" in kv)
argv = [a for a in open(f"{L}/argv").read().split("\n") if a]
cwd = open(f"{L}/cwd").read().strip()
p = subprocess.Popen(["taskset", "-c", "0-7"] + argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                     stdout=open(log, "ab"), stderr=subprocess.STDOUT, start_new_session=True)
print(p.pid)
PY
chown unreal:unreal $L/launch.py; chmod 600 $L/launch.py
touch $LOG; chown unreal:unreal $LOG; chmod 600 $LOG

launch() {                                                  # -> pid of a live UnrealEditor-Cmd, or nothing
  local pid; pid=$(runuser -u unreal -- python3 $L/launch.py $L "$1") || return 1
  sleep 3
  kill -0 "$pid" 2>/dev/null && tr '\0' ' ' < /proc/$pid/cmdline | grep -q "UnrealEditor-Cmd .*Sub01HomeLab.uproject" || return 1
  echo "$pid"
}
write_pid() {
  for f in $P/streamer/game.pid $P/owner-stack-20261026/game.pid; do echo "$1" > $f.tmp; chown unreal:unreal $f.tmp; mv $f.tmp $f; done
}
rollback() {
  trap - ERR
  kill -0 $OLD 2>/dev/null && { echo "the old game $OLD still runs: nothing swapped"; rm -rf $BIN.new-$TS $SRC.new-$TS; return; }
  echo "FAILED after the stop: restoring the previous build and relaunching"
  if [ -n "${NEW:-}" ] && kill -0 "$NEW" 2>/dev/null; then kill -TERM "$NEW"; sleep 5; kill -KILL "$NEW" 2>/dev/null || true; fi   # never two games
  [ -d $BIN.old-$TS ] && { rm -rf $BIN.failed-$TS; [ -d $BIN ] && mv $BIN $BIN.failed-$TS; mv $BIN.old-$TS $BIN; }
  [ -d $SRC.old-$TS ] && { rm -rf $SRC.failed-$TS; [ -d $SRC ] && mv $SRC $SRC.failed-$TS; mv $SRC.old-$TS $SRC; }
  local pid; pid=$(launch $P/owner-stack-20261026/logs/native-rollback-$TS.log) && write_pid "$pid" && echo "rolled back, game pid $pid" || echo "ROLLBACK LAUNCH FAILED: relaunch by hand with $L/launch.py"
  echo "$(date -u '+%F %T') UTC | claude 20261028 | swap_game $TAG FAILED, rolled back" >> /tmp/sub01-share/pod-changes.log
}

echo "$(date -u '+%F %T') UTC | claude 20261028 | swap_game $TAG: stop game $OLD, swap in $BUILD (previous kept as *.old-$TS), relaunch" >> /tmp/sub01-share/pod-changes.log
trap rollback ERR                                           # from the stop until both pid files name the new game
kill -TERM $OLD || true
for i in $(seq 1 30); do kill -0 $OLD 2>/dev/null || break; sleep 1; done
if kill -0 $OLD 2>/dev/null; then kill -KILL $OLD; sleep 2; fi
mv $BIN $BIN.old-$TS && mv $BIN.new-$TS $BIN
mv $SRC $SRC.old-$TS && mv $SRC.new-$TS $SRC
NEW=$(launch $LOG)
write_pid $NEW
trap - ERR
echo "new game pid $NEW, log $LOG; previous build kept in $BIN.old-$TS and $SRC.old-$TS"
echo "rollback by hand: kill $NEW; mv $BIN $BIN.v26-$TS; mv $BIN.old-$TS $BIN; mv $SRC $SRC.v26-$TS; mv $SRC.old-$TS $SRC; runuser -u unreal -- python3 $L/launch.py $L <log>"
sleep 20                                                    # the game's threads exist before the partition pins them
runuser -u unreal -- /home/unreal/venv/bin/python /home/sub01-recovery-stage-20261026/runtime-source/scripts/streamer_cpu_partition.py \
  --once --game-pid-file $P/streamer/game.pid --game-cpus 0-7 --other-cpus 8-15,24-31 | tail -2 || echo "partition failed: rerun it"
