#!/bin/bash
# Coordinator: relaunch the plain m3 launcher now (loads whatever is in Sub01HomeLab/Binaries/Linux), wait for NEW PERF lines.
set -u
R=/root/.sub01-windows-recovery; M3=$R/launch-streamer-game-20261023m3.py
PRIV=/home/unreal/.sub01-private; OUT=$PRIV/streamer-game-20261023m3; L=$PRIV/latest-source-20261023
log(){ echo "$(date -u +%T) $*"; }
[ -e /tmp/sub01-share/MEASURING ] && { echo "REFUSED: measurement lease active"; exit 3; }
OLD=$(cat $PRIV/streamer/game.pid); log "stop game pid $OLD"
kill -TERM -- -$OLD 2>/dev/null || kill -TERM $OLD
for i in $(seq 1 60); do kill -0 $OLD 2>/dev/null || break; sleep 1; done
kill -0 $OLD 2>/dev/null && { log "still alive, SIGKILL"; kill -KILL -- -$OLD 2>/dev/null; sleep 2; }
mkdir -p $OUT; mv $OUT/status.json $OUT/status-before-$(date -u +%H%M).json 2>/dev/null; ln -sfn $OUT/game.log /tmp/sub01-share/game.log
START=$(wc -l < $OUT/game.log 2>/dev/null || echo 0)
log "launch m3 (game.log line $START)"
setsid nohup python3 $M3 > $OUT/launcher-rerun.out 2>&1 < /dev/null & disown
NEW=""
for i in $(seq 1 30); do sleep 2; NEW=$(python3 -c "import json;print(json.load(open('$OUT/status.json')).get('pid',''))" 2>/dev/null); [ -n "$NEW" ] && break; done
log "game pid $NEW"; echo -n "$NEW" > $PRIV/streamer/game.pid.tmp && chown unreal:unreal $PRIV/streamer/game.pid.tmp && mv $PRIV/streamer/game.pid.tmp $PRIV/streamer/game.pid
pgrep -f streamer_cpu_partition.py >/dev/null || { cd /home/unreal && setsid nohup runuser -u unreal -- /usr/bin/python3 $L/scripts/streamer_cpu_partition.py \
  --game-pid-file $PRIV/streamer/game.pid --interval 10 >> $PRIV/streamer/logs/cpu-partition.log 2>&1 < /dev/null & disown; }
sleep 3; pgrep -af streamer_cpu_partition | cut -c1-160
echo "$(date -u '+%F %T') UTC | coordinator | relaunch plain m3 (pid $NEW) on the binaries in place | binaries-v2x-linux + this script" >> /tmp/sub01-share/pod-changes.log
log "waiting for new PERF lines"
for i in $(seq 1 60); do sleep 10; tail -n +$((START+1)) $OUT/game.log | grep -aq SUB01_STREAMER_VISUAL_PERF && break; done
tail -n +$((START+1)) $OUT/game.log | grep -aE "V2_V23|_V23|MONITOR_FEED started|CAM2_EXPOSURE|STREAMER_VISUAL_STARTED" | cut -c1-200 | head -8
tail -n +$((START+1)) $OUT/game.log | grep -a SUB01_STREAMER_VISUAL_PERF | tail -2 | cut -c1-200
log done
