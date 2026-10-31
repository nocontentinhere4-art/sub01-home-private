#!/bin/bash
# SUB-01 Simli live stack (owner 10-30/31: no Unreal body, no GPU; SUB-01 is a Simli face over his Vagon PC, scheduled
# lives of about 10 h a day). Runs as root on the CPU pod; every service runs as unreal.
#
#   simli_live.sh keys     move the keys the owner put in /root/sub01-keys/ (anthropic-key, kimi-key, simli-key,
#                          optional elevenlabs-key) into the private dir, mode 600, never printed
#   simli_live.sh prep     dirs, operator token, vagon.json, switches (x-on, trading-on), announce.json, music, sfx
#   simli_live.sh up       backend shim 8830, stage display :99 + stage server 8842 + stage Chrome, audio, supervisor
#                          (desktop 8838, voice 8835, agent 8836, director 8837, monitor 8840, hls 8839), lease renewal,
#                          relay 8841 (loopback until `public`)
#   simli_live.sh public   the Cloudflare quick tunnel to the relay (owner's OK only); its URL goes to $S/tunnel-url
#   simli_live.sh console  a quick tunnel to the desktop runner's /operator page while the owner logs in to Vagon
#   simli_live.sh rest     off hours: agent, Vagon browser, Simli face and director stop; relay and tunnel stay
#   simli_live.sh schedule [START END]   (run under nohup) `up` between START and END UTC (default 18-4), `rest` outside
#   simli_live.sh down     everything above stopped (the keys and the private dir stay)
#   simli_live.sh guest on|off   Kimchi as guest: his Simli face beside SUB-01 (stage), his voice (voices pod) and his
#                          lines in the conversation (scripts/guest_driver.py, Claude Haiku in his persona)
#   simli_live.sh status   one line per piece
#
# Config: $P/simli-face-id (the SUB-01 face from app.simli.com), optional $P/simli-live.env (VOICE_ENGINE=kokoro|remote|
# elevenlabs, VOICE=am_puck / sub01 (remote) / an ElevenLabs voice id, REMOTE_URL=https://<voices pod>-8000.proxy.runpod.net,
# LEAD_S=0.4, PIP=480x270). remote also needs $P/voices-token (the voices pod's token).
set -u
P=/home/unreal/.sub01-private; S=$P/streamer; SRC=/home/unreal/sub01-src; ON=$SRC/tools/pod/onpod
PY=/home/unreal/venv/bin/python; VPY=/home/unreal/voice-rt-venv/bin/python; CHROME=/usr/bin/google-chrome
VOICE_ENGINE=kokoro; VOICE=am_puck; LEAD_S=0.4; PIP=480x270; REMOTE_URL=; ENCODER=libx264; FPS=30
[ -f $P/simli-live.env ] && . $P/simli-live.env

say() { printf '%s simli-live: %s\n' "$(date -u +%H:%M:%S)" "$*"; }
own() { chown unreal:unreal "$@"; }
spawn() {   # spawn NAME CMD...: a detached unreal process, its pid in $S/pids/x-NAME.pid, its log in $S/logs/NAME.log
  local name=$1; shift
  runuser -u unreal -- env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/home/unreal USER=unreal LANG=C.UTF-8 \
    XDG_RUNTIME_DIR=$P/xdg-runtime bash -c 'echo $$ > "$0"; exec setsid "$@"' $S/pids/x-$name.pid "$@" \
    >> $S/logs/$name.log 2>&1 < /dev/null &
  sleep 0.3
}
alive() { [ -f $S/pids/x-$1.pid ] && kill -0 "$(cat $S/pids/x-$1.pid)" 2>/dev/null; }
stop_one() { if alive $1; then kill -TERM -- -"$(cat $S/pids/x-$1.pid)" 2>/dev/null || kill "$(cat $S/pids/x-$1.pid)"; fi; rm -f $S/pids/x-$1.pid; }
wait_http() { for _ in $(seq 1 ${2:-30}); do curl -s -m2 -o /dev/null "$1" && return 0; sleep 1; done; return 1; }

keys() {
  mkdir -p $P && own $P && chmod 700 $P
  for k in anthropic-key kimi-key simli-key elevenlabs-key; do
    if [ -s /root/sub01-keys/$k ]; then
      install -m 600 -o unreal -g unreal /root/sub01-keys/$k $P/$k && shred -u /root/sub01-keys/$k 2>/dev/null || rm -f /root/sub01-keys/$k
      say "key $k installed"
    fi
    [ -s $P/$k ] && say "key $k present" || say "key $k MISSING"
  done
}

