"""Set live tuning keys in the private face-tuning file (as unreal): tune_set.py key=value ... ; bumps `sequence` so the
game applies them, writes atomically, keeps a timestamped backup and prints the previous values. The game clamps every
value to its compiled limits."""
import json, os, shutil, sys, tempfile, time
P = "/home/unreal/.sub01-private/streamer-visual-face-tuning.json"
BAK = "/home/sub01-review-20261027"
st = os.stat(P)                                  # the game reads it as unreal: keep its owner whoever runs this
d = json.load(open(P))
shutil.copy2(P, f"{BAK}/face-tuning.bak-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{os.getpid()}.json")
prev = {}
for kv in sys.argv[1:]:
    k, v = kv.split("=", 1)
    prev[k] = d.get(k)
    d[k] = float(v)
d["sequence"] = max(int(time.time() * 1000), int(d.get("sequence", 0)) + 1)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(P), prefix=".tuning-")   # unique: concurrent runs never share it
with os.fdopen(fd, "w") as f:
    json.dump(d, f)
os.chmod(tmp, 0o600)
os.chown(tmp, st.st_uid, st.st_gid)
os.replace(tmp, P)
print(json.dumps({"previous": prev, "now": {k: d[k] for k in prev}, "sequence": d["sequence"]}))
