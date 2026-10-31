set -x
P=/home/unreal/.sub01-private; mkdir -p $P/voices; F=$(ls /workspace/voices.tgz /voices.tgz /root/voices.tgz 2>/dev/null | head -1)
tar xzf $F -C $P/voices && rm -f $F; cd $P/voices && mv ccf39d76-sub-01.wav sub01-full.wav; mv 5b281c72-kimchi.wav kimchi-full.wav
ffmpeg -hide_banner -loglevel error -y -i sub01-full.wav -t 9 sub01-ref.wav; ffmpeg -hide_banner -loglevel error -y -i kimchi-full.wav -t 9 kimchi-ref.wav
chown -R unreal:unreal $P/voices
su - unreal -c 'python3 -m venv --system-site-packages /home/unreal/omni-venv && /home/unreal/omni-venv/bin/pip install -q omnivoice soundfile' 
/home/unreal/omni-venv/bin/python -c "import torch; print('torch', torch.__version__)"
echo OMNI-SETUP-DONE
