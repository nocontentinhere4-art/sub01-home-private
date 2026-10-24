#!/usr/bin/env bash
# SUB-01 streamer: application audio (browser, game) on the headless pod, which has no audio device.
#
# Chain (docs/streamer/RUNBOOK.md "Application audio"; decisions in docs/streamer/kimi/DECISIONS.md):
#   one per-user PulseAudio server (or pipewire-pulse, whichever the pod already has) with a null sink `sub01_apps`;
#   the desktop/kiosk Chromium plays into it; the director records `sub01_apps.monitor`. The voice stays on its own
#   PCM FIFO (`voice.pcm`) and is never played into the sink: it would be recorded twice.
#
#   streamer_audio.sh check         what the pod has (server, pactl, parec/pacat, ffmpeg pulse device, amix normalize)
#   streamer_audio.sh up            start a server if none answers, load the null sink once, print the env to export
#   streamer_audio.sh env           the env lines Chromium, pactl and ffmpeg need:  eval "$(streamer_audio.sh env)"
#   streamer_audio.sh test [SEC]    record SEC s (6) of the monitor while a 1 kHz tone plays into the sink; verdict
#   streamer_audio.sh ffmpeg-args   the director's input line and filter snippet (documentation: the director does
#                                   not use them yet, that is W6's change)
#   streamer_audio.sh down          unload the sink, stop a server this script started
#
# Idempotent: `up` twice starts nothing twice and loads one sink. Installs nothing: `check` says what is missing
# (apt may be unavailable on the pod; the root disk has about 3.7 GB free). Runs as uid 1001 `unreal`, never root.
#
# Env: STREAMER_DIR        default /home/unreal/.sub01-private/streamer   (pulse.pa, logs/, pids/, audio/ live here)
#      SUB01_AUDIO_SINK    default sub01_apps
#      SUB01_AUDIO_RUNTIME default /run/user/<uid> when it exists and is writable, else $STREAMER_DIR/run (mode 0700)
#
# Must be verified on the pod (no pod access from here): the server binary exists; ffmpeg lists `pulse` under
# `-devices` (else the parec FIFO path below); `ffmpeg -h filter=amix` knows `normalize`; the Playwright Chromium
# finds `libpulse.so.0` (`ldconfig -p | grep libpulse`, or the LD_LIBRARY_PATH of DESKTOP.md); Chromium is launched
# WITHOUT `--mute-audio` (today `chromium_args` in scripts/streamer_desktop.py adds it: W1 adds an `--audio` flag) and
# WITH the env printed by `env`; `pactl list short sink-inputs` shows Chromium while a page plays sound (autoplay may
# need the Vagon connect click); the Vagon Cloud Computer actually sends audio to the web client (unknown).
set -euo pipefail

STREAMER_DIR=${STREAMER_DIR:-/home/unreal/.sub01-private/streamer}
SINK=${SUB01_AUDIO_SINK:-sub01_apps}
PA_FILE="$STREAMER_DIR/audio/pulse.pa"
PID_FILE="$STREAMER_DIR/pids/pulse.pid"
LOG_FILE="$STREAMER_DIR/logs/pulse.log"

