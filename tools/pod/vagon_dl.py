"""Download files from the pod's /tmp/sub01-share/<path> through the Jupyter contents API (same auth as jupput.py),
never printing the token.

usage: python -I vagon_dl.py pods.json POD_ID OUT_DIR path [path ...]   (paths relative to /tmp/sub01-share/)
"""
import base64
import json
import os
import subprocess
import sys

pods_file, pod_id, out_dir, paths = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
pods = json.load(open(pods_file))
pod = next(p for p in pods if isinstance(p, dict) and p.get("id") == pod_id)
token = pod["env"]["JUPYTER_PASSWORD"]
os.makedirs(out_dir, exist_ok=True)
for rel in paths:
    url = f"https://{pod_id}-8888.proxy.runpod.net/api/contents/tmp/sub01-share/{rel}?content=1&format=base64&type=file"
    r = subprocess.run(["curl", "-sS", "-m", "120", "-H", "Authorization: token " + token, url], capture_output=True, text=True)
    try:
        doc = json.loads(r.stdout)
        data = base64.b64decode(doc["content"])
    except Exception as error:
        print(f"{rel}: FAILED {type(error).__name__} http-body={r.stdout[:120].replace(token, '<token>')!r} err={r.stderr[:80].replace(token, '<token>')!r}")
        continue
    dest = os.path.join(out_dir, os.path.basename(rel))
    with open(dest, "wb") as f:
        f.write(data)
    print(f"{rel}: {len(data)} bytes -> {dest}")
