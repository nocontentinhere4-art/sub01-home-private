#!/bin/bash
# facegrab.sh TAG [WAIT_S]: wait (up to WAIT_S, default 600) until the game's camera is `face` for 4 s, then grab 3 frames
# from the live HLS (it lags the receipt by a segment or two) into /home/sub01-review-20261027/frames/TAG-face-N.jpg.
set -u
TAG=$1; WAIT=${2:-600}; H=/home/unreal/.sub01-private/owner-stack-20261026/hls; O=/home/sub01-review-20261027/frames
R=/home/unreal/.sub01-private/streamer-visual-receipt.json; mkdir -p $O
rm -f $O/$TAG-face-*.jpg                                   # no stale frames from an earlier run
cam() { python3 -c "import json;print(json.load(open('$R')).get('camera'))" 2>/dev/null; }
end=$(( $(date +%s) + WAIT )); since=0
while [ $(date +%s) -lt $end ]; do
  if [ "$(cam)" = face ]; then since=$((since+1)); else since=0; fi
  if [ $since -ge 4 ]; then
    for i in 1 2 3; do
      sleep 2; SEG=$(ls -t $H/*.ts | sed -n 2p)
      [ -n "$SEG" ] && [ $(( $(date +%s) - $(stat -c %Y "$SEG") )) -lt 10 ] || { echo "no fresh HLS segment"; exit 1; }
      ffmpeg -loglevel error -y -i "$SEG" -frames:v 1 -update 1 $O/$TAG-face-$i.jpg || { echo "ffmpeg failed"; exit 1; }
    done
    echo "grabbed after face for ${since}s, camera now $(cam)"; exit 0
  fi
  sleep 1
done
echo "no face shot within ${WAIT}s"; exit 1