die() { printf 'streamer audio: %s\n' "$*" >&2; exit 1; }
note() { printf 'streamer audio: %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(id -u)" -ne 0 ] || die "run as the streamer user (uid 1001), not root"

runtime_dir() {
  if [ -n "${SUB01_AUDIO_RUNTIME:-}" ]; then printf '%s' "$SUB01_AUDIO_RUNTIME"; return; fi
  local d="/run/user/$(id -u)"
  if [ -d "$d" ] && [ -w "$d" ]; then printf '%s' "$d"; else printf '%s' "$STREAMER_DIR/run"; fi
}

RT=$(runtime_dir)
export XDG_RUNTIME_DIR="$RT"
export PULSE_SERVER="unix:$RT/pulse/native"
export HOME="${HOME:-/home/unreal}"

server_up() { pactl info >/dev/null 2>&1; }
sink_loaded() { pactl list short sinks 2>/dev/null | awk '{print $2}' | grep -qx "$SINK"; }
ffmpeg_has_pulse() { have ffmpeg && ffmpeg -hide_banner -devices 2>/dev/null | grep -Eq '^\s*D?E?\s+pulse\s'; }
ffmpeg_pulse_in() { have ffmpeg && ffmpeg -hide_banner -devices 2>/dev/null | grep -Eq '^\s*DE?\s+pulse\s'; }
ffmpeg_pulse_out() { have ffmpeg && ffmpeg -hide_banner -devices 2>/dev/null | grep -Eq '^\s*D?E\s+pulse\s'; }

server_kind() {
  if have pulseaudio; then printf 'pulseaudio'
  elif have pipewire && have pipewire-pulse; then printf 'pipewire-pulse'
  else printf 'none'; fi
}

cmd_env() {
  printf 'export XDG_RUNTIME_DIR=%q\n' "$RT"
  printf 'export PULSE_SERVER=%q\n' "$PULSE_SERVER"
}

cmd_check() {
  local ok=1 kind; kind=$(server_kind)
  note "runtime dir: $RT  (server socket $RT/pulse/native)"
  note "server binary: $kind"
  for t in pactl parec pacat; do
    if have "$t"; then note "$t: $(command -v "$t")"; else note "$t: missing"; fi
  done
  if have ffmpeg; then
    note "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1)"
    if ffmpeg_pulse_in; then note "ffmpeg pulse input device: yes (-f pulse -i $SINK.monitor)"
    else note "ffmpeg pulse input device: NO (fallback: parec -> FIFO -> ffmpeg -f s16le)"; fi
    if ffmpeg -hide_banner -h filter=amix 2>/dev/null | grep -q normalize; then note "amix normalize option: yes"
    else note "amix normalize option: NO (old ffmpeg: amix attenuates each input by 1/n; raise the gains)"; fi
    if ffmpeg -hide_banner -h filter=sidechaincompress 2>/dev/null | grep -q threshold; then note "sidechaincompress: yes"
    else note "sidechaincompress: NO (ducking needs it; mix without ducking meanwhile)"; fi
  else
    note "ffmpeg: missing"; ok=0
  fi
  if have ldconfig && ldconfig -p 2>/dev/null | grep -q 'libpulse\.so\.0'; then note "libpulse.so.0 (Chromium needs it): in ldconfig"
  else note "libpulse.so.0: not in ldconfig (check the LD_LIBRARY_PATH the desktop runner uses; Chromium is silent without it)"; fi
  if server_up; then note "a server answers now: $(pactl info 2>/dev/null | sed -n 's/^Server Name: //p')"
    if sink_loaded; then note "sink $SINK: loaded"; else note "sink $SINK: not loaded (run: up)"; fi
  else note "no server answers at $PULSE_SERVER (run: up)"; fi
  [ "$kind" != none ] || ok=0
  have pactl || ok=0
  if ! ffmpeg_pulse_in && ! have parec; then ok=0; fi
  if [ "$ok" = 1 ]; then
    note "verdict: the chain is possible on this host; next: up, then test"
  else
    note "verdict: NOT possible without new software (server: $kind; pactl: $(have pactl && echo yes || echo no); capture: $( (ffmpeg_pulse_in || have parec) && echo yes || echo no))."
    note "nothing is installed by this script. Options for the owner: apt (if available) pulseaudio pulseaudio-utils;"
    note "or a user-space install under /home/unreal (conda-forge 'pulseaudio', about 50 MB); or declare 'no application audio'."
    return 1
  fi
}

write_pa() {
  mkdir -p "$(dirname "$PA_FILE")" "$STREAMER_DIR/logs" "$STREAMER_DIR/pids"
  umask 077
  cat >"$PA_FILE" <<EOF
.fail
# SUB-01 application audio. Unix socket only: no TCP/network protocol module, no hardware detection.
load-module module-native-protocol-unix
load-module module-null-sink sink_name=$SINK rate=48000 channels=2 format=s16le channel_map=front-left,front-right sink_properties=device.description=SUB01_Apps
set-default-sink $SINK
EOF
  chmod 0600 "$PA_FILE"
}

start_server() {
  local kind; kind=$(server_kind)
  [ "$kind" != none ] || die "no pulseaudio or pipewire-pulse binary; see: check"
  mkdir -p "$RT"; chmod 0700 "$RT"
  case "$kind" in
    pulseaudio)
      write_pa
      # -n: no default config (no dbus, no hardware modules); own file; stays up without clients.
      setsid nohup pulseaudio -n -F "$PA_FILE" --daemonize=no --exit-idle-time=-1 --log-target=stderr \
        >>"$LOG_FILE" 2>&1 < /dev/null &
      echo $! >"$PID_FILE" ;;
    pipewire-pulse)
      setsid nohup pipewire >>"$LOG_FILE" 2>&1 < /dev/null &
      echo $! >"$PID_FILE"
      sleep 1
      setsid nohup pipewire-pulse >>"$LOG_FILE" 2>&1 < /dev/null &
      echo $! >>"$PID_FILE" ;;
  esac
  local i
  for i in $(seq 1 20); do server_up && return 0; sleep 0.25; done
  die "server did not answer within 5 s; see $LOG_FILE"
}

