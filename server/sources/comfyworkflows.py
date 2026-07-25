import re

from ..http_utils import fetch_json, normalize_result

API = "https://comfyworkflows.com/api"


async def search(query, limit=20, page=1):
    data = await fetch_json(f"{API}/workflows", params={
        "search": query,
        "limit": str(limit),
        "page": str(page),
    })
    items = data.get("workflows") or data.get("items") or data.get("data") or []
    results = []
    for item in items[:limit]:
        slug = item.get("slug") or item.get("id")
        samples = []
        thumb = item.get("thumbnail") or item.get("image") or item.get("coverImage")
        if thumb:
            samples.append({"type": "image", "url": thumb, "nsfw": False})
        results.append(normalize_result(
            source="comfyworkflows",
            external_id=slug,
            title=item.get("title") or item.get("name"),
            url=f"https://comfyworkflows.com/workflows/{slug}",
            author=(item.get("user") or {}).get("username", "") if isinstance(item.get("user"), dict) else item.get("author", ""),
            published_at=item.get("createdAt") or item.get("created_at") or item.get("publishedAt"),
            base_model=item.get("baseModel") or item.get("base_model"),
            samples=samples,
            tags=item.get("tags") or [],
            stats={"views": item.get("viewCount") or item.get("views"),
                   "likes": item.get("likeCount") or item.get("likes")},
            extra={"raw_keys": list(item.keys())[:20]},
        ))
    return results


async def get_workflow(result):
    wid = result.get("id")
    data = await fetch_json(f"{API}/workflows/{wid}")
    wf = data.get("workflow") or data.get("json") or data.get("workflowJson")
    if isinstance(wf, str):
        import json
        try:
            wf = json.loads(wf)
        except Exception:
            return None
    return wf
