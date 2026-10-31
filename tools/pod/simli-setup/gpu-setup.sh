set -x
mkdir -p /root/voices && cd /root/voices
F=$(ls /workspace/gpu-bundle.tgz /gpu-bundle.tgz 2>/dev/null | head -1); tar xzf $F -C /root/voices && rm -f $F
F=$(ls /workspace/voices.tgz /voices.tgz 2>/dev/null | head -1); tar xzf $F -C /root/voices && rm -f $F
mv ccf39d76-sub-01.wav sub01-full.wav; mv 5b281c72-kimchi.wav kimchi-full.wav
apt-get install -y -qq ffmpeg >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq ffmpeg)
ffmpeg -hide_banner -loglevel error -y -i sub01-full.wav -t 9 sub01-ref.wav; ffmpeg -hide_banner -loglevel error -y -i kimchi-full.wav -t 9 kimchi-ref.wav
# token: written separately from the session scratchpad (never in git)
pip install -q omnivoice aiohttp soundfile
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
cd /root/voices && HF_HOME=/root/hf nohup python3 tts_gpu_server.py --voices-dir /root/voices --token-file /root/voices/token > /root/voices/server.log 2>&1 &
echo GPU-SETUP-STARTED
