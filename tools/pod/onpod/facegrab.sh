#!/bin/bash
# facegrab.sh TAG [WAIT_S] [N]: wait (up to WAIT_S, default 600) until the game's camera has been `face` for 4 s, then grab
# frames from the live HLS while it stays `face`, LAG s later (the HLS trails the receipt by a few seconds: segment
# length + encoding), into /home/sub01-review-20261027/frames/TAG-face-N.jpg; up to N (default 3) frames.
# A face stretch shorter than the lag yields nothing and the wait goes on.
set -u
TAG=$1; WAIT=${2:-600}; N=${3:-3}; LAG=6
H=/home/unreal/.sub01-private/owner-stack-20261026/hls; O=/home/sub01-review-20261027/frames
R=/home/unreal/.sub01-private/streamer-visual-receipt.json; mkdir -p $O
rm -f $O/$TAG-face-*.jpg                                   # no stale frames from an earlier run
cam() { python3 -c "import json;print(json.load(open('$R')).get('camera'))" 2>/dev/null; }
end=$(( $(date +%s) + WAIT )); since=0; got=0; last=""
while [ $(date +%s) -lt $end ] && [ $got -lt $N ]; do
  if [ "$(cam)" = face ]; then since=$((since+1)); else since=0; fi
  if [ $since -ge $((1 + LAG)) ]; then                      # face for LAG+1 s: the HLS now shows it past the 1 s blend
    SEG=$(ls -t $H/*.ts | sed -n 2p)
    [ -n "$SEG" ] && [ $(( $(date +%s) - $(stat -c %Y "$SEG") )) -lt 10 ] || { echo "no fresh HLS segment"; exit 1; }
    [ "$SEG" = "$last" ] && { sleep 1; continue; }           # one frame per segment: wait for a later one
    last=$SEG; got=$((got+1))
    ffmpeg -loglevel error -y -i "$SEG" -frames:v 1 -update 1 $O/$TAG-face-$got.jpg || { echo "ffmpeg failed"; exit 1; }
  fi
  sleep 1
done
echo "grabbed $got face frame(s)"; [ $got -gt 0 ]