ensure_sink() {
  if sink_loaded; then note "sink $SINK already loaded"
  else
    pactl load-module module-null-sink "sink_name=$SINK" rate=48000 channels=2 format=s16le \
      channel_map=front-left,front-right "sink_properties=device.description=SUB01_Apps" >/dev/null
    note "sink $SINK loaded"
  fi
  pactl set-default-sink "$SINK"
  pactl list short sources | awk '{print $2}' | grep -qx "$SINK.monitor" || die "monitor source $SINK.monitor not found"
}

cmd_up() {
  have pactl || die "pactl missing; see: check"
  if server_up; then note "server already up ($(pactl info 2>/dev/null | sed -n 's/^Server Name: //p'))"
  else start_server; note "server started ($(server_kind)), log $LOG_FILE"; fi
  ensure_sink
  note "default sink: $(pactl info | sed -n 's/^Default Sink: //p'); capture from: $SINK.monitor"
  note "export this for Chromium (desktop runner), pactl and ffmpeg (director):"
  cmd_env
}

cmd_test() {
  local sec=${1:-6} out raw rec_pid max
  server_up || die "no server; run: up"
  sink_loaded || die "sink $SINK not loaded; run: up"
  have ffmpeg || die "ffmpeg missing"
  mkdir -p "$STREAMER_DIR/audio"
  out="$STREAMER_DIR/audio/test-$(date -u +%Y%m%dT%H%M%SZ).wav"
  if ffmpeg_pulse_in; then
    ffmpeg -y -hide_banner -loglevel error -f pulse -i "$SINK.monitor" -t "$sec" -c:a pcm_s16le "$out" &
    rec_pid=$!
  elif have parec; then
    raw="$out.s16le"
    ( parec -d "$SINK.monitor" --format=s16le --rate=48000 --channels=2 --raw \
        | head -c $((48000 * 4 * sec)) >"$raw" ) &
    rec_pid=$!
  else
    die "no capture path (ffmpeg pulse input or parec)"
  fi
  sleep 1
  if have pacat; then
    ffmpeg -v error -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=3" -f s16le -ac 2 -ar 48000 - \
      | pacat --raw --device="$SINK" --format=s16le --rate=48000 --channels=2
  elif ffmpeg_pulse_out; then
    ffmpeg -v error -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=3" -f pulse -device "$SINK" sub01-audio-test
  else
    kill "$rec_pid" 2>/dev/null || true
    die "no player (pacat or ffmpeg pulse output) to put a tone into the sink"
  fi
  wait "$rec_pid" || true
  if [ -n "${raw:-}" ]; then
    ffmpeg -y -hide_banner -loglevel error -f s16le -ar 48000 -ac 2 -i "$raw" -c:a pcm_s16le "$out"; rm -f "$raw"
  fi
  [ -s "$out" ] || die "nothing recorded ($out)"
  max=$(ffmpeg -hide_banner -i "$out" -af volumedetect -f null - 2>&1 | sed -n 's/.*max_volume: \([-0-9.]*\) dB.*/\1/p')
  note "recorded $out, max_volume ${max:-?} dB"
  if [ -n "$max" ] && awk -v m="$max" 'BEGIN{exit !(m > -40)}'; then
    note "PASS: the monitor carries what is played into the sink."
    note "next: play a sound in the desktop Chromium and check 'pactl list short sink-inputs' lists it; then the Vagon game."
  else
    die "FAIL: the recording is silent; check sink-inputs and the server log $LOG_FILE"
  fi
}

