#!/bin/bash
# snap.sh TAG [SECONDS]: one frame every 2 s from the live HLS for SECONDS (default 16) -> a 4x2 contact sheet
# /home/sub01-review-20261027/frames/TAG-sheet.jpg (960 px wide per tile / 4), plus the camera and the receipt hand fields.
set -eu
TAG=$1; N=$(( ${2:-16} / 2 )); H=/home/unreal/.sub01-private/owner-stack-20261026/hls; O=/home/sub01-review-20261027/frames
mkdir -p $O
rm -f $O/$TAG-[0-9]*.jpg $O/$TAG-sheet.jpg                 # no stale frames from an earlier run
for i in $(seq 1 $N); do
  SEG=$(ls -t $H/*.ts | sed -n 2p)
  [ -n "$SEG" ] && [ $(( $(date +%s) - $(stat -c %Y "$SEG") )) -lt 10 ] || { echo "no fresh HLS segment"; exit 1; }
  ffmpeg -loglevel error -y -i "$SEG" -frames:v 1 -update 1 -vf scale=640:-2 $O/$TAG-$i.jpg
  sleep 2
done
ffmpeg -loglevel error -y -pattern_type glob -i "$O/$TAG-[0-9]*.jpg" -vf tile=4x2 -q:v 4 $O/$TAG-sheet.jpg
python3 - <<'PY'
import json
r=json.load(open('/home/unreal/.sub01-private/streamer-visual-receipt.json'))
print({k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items() if any(s in k for s in ('camera','slide','tips_above','desk_base','state'))})
PY
