"""Pod-side file server: PUT /in/<name> stores an upload, GET /<name> serves /out/<name>. Every request must carry the
per-run job token in X-Job-Token (env SUB01_JOB_TOKEN, made by the job and never written to disk); without a token the
server refuses to start. Exits after 60 minutes so a forgotten pod stops working even before it is deleted."""
import hmac
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("SUB01_JOB_TOKEN", "")
if not TOKEN:
    sys.exit("refusing to start: SUB01_JOB_TOKEN is not set")


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory="/out", **k)

    def authorized(self):
        sent = self.headers.get("X-Job-Token", "")
        if hmac.compare_digest(sent.encode(), TOKEN.encode()):
            return True
        self.send_error(403, "missing or wrong job token")
        return False

    def do_GET(self):
        if self.authorized():
            super().do_GET()

    def do_PUT(self):
        if not self.authorized():
            return
        name = os.path.basename(self.path)
        n = int(self.headers.get("Content-Length", 0))
        tmp = f"/in/.{name}.part"
        with open(tmp, "wb") as f:
            while n > 0:
                chunk = self.rfile.read(min(n, 1 << 20))
                if not chunk:
                    break
                f.write(chunk)
                n -= len(chunk)
        os.replace(tmp, f"/in/{name}")
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


threading.Thread(target=lambda: (time.sleep(3600), os._exit(0)), daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
