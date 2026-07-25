import asyncio
import base64
import json
import os

from aiohttp import web
from server import PromptServer

from . import deps, installer, local_index, runner
from .sources import civitai, comfyworkflows, github_collections, openart

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PLUGIN_DIR, "config.json")

SOURCES = {
    "civitai": civitai,
    "comfyworkflows": comfyworkflows,
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
    if safe.get("llm", {}).get("api_key"):
        safe["llm"]["api_key"] = "***"
    return web.json_response(safe)


@routes.post("/ai_executor/settings")
async def set_settings(request):
    body = await request.json()
    cfg = _load_config()
    if "llm" in body:
        llm = body["llm"] or {}
        if llm.get("api_key") == "***":
            llm["api_key"] = (cfg.get("llm") or {}).get("api_key", "")
        cfg["llm"] = llm
    for k in ("hf_mirror", "github_token", "github_repos"):
        if k in body:
            cfg[k] = body[k]
    _save_config(cfg)
    return web.json_response({"ok": True})


@routes.get("/ai_executor/search")
async def search(request):
    query = request.query.get("query", "")
    sources = [s for s in request.query.get("sources", "local,civitai,comfyworkflows,openart,github").split(",") if s]
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


def setup():
    server = PromptServer.instance
    server.app.add_routes(routes)


try:
    setup()
except Exception:
    pass
