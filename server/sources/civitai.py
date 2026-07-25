from ..http_utils import fetch_json, normalize_result

API = "https://civitai.com/api/v1"


async def search(query, limit=20, page=1):
    data = await fetch_json(f"{API}/models", params={
        "query": query,
        "tag": "comfyui workflow",
        "limit": str(limit),
        "page": str(page),
        "nsfw": "false",
    })
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
    if not url:
        ver_id = (result.get("extra") or {}).get("version_id")
        if not ver_id:
            return None
        data = await fetch_json(f"{API}/model-versions/{ver_id}")
        for f in (data.get("files") or []):
            if (f.get("name") or "").lower().endswith(".json"):
                url = f.get("downloadUrl")
                break
    if not url:
        return None
    return await fetch_json(url)
