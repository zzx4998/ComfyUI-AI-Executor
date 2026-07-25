import asyncio
import os
import shutil
import subprocess
import threading
import time

import aiohttp

from . import installer

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKDIR = os.path.join(PLUGIN_DIR, "opencode")

_state = {"proc": None, "port": 4097, "exe": None}


def find_exe():
    if _state["exe"] and shutil.which(_state["exe"]):
        return _state["exe"]
    for name in ("opencode", "opencode.exe"):
        p = shutil.which(name)
        if p:
            _state["exe"] = p
            return p
    return None


def base_url():
    return f"http://127.0.0.1:{_state['port']}"


async def health():
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(base_url() + "/global/health") as r:
                if r.status == 200:
                    return await r.json(content_type=None)
    except Exception:
        pass
    return None


def start(port=4097):
    if _state["proc"] and _state["proc"].poll() is None:
        return {"ok": True, "already": True, "port": _state["port"]}
    exe = find_exe()
    if not exe:
        return {"ok": False, "error": "opencode executable not found on PATH. Install: npm i -g opencode-ai"}
    os.makedirs(WORKDIR, exist_ok=True)
    _state["port"] = port
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    _state["proc"] = subprocess.Popen(
        [exe, "serve", "--port", str(port), "--hostname", "127.0.0.1"],
        cwd=WORKDIR,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return {"ok": True, "pid": _state["proc"].pid, "port": port}


def stop():
    proc = _state["proc"]
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    _state["proc"] = None
    return {"ok": True}


async def status():
    h = await health()
    return {
        "installed": find_exe() is not None,
        "running": h is not None,
        "health": h,
        "port": _state["port"],
    }


async def _post(path, payload):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(base_url() + path, json=payload) as r:
            if r.status == 204:
                return None
            return await r.json(content_type=None)


async def _get(path):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.get(base_url() + path) as r:
            return await r.json(content_type=None)


TASK_PROMPT = """你在一个 ComfyUI 本地环境中执行图像/视频处理任务。规则手册见当前目录 AGENTS.md，必须遵守。

ComfyUI 插件 API 基址: {api_base}

用户需求: {requirement}

用户输入素材: {images}

请按 AGENTS.md 的流程执行: 理解需求 → 翻译扩充检索 → 搜索筛选工作流 → 依赖检查与安装 → 参数注入 → 运行 → 汇报结果文件。完成后用中文给出简明总结。"""


async def dispatch(requirement, api_base, images=None, title=None):
    if not await health():
        return {"ok": False, "error": "opencode server not running"}
    session = await _post("/session", {"title": title or f"comfyui-{int(time.time())}"})
    sid = session.get("id")
    if not sid:
        return {"ok": False, "error": f"failed to create session: {session}"}
    prompt = TASK_PROMPT.format(
        api_base=api_base,
        requirement=requirement,
        images=json_images(images),
    )
    await _post(f"/session/{sid}/prompt_async", {"parts": [{"type": "text", "text": prompt}]})
    return {"ok": True, "session_id": sid}


def json_images(images):
    if not images:
        return "无"
    out = []
    for img in images:
        out.append(img.get("filename", "input.png") + " (已通过 /ai_executor/upload 上传,文件名可直接用于注入 LoadImage 节点)")
    return "; ".join(out)


async def messages(session_id):
    return await _get(f"/session/{session_id}/message")


def find_npm():
    for name in ("npm.cmd", "npm", "npm.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def install_opencode_job():
    job = installer.new_job("opencode_install", "npm i -g opencode-ai")
    job["status"] = "running"

    def work():
        try:
            npm = find_npm()
            if not npm:
                job["status"] = "failed"
                job["error"] = "npm not found. Install Node.js first: https://nodejs.org"
                return
            proc = subprocess.Popen(
                [npm, "i", "-g", "opencode-ai"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in proc.stdout:
                installer._log(job, line.rstrip())
            proc.wait()
            _state["exe"] = None
            if proc.returncode == 0 and find_exe():
                job["status"] = "done"
            else:
                job["status"] = "failed"
                job["error"] = f"npm exited with {proc.returncode}"
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)

    threading.Thread(target=work, daemon=True).start()
    return job


async def providers():
    h = await health()
    if not h:
        return {"error": "opencode server not running"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.get(base_url() + "/provider") as r:
            data = await r.json(content_type=None)
        async with s.get(base_url() + "/config") as r:
            cfg = await r.json(content_type=None)
    out = []
    for p in data.get("all", []):
        out.append({
            "id": p.get("id"),
            "name": p.get("name") or p.get("id"),
            "connected": p.get("id") in (data.get("connected") or []),
            "models": sorted((p.get("models") or {}).keys()),
        })
    return {"providers": out, "default": data.get("default") or {}, "current_model": cfg.get("model")}


async def set_auth(provider_id, api_key):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.put(base_url() + f"/auth/{provider_id}", json={"type": "api", "key": api_key}) as r:
            ok = r.status == 200
            body = await r.text()
    return {"ok": ok, "response": body[:500]}


async def set_default_model(model):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.patch(base_url() + "/config", json={"model": model}) as r:
            ok = r.status == 200
    return {"ok": ok, "model": model}


async def onboarding():
    installed = find_exe() is not None
    running = await health() is not None
    stage = "ready"
    detail = {}
    if not installed:
        stage = "install"
        detail["npm"] = find_npm() is not None
    else:
        prov = await providers() if running else {"error": "not running"}
        if not running:
            stage = "start"
        elif "error" in prov:
            stage = "start"
        else:
            connected = [p for p in prov["providers"] if p["connected"]]
            detail["connected"] = [p["id"] for p in connected]
            detail["current_model"] = prov.get("current_model")
            if not connected:
                stage = "auth"
            elif not prov.get("current_model"):
                stage = "model"
    return {"stage": stage, "installed": installed, "running": running, "detail": detail}


async def session_status():
    return await _get("/session/status")


async def abort(session_id):
    return await _post(f"/session/{session_id}/abort", {})
