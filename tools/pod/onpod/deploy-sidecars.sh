#!/bin/bash
# Deploy window (coordinator): supervised sidecars (8634ff9) + agent-checks code (c59403b: agent, desktop runner, watchdog, live-check
# runner, shadow scorer). Restarts the supervisor with --hls-dir, then the watchdog. Backend files NOT deployed here. Refuses under MEASURING.
set -u
L=/home/unreal/.sub01-private/latest-source-20261023; PD=/home/unreal/.sub01-private/streamer; T=/home/unreal/.sub01-private/operator-token
D=/tmp/sub01-share/deploy/sidecars; U="runuser -u unreal --"; UP="$U /home/unreal/venv/bin/python $L/scripts/streamer_up.py"
COMMON="--source $L --streamer-dir $PD --token-file $T --display :103 --desktop-port 8838"
log(){ echo "$(date -u +%T) $*"; }
[ -e /tmp/sub01-share/MEASURING ] && { echo "REFUSED: measurement lease active"; exit 3; }
(cd $D && sha256sum -c SHA256SUMS) || { echo "REFUSED: checksum mismatch"; exit 4; }
for f in scripts/streamer_up.py scripts/streamer_monitor_feed.py scripts/streamer_hls_serve.py scripts/streamer_desktop.py scripts/streamer_watchdog.py \
         scripts/streamer_agent_checks.py scripts/streamer_shadow_report.py streamer_agent.py; do
  [ -e $L/$f ] && { [ -e $L/$f.bak-before-window ] || cp -p $L/$f $L/$f.bak-before-window; }
  install -o unreal -g unreal -m 644 $D/$(basename $f) $L/$f
done
pkill -u unreal -f scripts/streamer_monitor_feed.py; pkill -u unreal -f scripts/streamer_hls_serve.py
log "supervisor stop"; $UP stop $COMMON 2>&1 | tail -6; sleep 2
echo "$(date -u '+%F %T') UTC | coordinator | sidecars (8634ff9) + agent-checks code (c59403b) deployed, supervisor restarted with --hls-dir, watchdog restarted | *.bak-before-window + /tmp/sub01-share/cutover-c.sh" >> /tmp/sub01-share/pod-changes.log
log "supervisor start"
cd $PD && setsid nohup $UP start $COMMON --library-path /usr/local/cuda/lib64 --hls-dir $PD/hls \
  --child-env director=XAUTHORITY=/home/unreal/.sub01-private/native-xauthority \
  --child-arg "director=--game-pid-file $PD/game.pid" \
  --child-arg "director=--fps 60 --desktop-fps 60 --encoder h264_nvenc --hls-dir $PD/hls" \
  --child-arg "desktop=--data-dir $PD/desktop-vagon --pc-mode vagon --vagon-config $PD/vagon.json --streamer-dir $PD --chromium /opt/google/chrome/chrome" \
  --foreground > /tmp/sub01-share/supervisor-sidecars.out 2>&1 < /dev/null & disown
s=""
for i in $(seq 1 30); do sleep 5; s=$($UP status $COMMON 2>&1)
  echo "$s" | grep -q "^director  up" && echo "$s" | grep -q "^desktop   up" && echo "$s" | grep -q "^voice     up" && echo "$s" | grep -q "^hls *up" && break; done
echo "$s" | sed -E "s/([A-Za-z0-9_]*(TOKEN|token)[A-Za-z0-9_]*)[=:] *[^ ,]*/\1=***/g" | tail -14
log "watchdog restart (new code)"
for p in $(pgrep -f scripts/streamer_watchdog.py); do kill $p; done; sleep 2
setsid nohup $U /usr/bin/python3 $L/scripts/streamer_watchdog.py --streamer-dir $PD --token-file $T --agent-url http://127.0.0.1:8836 \
  --desktop-url http://127.0.0.1:8838 --desktop-data-dir $PD/desktop-vagon > /tmp/sub01-share/watchdog-window.out 2>&1 < /dev/null & disown
sleep 3; pgrep -af streamer_watchdog | cut -c1-160; ls -la $PD/STOP 2>&1
log done
