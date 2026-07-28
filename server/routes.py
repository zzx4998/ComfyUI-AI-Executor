import asyncio
import base64
import json
import os
import sys
import threading

import aiohttp
from aiohttp import web
from server import PromptServer

from . import analyzer, candidates, deps, installer, local_index, opencode_bridge, proxy, runner
from .sources import civitai, github_collections, openart

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PLUGIN_DIR, "config.json")

SOURCES = {
    "civitai": civitai,
    "openart": openart,
    "github": github_collections,
}


def _load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


routes = web.RouteTableDef()


@routes.get("/ai_executor/ping")
async def ping(request):
    return web.json_response({"ok": True, "version": "0.1.0"})


@routes.get("/ai_executor/settings")
async def get_settings(request):
    cfg = _load_config()
    safe = dict(cfg)
    llm = dict(safe.get("llm") or {})
    llm["has_key"] = bool(llm.get("api_key"))
    llm.pop("api_key", None)
    safe["llm"] = llm
    return web.json_response(safe)


@routes.post("/ai_executor/settings")
async def set_settings(request):
    body = await request.json()
    cfg = _load_config()
    if "llm" in body:
        llm = body["llm"] or {}
        if not llm.get("api_key") or llm.get("api_key") == "***":
            llm["api_key"] = (cfg.get("llm") or {}).get("api_key", "")
        cfg["llm"] = llm
    for k in ("hf_mirror", "github_token", "github_repos", "proxy", "opencode_exe"):
        if k in body:
            cfg[k] = body[k]
    _save_config(cfg)
    return web.json_response({"ok": True})


@routes.get("/ai_executor/search")
async def search(request):
    query = request.query.get("query", "")
    sources = [s for s in request.query.get("sources", "local,civitai,openart,github").split(",") if s]
    limit = int(request.query.get("limit", "12"))
    cfg = _load_config()
    results = []
    errors = {}

    async def run_source(name):
        try:
            if name == "local":
                return local_index.search(query, limit)
            mod = SOURCES.get(name)
            if not mod:
                return []
            kwargs = {}
            if name == "github":
                kwargs["token"] = cfg.get("github_token") or None
                if cfg.get("github_repos"):
                    kwargs["repos"] = cfg["github_repos"]
            return await mod.search(query, limit=limit, **kwargs)
        except Exception as e:
            errors[name] = str(e)
            return []

    batches = await asyncio.gather(*(run_source(s) for s in sources))
    for b in batches:
        results.extend(b)
    return web.json_response({"results": results, "errors": errors})


@routes.post("/ai_executor/workflow")
async def get_workflow(request):
    body = await request.json()
    source = body.get("source")
    if source == "local":
        wf = local_index.load_workflow(body.get("id", ""))
        return web.json_response({"workflow": wf})
    mod = SOURCES.get(source)
    if not mod:
        return web.json_response({"error": "unknown source"}, status=400)
    try:
        wf = await mod.get_workflow(body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)
    if wf is None:
        return web.json_response({"error": "workflow not available from this source"}, status=404)
    return web.json_response({"workflow": wf})


@routes.post("/ai_executor/deps/check")
async def deps_check(request):
    body = await request.json()
    wf = body.get("workflow")
    if wf is None:
        return web.json_response({"error": "workflow required"}, status=400)
    return web.json_response(deps.full_check(wf))


@routes.post("/ai_executor/install/nodes")
async def install_nodes(request):
    body = await request.json()
    class_types = body.get("class_types") or []
    if not class_types:
        return web.json_response({"error": "class_types required"}, status=400)
    job = installer.install_nodes_job(class_types)
    return web.json_response({"job_id": job["id"]})


@routes.post("/ai_executor/install/model")
async def install_model(request):
    body = await request.json()
    cfg = _load_config()
    use_mirror = cfg.get("hf_mirror", True)
    job = installer.download_model_job(
        url=body.get("url"),
        repo_id=body.get("repo_id"),
        filename=body.get("filename"),
        folder=body.get("folder"),
        use_mirror=bool(body.get("use_mirror", use_mirror)),
        timeout_sec=int(body.get("timeout_sec", 120)),
        auto_retry=bool(body.get("auto_retry", True)),
        retry_max=int(body.get("retry_max", 3)),
    )
    return web.json_response({"job_id": job["id"]})


@routes.get("/ai_executor/jobs/{jid}")
async def job_status(request):
    job = installer.get_job(request.match_info["jid"])
    if not job:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(job)