cmd_ffmpeg_args() {
  cat <<EOF
# Director (scripts/streamer_director.py, W6): inputs today are 0 game x11grab, 1 desktop x11grab, 2 voice FIFO.
# Add the application monitor as input 3 (ffmpeg needs the env from: streamer_audio.sh env):
  -thread_queue_size 1024 -f pulse -i $SINK.monitor
# Without a pulse-enabled ffmpeg, W6 runs 'parec -d $SINK.monitor --format=s16le --rate=48000 --channels=2 --raw'
# into a FIFO <streamer-dir>/apps.pcm and adds it like the voice FIFO:
  -thread_queue_size 4096 -f s16le -ar 48000 -ac 2 -i $STREAMER_DIR/apps.pcm
# Filter (replaces ';[2:a]apad[aout]'): voice [2:a] is the duck key, apps [3:a] about -9 dB before ducking;
# sidechaincompress threshold 0.03 ratio 6 attack 15 ms release 300 ms; limiter ~ -1 dBFS; nothing auto-levelled.
  [3:a]aresample=48000:async=1:first_pts=0,volume=0.35[app];
  [2:a]apad,aresample=48000:async=1:first_pts=0,asplit=2[voice][duckkey];
  [app][duckkey]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=300[ducked];
  [ducked][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.891[aout]
# Then as today: -map "[vout]" -map "[aout]" -c:a aac -b:a 160k -ar 48000 -ac 2   (96k today; 160-192k with game audio)
# Mute on privacy/kill without restarting ffmpeg: a zmq/sendcmd 'volume' command on [app] (W6), same flag as the safety view.
# Measure the finished segment, not the sources:
  ffmpeg -hide_banner -i <segment>.mp4 -map 0:a -af ebur128=peak=true -f null -
EOF
}

cmd_down() {
  if server_up; then
    pactl list short modules 2>/dev/null | awk -v s="sink_name=$SINK" 'index($0, s) {print $1}' \
      | while read -r m; do pactl unload-module "$m" && note "unloaded module $m"; done
  fi
  if [ -f "$PID_FILE" ]; then
    while read -r p; do
      [ -n "$p" ] && kill "$p" 2>/dev/null && note "stopped server pid $p" || true
    done <"$PID_FILE"
    rm -f "$PID_FILE"
  else
    note "no server started by this script (a pre-existing server is left running)"
  fi
}

case "${1:-}" in
  check) cmd_check ;;
  up) cmd_up ;;
  env) cmd_env ;;
  test) cmd_test "${2:-6}" ;;
  ffmpeg-args) cmd_ffmpeg_args ;;
  down) cmd_down ;;
  *) awk 'NR > 1 && !/^#/ {exit} NR > 1 {print}' "$0" >&2; exit 2 ;;
esac
