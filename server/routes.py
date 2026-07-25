import asyncio
import base64
import json
import os

import aiohttp
from aiohttp import web
from server import PromptServer

from . import analyzer, deps, installer, local_index, opencode_bridge, proxy, runner
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


def setup():
    server = PromptServer.instance
    server.app.add_routes(routes)


try:
    setup()
except Exception:
    pass
