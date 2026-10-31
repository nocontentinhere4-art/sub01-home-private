"""podput.py pods.json POD_ID LOCAL_FILE REMOTE_NAME: upload one file into the Jupyter root (contents API, base64)."""
import base64, json, ssl, sys, os, http.cookiejar, urllib.request
pods = json.load(open(sys.argv[1])); pod = [p for p in pods if p["id"] == sys.argv[2]][0]
tok = pod["env"]["JUPYTER_PASSWORD"]; base = f"https://{sys.argv[2]}-8888.proxy.runpod.net"
ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt") if os.path.exists("/root/.ccr/ca-bundle.crt") else None
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.HTTPCookieProcessor(jar)); op.addheaders = [("User-Agent", "Mozilla/5.0 sub01-upload")]
op.open(urllib.request.Request(f"{base}/api/contents?token={tok}", headers={"Authorization": f"token {tok}"}), timeout=30).read()
op.open(urllib.request.Request(f"{base}/lab?token={tok}"), timeout=30).read()
xsrf = next((c.value for c in jar if c.name == "_xsrf"), "")
data = open(sys.argv[3], "rb").read()
body = json.dumps({"type": "file", "format": "base64", "content": base64.b64encode(data).decode()}).encode()
req = urllib.request.Request(f"{base}/api/contents/{sys.argv[4]}", data=body, method="PUT",
                             headers={"Authorization": f"token {tok}", "Content-Type": "application/json", "X-XSRFToken": xsrf})
try:
    with op.open(req, timeout=180) as r:
        d = json.load(r); print("uploaded", d.get("path"), d.get("size"), "bytes")
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read()[:200].decode(errors="replace").replace(tok, "***"))
