#!/bin/bash
# Coordinator, visual tuning: frames.sh TAG [STATE]  -> /tmp/sub01-share/tune/TAG-{webcam,room,cam2}.jpg ; restores webcam_only.
set -u
TAG=$1; STATE=${2:-typing}
O=/tmp/sub01-share/tune; mkdir -p $O; chmod 777 $O
T=/home/unreal/.sub01-private/operator-token; HLS=/home/unreal/.sub01-private/streamer/hls
lay(){ curl -s -m5 -H "X-Admin-Token: $(cat $T)" -H "Content-Type: application/json" -d "{\"layout\":\"$1\"}" http://127.0.0.1:8837/director/layout > /dev/null; }
runuser -u unreal -- python3 /home/unreal/camera-check.py face $STATE 34 > /dev/null 2>&1 &
sleep 5
runuser -u unreal -- env XAUTHORITY=/home/unreal/.sub01-private/native-xauthority nice -n 19 ffmpeg -loglevel error -y -f x11grab -video_size 1920x1080 -i :99.0 -frames:v 1 -q:v 2 $O/$TAG-webcam.jpg
lay room; sleep 16
seg=$(ls -t $HLS/*.ts | sed -n 2p)
nice -n 19 ffmpeg -loglevel error -y -i "$seg" -vf "select=gte(n\,120)" -frames:v 1 -q:v 2 $O/$TAG-room.jpg
nice -n 19 ffmpeg -loglevel error -y -i $O/$TAG-room.jpg -vf "crop=1408:1080:0:0" -q:v 2 $O/$TAG-cam2.jpg
lay webcam_only; wait
chmod 644 $O/$TAG-*.jpg; ls -la $O/$TAG-*.jpg | awk '{print $5, $9}'
