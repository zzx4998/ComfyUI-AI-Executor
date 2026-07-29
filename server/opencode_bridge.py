import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile

import aiohttp

from . import installer, proxy, supervisor

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKDIR = os.path.join(PLUGIN_DIR, "opencode")
CONFIG_PATH = os.path.join(PLUGIN_DIR, "config.json")

RELEASE_API = "https://api.github.com/repos/anomalyco/opencode/releases/latest"


def _read_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

_state = {"proc": None, "port": 4097, "exe": None}


def find_exe():
    if _state["exe"] and os.path.exists(_state["exe"]):
        return _state["exe"]
    configured = _read_config().get("opencode_exe")
    if configured and os.path.exists(configured):
        _state["exe"] = configured
        return configured
    bin_dir = os.path.join(PLUGIN_DIR, "bin")
    for name in ("opencode.exe", "opencode"):
        p = os.path.join(bin_dir, name)
        if os.path.exists(p):
            _state["exe"] = p
            cfg = _read_config()
            cfg["opencode_exe"] = p
            _write_config(cfg)
            return p
    for name in ("opencode", "opencode.exe"):
        p = shutil.which(name)
        if p:
            _state["exe"] = p
            return p
    return None


def platform_asset_name():
    if os.name == "nt":
        machine = (os.environ.get("PROCESSOR_ARCHITECTURE") or "").lower()
        return "opencode-windows-arm64.zip" if "arm" in machine else "opencode-windows-x64.zip"
    import platform
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    if sysname == "darwin":
        return "opencode-darwin-arm64.zip" if "arm" in machine else "opencode-darwin-x64.zip"
    return "opencode-linux-arm64.zip" if "arm" in machine or "aarch64" in machine else "opencode-linux-x64.zip"


def _url_opener():
    p = proxy.get_proxy()
    if p:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": p, "https": p}))
    return urllib.request.build_opener()


def install_binary_job(dest_dir, timeout_sec=120, auto_retry=True, retry_max=3):
    job = installer.new_job("opencode_binary", dest_dir)
    job["status"] = "running"

    def work():
        try:
            os.makedirs(dest_dir, exist_ok=True)
            installer._log(job, "fetching latest release info...")
            opener = _url_opener()
            req = urllib.request.Request(RELEASE_API, headers={"User-Agent": "ComfyUI-AI-Executor"})
            with opener.open(req, timeout=30) as resp:
                release = json.load(resp)
            want = platform_asset_name()
            asset = next((a for a in release.get("assets", []) if a.get("name") == want), None)
            if not asset:
                job["status"] = "failed"
                job["error"] = f"asset {want} not found in release {release.get('tag_name')}"
                return
            url = asset["browser_download_url"]
            tag = release.get("tag_name")
            zip_path = os.path.join(dest_dir, want)
            installer._log(job, f"downloading {tag} {want} via proxy={proxy.get_proxy() or 'direct'} ...")
            installer.download_with_watch(job, url, zip_path, timeout_sec, auto_retry, retry_max,
                                          min_bytes=1 << 20)
            installer._log(job, "extracting...")
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(dest_dir)
            os.remove(zip_path)
            exe = None
            for root, _, files in os.walk(dest_dir):
                for name in files:
                    if name in ("opencode.exe", "opencode"):
                        exe = os.path.join(root, name)
                        break
                if exe:
                    break
            if not exe:
                job["status"] = "failed"
                job["error"] = "opencode binary not found after extraction"
                return
            cfg = _read_config()
            cfg["opencode_exe"] = exe
            _write_config(cfg)
            _state["exe"] = exe
            job["status"] = "done"
            job["saved_to"] = exe
            installer._log(job, f"installed {tag} -> {exe}")
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)

    threading.Thread(target=work, daemon=True).start()
    return job


def uninstall():
    stop()
    exe = find_exe()
    removed = []
    locked = []
    targets = set()
    if exe and exe.startswith(PLUGIN_DIR):
        targets.add(os.path.dirname(exe))
    bin_dir = os.path.join(PLUGIN_DIR, "bin")
    if os.path.isdir(bin_dir):
        targets.add(bin_dir)
    for d in targets:
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                    removed.append(p)
            except OSError:
                locked.append(p)
    cfg = _read_config()
    cfg.pop("opencode_exe", None)
    _write_config(cfg)
    _state["exe"] = None
    return {"ok": not locked, "removed": removed, "locked": locked,
            "hint": "有文件被占用,请重启 ComfyUI 后再次卸载" if locked else ""}


def browse_dirs(path):
    if not path:
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            d = f"{letter}:\\"
            if os.path.isdir(d):
                drives.append(d)
        return {"path": "", "parent": None, "dirs": drives}
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return {"error": "not a directory", "path": path}
    parent = os.path.dirname(path)
    if parent == path:
        parent = ""
    dirs = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full):
                dirs.append(full)
    except PermissionError:
        pass
    return {"path": path, "parent": parent, "dirs": dirs[:200]}


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


