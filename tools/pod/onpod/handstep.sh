#!/bin/bash
# handstep.sh TAG [key=value ...]: apply live keys (tune_set.py), wait 8 s, print the receipt's hand measurements and
# write a brightened 2x2 crop of the hands from the live HLS (spectator framing) to frames/TAG-hands.jpg.
set -eu
TAG=$1; shift; D=$(dirname "$0"); O=/home/sub01-review-20261027/frames; H=/home/unreal/.sub01-private/owner-stack-20261026/hls
[ $# -gt 0 ] && python3 $D/tune_set.py "$@" && echo "$(date -u '+%F %T') UTC | claude 20261028 | tune $* (hands step $TAG)" >> /tmp/sub01-share/pod-changes.log
sleep 8
python3 - <<'PY'
import json
r=json.load(open('/home/unreal/.sub01-private/streamer-visual-receipt.json'))
k=('state','camera','v23_slide_left_cm','v23_slide_right_cm','v23_elbow_back_left_cm','v23_elbow_back_right_cm','v23_tips_above_keys_left_cm','v23_tips_above_keys_right_cm','v23_residual_left_cm','v23_residual_right_cm','hand_left','hand_right','elbow_left_deg','elbow_right_deg')
print({x:(round(r[x],2) if isinstance(r.get(x),float) else r.get(x)) for x in k})
PY
rm -f $O/$TAG-h*.png $O/$TAG-hands.jpg
SEG=$(ls -t $H/*.ts | sed -n 2p)
[ -n "$SEG" ] && [ $(( $(date +%s) - $(stat -c %Y "$SEG") )) -lt 10 ] || { echo "no fresh HLS segment"; exit 1; }
ffmpeg -loglevel error -y -i "$SEG" -vf fps=2 -frames:v 4 $O/$TAG-h%d.png
ffmpeg -loglevel error -y -i $O/$TAG-h%d.png -vf "crop=iw*0.22:ih*0.25:iw*0.58:ih*0.55,eq=brightness=0.12:gamma=1.6,scale=iw*2:-2,tile=2x2" -frames:v 1 -update 1 -q:v 3 $O/$TAG-hands.jpg