@routes.post("/ai_executor/run")
async def run(request):
    body = await request.json()
    if not candidates.check_token(body.get("batch_id", ""), body.get("token", "")):
        return web.json_response({"ok": False, "error": "invalid token: 用户必须先在面板中选定候选工作流"}, status=403)
    wf = body.get("workflow")
    if wf is None:
        return web.json_response({"error": "workflow required"}, status=400)
    if body.get("params"):
        wf, applied = runner.inject_params(wf, body["params"])
    if body.get("randomize_seed", True):
        wf = runner.randomize_seeds(wf)
    for img in body.get("images", []) or []:
        try:
            data = base64.b64decode(img["data"])
            name = runner.save_input_image(img.get("filename", "ai_executor_input.png"), data)
            targets = img.get("nodes") or []
            for nid in targets:
                nid = str(nid)
                if nid in wf and isinstance(wf[nid], dict):
                    wf[nid].setdefault("inputs", {})["image"] = name
        except Exception:
            continue
    result = runner.queue_prompt(wf, extra_data={"extra_pnginfo": {}})
    return web.json_response(result)


@routes.get("/ai_executor/env")
async def env_info(request):
    import folder_paths
    import nodes as comfy_nodes
    models = {}
    for folder in folder_paths.folder_names_and_paths.keys():
        try:
            files = folder_paths.get_filename_list(folder)
            if files:
                models[folder] = files
        except Exception:
            continue
    node_names = sorted(comfy_nodes.NODE_CLASS_MAPPINGS.keys())
    return web.json_response({
        "nodes": node_names,
        "node_count": len(node_names),
        "models": models,
        "api_base": "/ai_executor",
    })


@routes.post("/ai_executor/classify")
async def classify(request):
    body = await request.json()
    wf = body.get("workflow")
    if wf is None:
        return web.json_response({"error": "workflow required"}, status=400)
    return web.json_response(analyzer.classify(wf))


@routes.post("/ai_executor/upload")
async def upload(request):
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "image":
        return web.json_response({"error": "multipart field 'image' required"}, status=400)
    filename = field.filename or "ai_executor_input.png"
    data = await field.read()
    saved = runner.save_input_image(filename, data)
    return web.json_response({"ok": True, "filename": saved})


@routes.get("/ai_executor/run_status/{prompt_id}")
async def run_status(request):
    return web.json_response(runner.run_status(request.match_info["prompt_id"]))


@routes.get("/ai_executor/opencode/status")
async def oc_status(request):
    return web.json_response(await opencode_bridge.status())


@routes.post("/ai_executor/opencode/start")
async def oc_start(request):
    result = opencode_bridge.start()
    if result.get("ok"):
        for _ in range(20):
            if await opencode_bridge.health():
                result["ready"] = True
                break
            await asyncio.sleep(0.5)
    return web.json_response(result)


@routes.post("/ai_executor/opencode/stop")
async def oc_stop(request):
    return web.json_response(opencode_bridge.stop())


@routes.post("/ai_executor/opencode/dispatch")
async def oc_dispatch(request):
    body = await request.json()
    requirement = (body.get("requirement") or "").strip()
    if not requirement:
        return web.json_response({"ok": False, "error": "requirement required"}, status=400)
    host = request.host
    result = await opencode_bridge.dispatch(
        requirement=requirement,
        api_base=f"http://{host}/ai_executor",
        images=body.get("images"),
    )
    return web.json_response(result)


@routes.get("/ai_executor/opencode/messages/{session_id}")
async def oc_messages(request):
    return web.json_response(await opencode_bridge.messages(request.match_info["session_id"]))


@routes.get("/ai_executor/opencode/sessions_status")
async def oc_sessions_status(request):
    return web.json_response(await opencode_bridge.session_status())


@routes.post("/ai_executor/opencode/abort/{session_id}")
async def oc_abort(request):
    return web.json_response(await opencode_bridge.abort(request.match_info["session_id"]))


@routes.post("/ai_executor/llm/models")
async def llm_models(request):
    body = await request.json()
    base = (body.get("base") or "").strip().rstrip("/")
    key = (body.get("api_key") or "").strip()
    proto = (body.get("proto") or "openai").strip()
    if not key:
        key = ((_load_config().get("llm") or {}).get("api_key") or "").strip()
    if not base or not key:
        return web.json_response({"ok": False, "error": "base and api_key required"}, status=400)
    headers = {"Authorization": f"Bearer {key}"}
    if proto == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    px = proxy.get_proxy()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(base + "/models", headers=headers, proxy=px) as r:
                text = await r.text()
                if (r.status in (401, 403)) and proto == "anthropic":
                    async with s.get(base + "/models", headers={"Authorization": f"Bearer {key}", "anthropic-version": "2023-06-01"}, proxy=px) as r2:
                        text = await r2.text()
                        return _parse_models_response(r2.status, text)
                return _parse_models_response(r.status, text)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


