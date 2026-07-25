import asyncio
import os
import shutil
import subprocess
import time

import aiohttp

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


async def session_status():
    return await _get("/session/status")


async def abort(session_id):
    return await _post(f"/session/{session_id}/abort", {})
