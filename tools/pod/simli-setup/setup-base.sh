set -x
export DEBIAN_FRONTEND=noninteractive
id unreal 2>/dev/null || useradd -m -u 1001 -s /bin/bash unreal
apt-get update
apt-get install -y --no-install-recommends xvfb xdotool x11-utils pulseaudio pulseaudio-utils ffmpeg python3-venv python3-dev \
  fonts-dejavu fonts-noto-color-emoji fonts-liberation wget curl ca-certificates gnupg jq procps psmisc net-tools rsync
wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && apt-get install -y /tmp/chrome.deb
wget -q -O /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && apt-get install -y /tmp/cloudflared.deb
su - unreal -c 'python3 -m venv /home/unreal/venv && /home/unreal/venv/bin/pip install -q aiohttp anthropic numpy scipy pillow playwright openai websockets'
su - unreal -c '/home/unreal/venv/bin/python -m playwright install chromium' 
/home/unreal/venv/bin/python -m playwright install-deps chromium
mkdir -p /home/unreal/.sub01-private/streamer && chown -R unreal:unreal /home/unreal/.sub01-private && chmod 700 /home/unreal/.sub01-private
google-chrome --version; ffmpeg -version | head -1; cloudflared --version
echo SETUP-DONE
