set -x
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends espeak-ng
su - unreal -c 'python3 -m venv --system-site-packages /home/unreal/voice-rt-venv && /home/unreal/voice-rt-venv/bin/pip install -q kokoro soundfile aiohttp numpy scipy && mkdir -p /home/unreal/hf-cache'
su - unreal -c 'cd /tmp && HF_HOME=/home/unreal/hf-cache /home/unreal/voice-rt-venv/bin/python -c "
from kokoro import KPipeline; import time; t=time.time(); p=KPipeline(lang_code=\"a\", repo_id=\"hexgrad/Kokoro-82M\", device=\"cpu\"); v=p.load_single_voice(\"am_puck\")
t1=time.time(); out=[r.audio for r in p(\"Yo chat, SUB-01 is back and the Halloween special starts right now.\", voice=v)]
import numpy as np; a=np.concatenate([o.numpy() for o in out]); print(\"KOKORO OK\", len(a)/24000, \"s audio in\", round(time.time()-t1,2), \"s\")"'
google-chrome --version; /home/unreal/venv/bin/python -c "import playwright, anthropic, aiohttp; print('venv ok')"
echo VOICE-DONE
