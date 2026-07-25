import json
import os
import subprocess
import sys
import threading
import time
import uuid
import urllib.request

import folder_paths

JOBS = {}

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY_DIR = os.path.dirname(os.path.dirname(PLUGIN_DIR))
CUSTOM_NODES_DIR = os.path.dirname(PLUGIN_DIR)

NODE_MAP_LOCAL = os.path.join(CUSTOM_NODES_DIR, "comfyui-manager", "extension-node-map.json")
NODE_MAP_REMOTE = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json"


def new_job(kind, label):
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {
        "id": jid, "kind": kind, "label": label,
        "status": "pending", "progress": 0, "total": 0,
        "log": [], "error": None, "created": time.time(),
    }
    return JOBS[jid]


def _log(job, msg):
    job["log"].append(msg)
    if len(job["log"]) > 500:
        job["log"] = job["log"][-500:]


def _run_cmd(job, cmd, cwd=None):
    _log(job, "$ " + " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    for line in proc.stdout:
        _log(job, line.rstrip())
    proc.wait()
    return proc.returncode


_node_map_cache = {"data": None, "ts": 0}


def load_node_map():
    if _node_map_cache["data"] and time.time() - _node_map_cache["ts"] < 3600:
        return _node_map_cache["data"]
    data = None
    if os.path.exists(NODE_MAP_LOCAL):
        try:
            with open(NODE_MAP_LOCAL, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None
    if data is None:
        try:
            with urllib.request.urlopen(NODE_MAP_REMOTE, timeout=20) as resp:
                data = json.load(resp)
        except Exception:
            data = {}
    _node_map_cache.update(data=data, ts=time.time())
    return data


def find_node_packages(class_types):
    node_map = load_node_map()
    wanted = set(class_types)
    packages = []
    for url, entry in node_map.items():
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        provided = set(entry[0] if isinstance(entry[0], (list, tuple)) else [])
        hit = wanted & provided
        if hit:
            packages.append({"url": url, "provides": sorted(hit)})
    remaining = wanted - {c for p in packages for c in p["provides"]}
    return packages, sorted(remaining)


def install_nodes_job(class_types):
    job = new_job("nodes", ", ".join(class_types[:5]))
    job["status"] = "running"

    def work():
        try:
            packages, unresolved = find_node_packages(class_types)
            if unresolved:
                _log(job, "unresolved class_types: " + ", ".join(unresolved))
            if not packages:
                job["status"] = "failed"
                job["error"] = "no package found in extension-node-map"
                return
            job["total"] = len(packages)
            for i, pkg in enumerate(packages):
                url = pkg["url"]
                name = url.rstrip("/").rsplit("/", 1)[-1].replace(".git", "")
                dest = os.path.join(CUSTOM_NODES_DIR, name)
                _log(job, f"installing {name} from {url}")
                if os.path.exists(dest):
                    _log(job, f"{name} already exists, pulling")
                    _run_cmd(job, ["git", "-C", dest, "pull", "--ff-only"])
                else:
                    rc = _run_cmd(job, ["git", "clone", "--depth", "1", url, dest])
                    if rc != 0:
                        job["status"] = "failed"
                        job["error"] = f"git clone failed: {url}"
                        return
                req = os.path.join(dest, "requirements.txt")
                if os.path.exists(req):
                    rc = _run_cmd(job, [sys.executable, "-m", "pip", "install", "-r", req])
                    if rc != 0:
                        _log(job, f"warning: pip install failed for {name}")
                job["progress"] = i + 1
            job["status"] = "done"
            job["needs_restart"] = True
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)

    threading.Thread(target=work, daemon=True).start()
    return job


FOLDER_HINTS = [
    (("lora",), "loras"),
    (("vae",), "vae"),
    (("controlnet", "t2i", "openpose", "depth", "canny"), "controlnet"),
    (("upscale", "esrgan", "4x", "2x", "8x"), "upscale_models"),
    (("clip_vision",), "clip_vision"),
    (("clip", "text_encoder", "t5", "umt5", "llava"), "text_encoders"),
    (("unet", "flux", "wan", "hunyuan", "qwen", "sd3", "z_image"), "diffusion_models"),
    (("ipadapter",), "ipadapter"),
    (("embedding", "embeddings"), "embeddings"),
    (("sam", "segment"), "sams"),
    (("yolo", "ultralytics", "bbox", "segm"), "ultralytics"),
]


def guess_folder(filename, override=None):
    if override and override in folder_paths.folder_names_and_paths:
        return override
    low = filename.lower()
    for keys, folder in FOLDER_HINTS:
        if any(k in low for k in keys):
            if folder in folder_paths.folder_names_and_paths:
                return folder
    return "checkpoints"


def download_model_job(url=None, repo_id=None, filename=None, folder=None, use_mirror=True):
    label = filename or (url.rsplit("/", 1)[-1] if url else "model")
    job = new_job("model", label)
    job["status"] = "running"

    def work():
        try:
            target_folder = guess_folder(label, folder)
            dest_dir = folder_paths.folder_names_and_paths[target_folder][0][0]
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, label)
            dl_url = url
            if not dl_url and repo_id and filename:
                host = "https://hf-mirror.com" if use_mirror else "https://huggingface.co"
                dl_url = f"{host}/{repo_id}/resolve/main/{filename}"
            if not dl_url:
                job["status"] = "failed"
                job["error"] = "no url or repo_id/filename given"
                return
            if use_mirror and "huggingface.co" in dl_url:
                dl_url = dl_url.replace("https://huggingface.co", "https://hf-mirror.com")
            _log(job, f"downloading {dl_url} -> {dest}")
            req = urllib.request.Request(dl_url, headers={"User-Agent": "ComfyUI-AI-Executor"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest + ".part", "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                job["total"] = total
                done = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    job["progress"] = done
            os.replace(dest + ".part", dest)
            job["status"] = "done"
            job["saved_to"] = dest
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)

    threading.Thread(target=work, daemon=True).start()
    return job


def get_job(jid):
    return JOBS.get(jid)
