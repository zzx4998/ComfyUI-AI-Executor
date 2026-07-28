import json
import os
import subprocess
import sys
import time
import urllib.request

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PLUGIN_DIR, "cache")
STATE_PATH = os.path.join(CACHE_DIR, "supervisor.json")
LOG_PATH = os.path.join(CACHE_DIR, "supervisor.log")

BASE_PORT = 4123
ROLE = "ai-executor-supervisor"


def _log(msg):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def read_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def health(port, timeout=2):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            data = json.load(r)
            if data.get("role") == ROLE:
                return data
    except Exception:
        pass
    return None


def find_supervisor():
    st = read_state()
    for port in [st.get("port")] + list(range(BASE_PORT, BASE_PORT + 5)):
        if not port:
            continue
        h = health(port)
        if h:
            return port
    return None


def ensure_running():
    port = find_supervisor()
    if port:
        return port
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.abspath(__file__)
    cmd = f'"{exe}" "{script}" --serve'
    ps = ("Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
          f"-Arguments @{{CommandLine = '{cmd}'}} | Out-Null")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        _log(f"wmi spawn failed: {e}")
        return None
    for _ in range(40):
        port = find_supervisor()
        if port:
            _log(f"supervisor up on {port}")
            return port
        time.sleep(0.5)
    _log("supervisor did not come up")
    return None


def _post(port, path, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def opencode_start(port, exe, cwd, oc_port, env):
    return _post(port, "/opencode/start", {"exe": exe, "cwd": cwd, "port": oc_port, "env": env})


def opencode_stop(port):
    return _post(port, "/opencode/stop", {})


def serve():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {"proc": None}

    class H(BaseHTTPRequestHandler):
        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"ok": True, "role": ROLE, "pid": os.getpid(),
                                 "opencode_running": state["proc"] is not None and state["proc"].poll() is None})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                body = {}
            if self.path == "/opencode/start":
                if state["proc"] and state["proc"].poll() is None:
                    self._json(200, {"ok": True, "already": True})
                    return
                env = dict(os.environ)
                env.update(body.get("env") or {})
                try:
                    state["proc"] = subprocess.Popen(
                        [body["exe"], "serve", "--port", str(body["port"]), "--hostname", "127.0.0.1"],
                        cwd=body["cwd"], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    _log(f"opencode started pid={state['proc'].pid} port={body['port']}")
                    self._json(200, {"ok": True, "pid": state["proc"].pid})
                except Exception as e:
                    _log(f"opencode start failed: {e}")
                    self._json(500, {"ok": False, "error": str(e)})
            elif self.path == "/opencode/stop":
                p = state["proc"]
                if p and p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except Exception:
                        p.kill()
                state["proc"] = None
                _log("opencode stopped")
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "not found"})

    port = BASE_PORT
    server = None
    for _ in range(5):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            port += 1
    if server is None:
        _log("no free port for supervisor")
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"port": port, "pid": os.getpid()}, f)
    _log(f"supervisor serving on {port} pid={os.getpid()}")
    try:
        server.serve_forever()
    finally:
        try:
            os.remove(STATE_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