def _parse_models_response(status, text):
    if status != 200:
        return web.json_response({"ok": False, "error": f"HTTP {status}: {text[:300]}"})
    try:
        data = json.loads(text)
    except Exception:
        return web.json_response({"ok": False, "error": "response is not JSON"})
    ids = sorted(m.get("id") for m in (data.get("data") or []) if m.get("id"))
    return web.json_response({"ok": True, "models": ids})


@routes.post("/ai_executor/candidates/present")
async def candidates_present(request):
    body = await request.json()
    items = body.get("candidates")
    if not items:
        return web.json_response({"error": "candidates required"}, status=400)
    result = candidates.present(items)
    return web.json_response(result)


@routes.get("/ai_executor/candidates/pending")
async def candidates_pending(request):
    return web.json_response({"batches": candidates.pending_batches()})


@routes.post("/ai_executor/candidates/choose")
async def candidates_choose(request):
    body = await request.json()
    chosen = candidates.choose(body.get("batch_id", ""), int(body.get("index", -1)))
    if not chosen:
        return web.json_response({"ok": False, "error": "invalid batch or index"}, status=404)
    session_id = body.get("session_id")
    if session_id:
        try:
            await opencode_bridge._post(f"/session/{session_id}/prompt_async", {"parts": [{"type": "text",
                "text": f"用户已在面板中选择了候选 #{chosen['index']}: 《{chosen['title']}》。请继续阶段4: 拉取该工作流,转换为UI格式,调用 /workflows/save 保存,然后处理依赖。"}]})
        except Exception:
            pass
    return web.json_response({"ok": True, "chosen": chosen})


@routes.get("/ai_executor/candidates/batch/{batch_id}")
async def candidates_batch(request):
    b = candidates.get_batch(request.match_info["batch_id"])
    if not b:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({k: v for k, v in b.items() if k != "token"})


@routes.get("/ai_executor/samples/{name}")
async def samples_serve(request):
    p = candidates.get_sample_path(request.match_info["name"])
    if not p:
        return web.json_response({"error": "not found"}, status=404)
    return web.FileResponse(p)


@routes.post("/ai_executor/workflows/save")
async def workflows_save(request):
    body = await request.json()
    batch_id = body.get("batch_id", "")
    token = body.get("token", "")
    if not candidates.check_token(batch_id, token):
        return web.json_response({"ok": False, "error": "invalid token or no user selection yet"}, status=403)
    wf = body.get("workflow")
    if not isinstance(wf, dict) or "nodes" not in wf:
        return web.json_response({"ok": False, "error": "workflow must be UI format (with nodes/links)"}, status=400)
    filename = os.path.basename(body.get("filename") or "ai_executor_workflow.json")
    if not filename.endswith(".json"):
        filename += ".json"
    port = _comfy_port()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.post(f"http://127.0.0.1:{port}/userdata/workflows/{filename}",
                          json=wf, headers={"Content-Type": "application/json"}) as r:
            if r.status not in (200, 201):
                return web.json_response({"ok": False, "error": f"userdata save failed: HTTP {r.status}"}, status=502)
    candidates.set_workflow(batch_id, wf)
    return web.json_response({"ok": True, "filename": f"workflows/{filename}"})


def _comfy_port():
    try:
        from comfy.cli_args import args as comfy_args
        return getattr(comfy_args, "port", 8188)
    except Exception:
        return 8188


@routes.get("/ai_executor/workflows/load/{batch_id}")
async def workflows_load(request):
    b = candidates.get_batch(request.match_info["batch_id"])
    if not b or not b.get("workflow"):
        return web.json_response({"error": "workflow not saved yet"}, status=404)
    return web.json_response({"workflow": b["workflow"], "chosen": b["chosen"]})


@routes.get("/ai_executor/opencode/onboarding")
async def oc_onboarding(request):
    return web.json_response(await opencode_bridge.onboarding())


