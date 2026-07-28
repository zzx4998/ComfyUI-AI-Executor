import hashlib
import json
import os
import time
import urllib.request

from . import proxy

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PLUGIN_DIR, "cache", "samples")
CACHE_MAX_BYTES = 200 << 20

BATCHES = {}


def _cache_prune():
    if not os.path.isdir(CACHE_DIR):
        return
    files = []
    total = 0
    for name in os.listdir(CACHE_DIR):
        p = os.path.join(CACHE_DIR, name)
        if os.path.isfile(p):
            st = os.stat(p)
            files.append((st.st_mtime, st.st_size, p))
            total += st.st_size
    if total <= CACHE_MAX_BYTES:
        return
    files.sort()
    for mtime, size, p in files:
        try:
            os.remove(p)
            total -= size
        except OSError:
            pass
        if total <= CACHE_MAX_BYTES:
            break


def cache_sample(url):
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"):
        ext = ".png" if "image" in url else ".mp4"
    dest = os.path.join(CACHE_DIR, h + ext)
    if os.path.exists(dest):
        return h + ext
    p = proxy.get_proxy()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": p, "https": p}) if p else urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-AI-Executor"})
    with opener.open(req, timeout=30) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    _cache_prune()
    return h + ext


def get_sample_path(name):
    safe = os.path.basename(name)
    p = os.path.join(CACHE_DIR, safe)
    return p if os.path.exists(p) else None


def present(candidates):
    import uuid
    batch_id = uuid.uuid4().hex[:10]
    token = uuid.uuid4().hex
    out = []
    for i, c in enumerate(candidates[:8]):
        samples = []
        for s in (c.get("samples") or [])[:4]:
            url = s.get("url")
            if not url:
                continue
            try:
                fname = cache_sample(url)
                samples.append({"type": s.get("type", "image"), "url": f"/ai_executor/samples/{fname}"})
            except Exception:
                samples.append({"type": s.get("type", "image"), "url": url})
        out.append({
            "index": i,
            "title": c.get("title", ""),
            "source": c.get("source", ""),
            "url": c.get("url", ""),
            "published_at": c.get("published_at"),
            "base_model": c.get("base_model"),
            "description": c.get("description", ""),
            "reason": c.get("reason", ""),
            "samples": samples,
        })
    BATCHES[batch_id] = {
        "id": batch_id,
        "token": token,
        "candidates": out,
        "chosen": None,
        "workflow": None,
        "created": time.time(),
    }
    for bid in [b for b, v in BATCHES.items() if time.time() - v["created"] > 3600]:
        BATCHES.pop(bid, None)
    return {"batch_id": batch_id, "token": token, "count": len(out)}


def pending_batches():
    return [v for v in BATCHES.values() if v["chosen"] is None]


def dismiss_all():
    BATCHES.clear()


def get_batch(batch_id):
    return BATCHES.get(batch_id)


def choose(batch_id, index):
    b = BATCHES.get(batch_id)
    if not b:
        return None
    if 0 <= index < len(b["candidates"]):
        b["chosen"] = index
        return b["candidates"][index]
    return None


def check_token(batch_id, token):
    b = BATCHES.get(batch_id)
    return bool(b and b["token"] == token and b["chosen"] is not None)


def set_workflow(batch_id, workflow):
    b = BATCHES.get(batch_id)
    if b:
        b["workflow"] = workflow