prep() {
  mkdir -p $S/logs $S/pids $S/hls $S/recordings $S/music $S/sfx $P/xdg-runtime $P/stage-chrome
  [ -s $P/operator-token ] || (umask 077; head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > $P/operator-token)
  [ -s $S/vagon.json ] || echo '{"schema":"sub01.streamer-vagon.v1","kind":"workstation","url":"https://app.vagon.io/workstation"}' > $S/vagon.json
  touch $S/x-on $S/trading-on
  cat > $S/announce.json <<'EOF'
{"text": "Halloween special tonight, chat. Kimchi joins the stream as his AI avatar, drop your costume ideas in chat.", "keywords": ["Kimchi", "Halloween"], "until": 1793520000}
EOF
  [ -s $S/music/bgm.mp3 ] || bash $ON/make-bgm.sh $S/music/bgm.mp3 >/dev/null 2>&1
  ls $S/sfx/*.wav >/dev/null 2>&1 || $PY $ON/make_sfx.py $S/sfx >/dev/null 2>&1
  cp -f $SRC/docs/streamer/simli/sub01-face-a3.jpg $P/stage-face.jpg 2>/dev/null
  chown -R unreal:unreal $P; chmod 700 $P $P/xdg-runtime; chmod 600 $P/operator-token
  say "prep done (face id: $([ -s $P/simli-face-id ] && echo set || echo MISSING))"
}

up() {
  [ -s $P/simli-face-id ] || { say "no $P/simli-face-id: put the SUB-01 Face ID there first"; return 1; }
  rm -f $S/STOP
  alive backend || spawn backend $PY $SRC/scripts/backend_shim.py --port 8830
  if ! alive xvfb-stage; then spawn xvfb-stage /usr/bin/Xvfb :99 -screen 0 960x540x24 -nolisten tcp -noreset; sleep 2; fi
  alive stage || spawn stage $PY $SRC/scripts/simli_stage.py --key-file $P/simli-key --face-id "$(cat $P/simli-face-id)" \
    --face-image $P/stage-face.jpg --guest-switch $S/guest-on --guest-face-file $P/kimchi-face-id --guest-voice kimchi \
    --guest-name KIMCHI
  wait_http http://127.0.0.1:8842/healthz 20 || say "stage server not answering"
  alive stage-chrome || spawn stage-chrome env DISPLAY=:99 $CHROME --user-data-dir=$P/stage-chrome --no-first-run \
    --no-default-browser-check --password-store=basic --no-sandbox --kiosk --window-position=0,0 --window-size=960,540 \
    --autoplay-policy=no-user-gesture-required --disable-features=Translate,MediaRouter --mute-audio \
    --app=http://127.0.0.1:8842/
  runuser -u unreal -- env HOME=/home/unreal STREAMER_DIR=$S bash $SRC/scripts/streamer_audio.sh up > $S/logs/audio-up.log 2>&1 || say "audio up failed (see logs/audio-up.log)"
  local voice_args="--engine $VOICE_ENGINE --voice $VOICE --fallback none --threads 4 --keep-hours 0 --simli-url http://127.0.0.1:8842/pcm --simli-lead-s $LEAD_S"
  if [ "$VOICE_ENGINE" = remote ]; then   # the voices pod (OmniVoice on a GPU), Kokoro am_puck for a sentence it misses
    voice_args="--engine remote --remote-url $REMOTE_URL --remote-token-file $P/voices-token --voice $VOICE --fallback kokoro --threads 4 --keep-hours 0 --simli-url http://127.0.0.1:8842/pcm --simli-lead-s $LEAD_S"
  fi
  local env_eleven=""
  if [ "$VOICE_ENGINE" = elevenlabs ]; then env_eleven="--child-env voice=ELEVENLABS_API_KEY=$(cat $P/elevenlabs-key)"; fi
  if ! runuser -u unreal -- env HOME=/home/unreal python3 $SRC/scripts/streamer_up.py status --streamer-dir $S --token-file $P/operator-token >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    runuser -u unreal -- env HOME=/home/unreal XDG_RUNTIME_DIR=$P/xdg-runtime python3 $SRC/scripts/streamer_up.py start \
      --source $SRC --streamer-dir $S --token-file $P/operator-token --display :103 --game-display :99.0 \
      --desktop-port 8838 --backend-port 8830 --hf-home /home/unreal/hf-cache --library-path "" --hls-dir $S/hls --xvfb-screen 1280x720x24 \
      --desktop-python $PY --voice-python $VPY --agent-python $PY --director-python $PY --monitor-python $PY --hls-python $PY \
      --child-arg "desktop=--data-dir $S/desktop-vagon --pc-mode vagon --vagon-kind workstation --chromium $CHROME --operator-console --size 1280x720" \
      --child-arg "voice=$voice_args" $env_eleven \
      --child-arg "director=--game-source x11 --window-prefix SUB01-STAGE --layout desktop --size 1280x720 --pip-size $PIP --fps $FPS --desktop-fps $FPS --encoder $ENCODER --recordings-dir $S/recordings --hls-dir $S/hls --min-free-gb 3 --keep-segments 12" \
      > $S/logs/up-start.log 2>&1 || say "supervisor start reported a problem (see logs/up-start.log)"
  fi
  alive lease || spawn lease python3 $ON/lease_renew.py
  alive guest || spawn guest $PY $SRC/scripts/guest_driver.py --streamer-dir $S --voice kimchi \
    --token-file $P/operator-token --key-file $P/anthropic-key
  alive relay || spawn relay $PY $ON/live_relay.py --hls $S/hls --stop $S/STOP --token-file $P/operator-token --port 8841
  status
}

public() {   # the Cloudflare quick tunnel to the relay: only on the owner's explicit OK (it makes the stream public)
  if ! alive tunnel; then
    spawn tunnel /usr/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8841
    for _ in $(seq 1 30); do
      url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' $S/logs/tunnel.log | tail -1); [ -n "$url" ] && break; sleep 1
    done
    [ -n "${url:-}" ] && echo "$url" > $S/tunnel-url && say "tunnel $url"
  fi
}

rest() {   # off hours: the paid parts stop (agent, Vagon browser, Simli face, director); relay + tunnel stay, so the
           # site keeps its address and shows the stream offline until the next `up`
  runuser -u unreal -- env HOME=/home/unreal python3 $SRC/scripts/streamer_up.py stop --streamer-dir $S --token-file $P/operator-token >/dev/null 2>&1
  for n in guest lease stage-chrome stage xvfb-stage; do stop_one $n; done
  say "resting (relay and tunnel kept)"
}

schedule() {   # schedule START END (UTC hours): `up` inside the window, `rest` outside; force with $P/live-force-on|off
  local start=${1:-18} end=${2:-4}
  say "schedule $start:00-$end:00 UTC"
  while :; do
    h=$((10#$(date -u +%H))); want=rest
    if [ $start -le $end ]; then [ $h -ge $start ] && [ $h -lt $end ] && want=up
    else { [ $h -ge $start ] || [ $h -lt $end ]; } && want=up; fi
    [ -e $P/live-force-on ] && want=up; [ -e $P/live-force-off ] && want=rest
    if [ $want = up ] && ! alive stage; then say "window open"; up > /dev/null 2>&1
    elif [ $want = rest ] && alive stage; then say "window closed"; rest; fi
    sleep 60
  done
}

down() {
  runuser -u unreal -- env HOME=/home/unreal python3 $SRC/scripts/streamer_up.py stop --streamer-dir $S --token-file $P/operator-token >/dev/null 2>&1
  for n in tunnel relay guest lease stage-chrome stage xvfb-stage backend; do stop_one $n; done
  say "down"
}

status() {
  for n in backend xvfb-stage stage stage-chrome lease guest relay tunnel; do printf '%-13s %s\n' $n "$(alive $n && echo up || echo DOWN)"; done
  curl -s -m3 http://127.0.0.1:8842/healthz; echo
  runuser -u unreal -- env HOME=/home/unreal python3 $SRC/scripts/streamer_up.py status --streamer-dir $S --token-file $P/operator-token 2>&1 | tail -12
  [ -s $S/tunnel-url ] && echo "tunnel: $(cat $S/tunnel-url)"
}

console() {   # console on|off: a second quick tunnel to the desktop runner, only while the owner logs in to Vagon
  if [ "${1:-on}" = off ]; then stop_one console; say "console tunnel closed"; return; fi
  alive console || spawn console /usr/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8838
  for _ in $(seq 1 30); do
    url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' $S/logs/console.log | tail -1); [ -n "$url" ] && break; sleep 1
  done
  say "Vagon login page: ${url:-?}/operator   (close it afterwards: simli_live.sh console off)"
}

guest() {   # guest on|off: Kimchi's face beside SUB-01 and his lines in the conversation (owner 10-31)
  if [ "${1:-on}" = off ]; then rm -f $S/guest-on; say "guest off"; else touch $S/guest-on; own $S/guest-on; say "guest on"; fi
}

case "${1:-status}" in
  keys) keys ;; prep) prep ;; up) up ;; public) public ;; rest) rest ;; schedule) schedule "${2:-18}" "${3:-4}" ;; down) down ;; status) status ;; console) console "${2:-on}" ;; guest) guest "${2:-on}" ;;
  *) echo "usage: $0 keys|prep|up|public|rest|schedule [START END]|down|status|console [on|off]|guest [on|off]"; exit 2 ;;
esac
