#!/bin/bash
# Coordinator: typing -> reading -> typing motion clip of the webcam (game window :99), 18 s at 30 fps, and a contact sheet.
set -u
O=/tmp/sub01-share/tune; P=/home/unreal/.sub01-private
X="runuser -u unreal -- env XAUTHORITY=$P/native-xauthority"
( runuser -u unreal -- python3 /home/unreal/camera-check.py face typing 6 >/dev/null 2>&1
  runuser -u unreal -- python3 /home/unreal/camera-check.py face reading 6 >/dev/null 2>&1
  runuser -u unreal -- python3 /home/unreal/camera-check.py face typing 7 >/dev/null 2>&1 ) &
sleep 1
$X nice -n 19 ffmpeg -loglevel error -y -f x11grab -framerate 30 -video_size 1920x1080 -i :99.0 -t 18 -vf scale=960:540 -c:v libx264 -preset veryfast -crf 23 $O/motion.mp4
wait
nice -n 19 ffmpeg -loglevel error -y -i $O/motion.mp4 -vf "fps=1,scale=480:270,tile=6x3" -frames:v 1 -q:v 3 $O/motion-sheet.jpg
chmod 644 $O/motion*; ls -la $O/motion* | awk '{print $5,$9}'
