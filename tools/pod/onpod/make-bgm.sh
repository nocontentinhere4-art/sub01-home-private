#!/bin/bash
# Original, royalty-free soft lo-fi pad (Am-F-C-G, one chord per 8 s, pink-noise vinyl hiss), 180 s, loudness -10 LUFS.
# The director mixes <streamer-dir>/music/bgm.mp3 at volume 0.08, ducked under the voice (live: about -34 dB mean).
# usage: make-bgm.sh /home/unreal/.sub01-private/streamer/music/bgm.mp3   (then chown unreal, chmod 600)
set -e; OUT="${1:?output path}"; DUR="${2:-180}"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "aevalsrc='0.09*pow(sin(PI*mod(t,8)/8),0.6)*(sin(2*PI*if(lt(mod(t,32),8),220,if(lt(mod(t,32),16),174.61,if(lt(mod(t,32),24),261.63,196)))*t)+sin(2*PI*if(lt(mod(t,32),8),261.63,if(lt(mod(t,32),16),220,if(lt(mod(t,32),24),329.63,246.94)))*t)+sin(2*PI*if(lt(mod(t,32),8),329.63,if(lt(mod(t,32),16),261.63,if(lt(mod(t,32),24),392,293.66)))*t)+0.5*sin(PI*if(lt(mod(t,32),8),220,if(lt(mod(t,32),16),174.61,if(lt(mod(t,32),24),261.63,196)))*t))':s=48000:d=$DUR" -f lavfi -i "anoisesrc=color=pink:amplitude=0.012:r=48000:d=$DUR" -filter_complex "[0:a]lowpass=f=1400,aecho=0.8:0.6:350:0.3[pad];[pad][1:a]amix=inputs=2:normalize=0,afade=t=in:d=3,pan=stereo|c0=c0|c1=c0,loudnorm=I=-10:TP=-1.5:LRA=7" -c:a libmp3lame -b:a 128k "$OUT"
