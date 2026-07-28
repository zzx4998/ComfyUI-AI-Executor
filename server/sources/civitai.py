from ..http_utils import fetch_json, normalize_result

API = "https://civitai.com/api/v1"


async def search(query, limit=20, page=1):
    params = {
        "query": query,
        "tag": "comfyui workflow",
        "limit": str(limit),
        "page": str(page),
        "nsfw": "false",
    }
    try:
        data = await fetch_json(f"{API}/models", params=params)
    except Exception:
        params.pop("tag", None)
        data = await fetch_json(f"{API}/models", params=params)
    results = []
    for item in data.get("items", []):
        versions = item.get("modelVersions") or []
        ver = versions[0] if versions else {}
        samples = []
        for img in (ver.get("images") or [])[:6]:
            samples.append({
                "type": "video" if img.get("type") == "video" else "image",
                "url": img.get("url"),
                "nsfw": img.get("nsfwLevel", 0) > 1,
            })
        workflow_url = None
        for f in (ver.get("files") or []):
            name = (f.get("name") or "").lower()
            if name.endswith(".json"):
                workflow_url = f.get("downloadUrl")
                break
        results.append(normalize_result(
            source="civitai",
            external_id=f"{item.get('id')}-{ver.get('id')}",
            title=item.get("name"),
            url=f"https://civitai.com/models/{item.get('id')}?modelVersionId={ver.get('id')}",
            author=(item.get("creator") or {}).get("username", ""),
            published_at=ver.get("publishedAt") or ver.get("createdAt"),
            base_model=ver.get("baseModel"),
            samples=samples,
            tags=item.get("tags") or [],
            workflow_url=workflow_url,
            stats={
                "downloads": (item.get("stats") or {}).get("downloadCount"),
                "thumbs": (item.get("stats") or {}).get("thumbsUpCount"),
            },
            extra={"model_id": item.get("id"), "version_id": ver.get("id")},
        ))
    return results


async def get_workflow(result):
    url = result.get("workflow_url")
    ver_id = (result.get("extra") or {}).get("version_id")
    ver = None
    if not url and ver_id:
        ver = await fetch_json(f"{API}/model-versions/{ver_id}")
        for f in (ver.get("files") or []):
            if (f.get("name") or "").lower().endswith(".json"):
                url = f.get("downloadUrl")
                break
    if url:
        try:
            return await fetch_json(url)
        except Exception:
            pass
    if ver is None and ver_id:
        try:
            ver = await fetch_json(f"{API}/model-versions/{ver_id}")
        except Exception:
            return None
    for img in (ver.get("images") or []) if ver else []:
        meta = img.get("meta") or {}
        wf = meta.get("workflow")
        if isinstance(wf, dict) and "nodes" in wf:
            return wf
    for img in (ver.get("images") or []) if ver else []:
        meta = img.get("meta") or {}
        wf = meta.get("workflow") or meta.get("prompt")
        if isinstance(wf, str):
            import json
            try:
                wf = json.loads(wf)
            except Exception:
                continue
        if isinstance(wf, dict) and (("nodes" in wf) or any(isinstance(v, dict) and "class_type" in v for v in wf.values())):
            return wf
    return None
