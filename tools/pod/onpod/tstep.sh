#!/bin/bash
# Coordinator, visual tuning: tstep.sh TAG STATE [key=value ...] -> apply the keys, wait for the glides, capture frames, print measured v23 receipt fields.
set -u
TAG=$1; STATE=$2; shift 2
[ $# -gt 0 ] && runuser -u unreal -- python3 /home/unreal/tune.py "$@" > /dev/null && echo "$(date -u '+%F %T') UTC | coordinator | tune.py $* | previous values in /tmp/sub01-share/tune/tune-log.txt" >> /tmp/sub01-share/pod-changes.log
echo "$(date -u +%T) $TAG $*" >> /tmp/sub01-share/tune/tune-log.txt
sleep 6
bash /tmp/sub01-share/frames.sh $TAG $STATE 2>&1 | grep -v POCs | tail -3
python3 - <<'PY'
import json
r=json.load(open('/home/unreal/.sub01-private/streamer-visual-receipt.json'))
M=('incline_deg','head_ahead_cm','elbow_back_left_cm','elbow_back_right_cm','slide_left_cm','slide_right_cm','residual_left_cm','residual_right_cm','orient_err_left_deg','orient_err_right_deg','tips_above_keys_left_cm','tips_above_keys_right_cm','tips_min_above_keys_left_cm','tips_min_above_keys_right_cm','neck_axis_align','mouse','chair_scale_applied','chair_extra')
print({k:(round(r['v23_'+k],2) if isinstance(r.get('v23_'+k),float) else r.get('v23_'+k)) for k in M})
PY
