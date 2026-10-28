"""RunPod network volume: get or grow. usage: netvol.py get ID | netvol.py grow ID NEW_SIZE_GB. The key is read from the
saved pods listing (field SUB01_HOME_CONTROL_API_KEY) and never printed."""
import json, re, sys, urllib.request
S = __import__("os").environ.get("SUB01_POD_SECRETS_DIR", ".")   # holds pods_body.txt (never committed)
key = re.search(r'"SUB01_HOME_CONTROL_API_KEY"\s*:\s*"(rpa_[A-Za-z0-9]+)"', open(f"{S}/pods_body.txt").read()).group(1)
op, vid = sys.argv[1], sys.argv[2]
url = f"https://rest.runpod.io/v1/networkvolumes/{vid}"
body, method = None, "GET"
if op == "grow":
    body, method = json.dumps({"size": int(sys.argv[3])}).encode(), "PATCH"
req = urllib.request.Request(url, data=body, method=method, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.status, json.dumps(json.load(r)))
except urllib.error.HTTPError as e:
    print(e.code, e.read()[:500].decode("utf-8", "replace").replace(key, "***"))
