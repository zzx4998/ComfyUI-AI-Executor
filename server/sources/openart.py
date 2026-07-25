import json
import re

import aiohttp

from ..http_utils import DEFAULT_HEADERS, normalize_result

BASE = "https://openart.ai"


async def search(query, limit=20, page=1):
    url = f"{BASE}/workflows?search={query}"
    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            html = await resp.text()
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    props = (data.get("props") or {}).get("pageProps") or {}
    items = props.get("workflows") or props.get("initialWorkflows") or []
    results = []
    for item in items[:limit]:
        wid = item.get("id") or item.get("slug")
        samples = []
        cover = item.get("coverImage") or item.get("cover_image") or item.get("image")
        if cover:
            samples.append({"type": "image", "url": cover, "nsfw": False})
        results.append(normalize_result(
            source="openart",
            external_id=wid,
            title=item.get("title") or item.get("name"),
            url=f"{BASE}/workflows/{wid}",
            author=(item.get("user") or {}).get("name", "") if isinstance(item.get("user"), dict) else "",
            published_at=item.get("createdAt") or item.get("created_at"),
            base_model=item.get("baseModel") or item.get("model"),
            samples=samples,
            tags=item.get("tags") or [],
            stats={"likes": item.get("likeCount") or item.get("likes")},
        ))
    return results


async def get_workflow(result):
    wid = result.get("id")
    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        async with session.get(f"{BASE}/workflows/{wid}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            html = await resp.text()
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    data = json.loads(m.group(1))
    props = (data.get("props") or {}).get("pageProps") or {}
    wf = props.get("workflow") or {}
    payload = wf.get("workflow") or wf.get("json") or wf.get("workflowJson")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    return payload