TEMPLATE_PATH = os.path.join(WORKDIR, "opencode.template.json")
RUNTIME_CONFIG_PATH = os.path.join(WORKDIR, "opencode.json")


COMMAND_NAME = "comfyui_task"

COMMAND_TEMPLATE = """你在一个 ComfyUI 本地环境中执行图像/视频处理任务。规则手册见当前目录 AGENTS.md，必须严格遵守其中的铁律与分阶段流水线。

ComfyUI 插件 API 基址: {api_base}

用户需求: $ARGUMENTS

按 AGENTS.md 的阶段流水线执行：阶段0 需求确认 → 阶段1 在线检索 → 阶段2 上报候选(含样例与说明) → 阶段3 等待用户选择(禁止擅自选定) → 阶段4 落地(保存工作流/装依赖/打开画布/运行)。全程用中文与用户交流。"""


def build_runtime_config():
    cfg = _read_config()
    llm = cfg.get("llm") or {}
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        from comfy.cli_args import args as comfy_args
        port = getattr(comfy_args, "port", 8188)
    except Exception:
        port = 8188
    data["command"] = {
        COMMAND_NAME: {
            "description": "执行 ComfyUI 图像/视频处理任务 (固定流水线)",
            "template": COMMAND_TEMPLATE.format(api_base=f"http://127.0.0.1:{port}/ai_executor"),
        }
    }
    env = {}
    base = (llm.get("base_url") or "").strip()
    key = (llm.get("api_key") or "").strip()
    model = (llm.get("model") or "").strip()
    if base and key:
        proto = (llm.get("proto") or "openai").strip()
        npm = "@ai-sdk/anthropic" if proto == "anthropic" else "@ai-sdk/openai-compatible"
        providers = data.setdefault("provider", {})
        custom = providers.setdefault("aie-custom", {
            "npm": npm,
            "name": "自定义 LLM (来自插件 LLM 设置)",
            "options": {"baseURL": "{env:AIE_LLM_BASE}", "apiKey": "{env:AIE_LLM_KEY}"},
            "models": {},
        })
        custom["npm"] = npm
        if model:
            custom.setdefault("models", {})[model] = {"name": model}
            data["model"] = f"aie-custom/{model}"
        env["AIE_LLM_BASE"] = base
        env["AIE_LLM_KEY"] = key
    else:
        data.pop("provider", None)
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return env


def start(port=4097):
    exe = find_exe()
    if not exe:
        return {"ok": False, "error": "opencode executable not found. 请先安装"}
    os.makedirs(WORKDIR, exist_ok=True)
    extra_env = build_runtime_config()
    _state["port"] = port
    sup = supervisor.ensure_running()
    if sup:
        try:
            r = supervisor.opencode_start(sup, exe, WORKDIR, port, extra_env)
            if r.get("ok"):
                return {"ok": True, "port": port, "via": "supervisor", "custom_llm": bool(extra_env)}
        except Exception as e:
            installer._log({"log": []}, f"supervisor start failed: {e}")
    if _state["proc"] and _state["proc"].poll() is None:
        return {"ok": True, "already": True, "port": _state["port"]}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = dict(os.environ)
    env.update(extra_env)
    _state["proc"] = subprocess.Popen(
        [exe, "serve", "--port", str(port), "--hostname", "127.0.0.1"],
        cwd=WORKDIR,
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return {"ok": True, "pid": _state["proc"].pid, "port": port, "via": "direct", "custom_llm": bool(extra_env)}


def stop():
    sup = supervisor.find_supervisor()
    if sup:
        try:
            supervisor.opencode_stop(sup)
        except Exception:
            pass
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


async def dispatch(requirement, api_base, images=None, title=None):
    if not await health():
        return {"ok": False, "error": "opencode server not running"}
    session = await _post("/session", {"title": title or f"comfyui-{int(time.time())}"})
    sid = session.get("id")
    if not sid:
        return {"ok": False, "error": f"failed to create session: {session}"}
    args = requirement
    if images:
        args += "\n\n用户输入素材: " + json_images(images)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(base_url() + f"/session/{sid}/command",
                         json={"command": COMMAND_NAME, "arguments": args})
    except Exception:
        pass
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
            if prov.get("current_model"):
                stage = "ready"
            elif not connected:
                stage = "auth"
            else:
                stage = "model"
    return {"stage": stage, "installed": installed, "running": running, "detail": detail}


async def session_status():
    return await _get("/session/status")


async def questions():
    try:
        data = await _get("/question")
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def question_reply(question_id, answers):
    return await _post(f"/question/{question_id}/reply", {"answers": answers})


async def question_reject(question_id):
    return await _post(f"/question/{question_id}/reject", {})


async def abort(session_id):
    return await _post(f"/session/{session_id}/abort", {})
