"""Upload a local file to the pod through the Jupyter contents API: jupput.py pods.json POD_ID local_path remote_path"""
import base64, json, subprocess, sys, tempfile
pods = json.load(open(sys.argv[1])); pod = [p for p in pods if p["id"] == sys.argv[2]][0]
token = pod["env"]["JUPYTER_PASSWORD"]; local, remote = sys.argv[3], sys.argv[4].strip("/")
body = {"type": "file", "format": "base64", "content": base64.b64encode(open(local, "rb").read()).decode()}
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(body, f); tmp = f.name
r = subprocess.run(["curl", "-sS", "-m", "300", "-X", "PUT", "-H", "Authorization: token " + token, "-H", "Content-Type: application/json",
                    "--data-binary", "@" + tmp, "-o", "/dev/null", "-w", "%{http_code}", f"https://{sys.argv[2]}-8888.proxy.runpod.net/api/contents/{remote}"],
                   capture_output=True, text=True)
print("PUT", remote, "->", r.stdout.strip(), r.stderr.strip()[:200])