@routes.post("/ai_executor/opencode/install")
async def oc_install(request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    dest = (body.get("dir") or "").strip()
    if dest:
        job = opencode_bridge.install_binary_job(
            dest,
            timeout_sec=int(body.get("timeout_sec", 120)),
            auto_retry=bool(body.get("auto_retry", True)),
            retry_max=int(body.get("retry_max", 3)),
        )
    else:
        job = opencode_bridge.install_opencode_job()
    return web.json_response({"job_id": job["id"]})


@routes.post("/ai_executor/opencode/uninstall")
async def oc_uninstall(request):
    return web.json_response(opencode_bridge.uninstall())


@routes.get("/ai_executor/opencode/browse")
async def oc_browse(request):
    return web.json_response(opencode_bridge.browse_dirs(request.query.get("path", "")))


@routes.get("/ai_executor/opencode/default_install_dir")
async def oc_default_dir(request):
    return web.json_response({"dir": os.path.join(opencode_bridge.PLUGIN_DIR, "bin")})


@routes.get("/ai_executor/opencode/providers")
async def oc_providers(request):
    return web.json_response(await opencode_bridge.providers())


@routes.post("/ai_executor/opencode/auth")
async def oc_auth(request):
    body = await request.json()
    pid = (body.get("provider") or "").strip()
    key = (body.get("api_key") or "").strip()
    if not pid or not key:
        return web.json_response({"ok": False, "error": "provider and api_key required"}, status=400)
    result = await opencode_bridge.set_auth(pid, key)
    model = (body.get("model") or "").strip()
    if result.get("ok") and model:
        result["model_set"] = await opencode_bridge.set_default_model(f"{pid}/{model}")
    return web.json_response(result)


RESTART_PENDING = {}
RESUME_PATH = os.path.join(PLUGIN_DIR, "cache", "pending_resume.json")


@routes.post("/ai_executor/system/restart_request")
async def restart_request(request):
    body = await request.json()
    if not candidates.check_token(body.get("batch_id", ""), body.get("token", "")):
        return web.json_response({"ok": False, "error": "invalid token"}, status=403)
    RESTART_PENDING.update({
        "reason": body.get("reason", "安装的新节点需要重启 ComfyUI 生效"),
        "session_id": body.get("session_id"),
        "batch_id": body.get("batch_id"),
    })
    return web.json_response({"ok": True})


@routes.get("/ai_executor/system/restart_pending")
async def restart_pending(request):
    return web.json_response({"pending": RESTART_PENDING or None})


@routes.post("/ai_executor/system/restart")
async def restart_comfy(request):
    if not RESTART_PENDING:
        return web.json_response({"ok": False, "error": "no pending restart"}, status=400)
    sup = opencode_bridge.supervisor.find_supervisor()
    if not sup:
        return web.json_response({"ok": False, "error": "supervisor unavailable"}, status=503)
    os.makedirs(os.path.dirname(RESUME_PATH), exist_ok=True)
    with open(RESUME_PATH, "w", encoding="utf-8") as f:
        json.dump({"session_id": RESTART_PENDING.get("session_id")}, f)
    RESTART_PENDING.clear()

    def work():
        r = opencode_bridge.supervisor.restart_comfy(sup)
        if not r.get("ok"):
            try:
                os.remove(RESUME_PATH)
            except OSError:
                pass

    threading.Thread(target=work, daemon=True).start()
    return web.json_response({"ok": True, "started": True})


def _register_with_supervisor():
    sup = opencode_bridge.supervisor.ensure_running()
    if not sup:
        return
    main_py = os.path.abspath(sys.argv[0])
    comfy_dir = os.path.dirname(main_py)
    try:
        opencode_bridge.supervisor.record_comfy(sup, {
            "pid": os.getpid(),
            "cmdline": [sys.executable, main_py] + sys.argv[1:],
            "cwd": comfy_dir,
            "env": dict(os.environ),
            "port": _comfy_port(),
        })
    except Exception:
        pass


async def _resume_if_pending():
    if not os.path.exists(RESUME_PATH):
        return
    try:
        with open(RESUME_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        session_id = data.get("session_id")
        if session_id and await opencode_bridge.health():
            await opencode_bridge._post(f"/session/{session_id}/prompt_async", {"parts": [{"type": "text",
                "text": "ComfyUI 已重启完成,插件 API 恢复可用。请继续之前的任务(依赖已装好,可从 /deps/check 重新确认)。"}]})
        os.remove(RESUME_PATH)
    except Exception:
        pass


def setup():
    server = PromptServer.instance
    server.app.add_routes(routes)
    threading.Thread(target=_register_with_supervisor, daemon=True).start()
    try:
        loop = asyncio.get_event_loop()
        loop.call_later(5, lambda: asyncio.ensure_future(_resume_if_pending()))
    except Exception:
        pass


try:
    setup()
except Exception:
    pass
