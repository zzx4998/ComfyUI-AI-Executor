from ..http_utils import fetch_json, normalize_result

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

DEFAULT_REPOS = [
    "comfyanonymous/ComfyUI_examples",
    "younik/comfyui-workflows",
    "wyrde/wyrde-comfyui-workflows",
]

GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def _list_repo_jsons(repo, token=None):
    headers = dict(GH_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = await fetch_json(f"{API}/repos/{repo}/git/trees/HEAD?recursive=1", headers=headers)
    out = []
    for node in data.get("tree", []):
        path = node.get("path", "")
        if node.get("type") == "blob" and path.lower().endswith(".json"):
            out.append(path)
    return out


async def _last_commit_date(repo, path, token=None):
    headers = dict(GH_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        data = await fetch_json(f"{API}/repos/{repo}/commits", params={"path": path, "per_page": "1"}, headers=headers)
        if data:
            return data[0]["commit"]["committer"]["date"]
    except Exception:
        return None
    return None


async def search(query, limit=20, page=1, repos=None, token=None):
    repos = repos or DEFAULT_REPOS
    q = (query or "").lower()
    results = []
    for repo in repos:
        try:
            paths = await _list_repo_jsons(repo, token)
        except Exception:
            continue
        for path in paths:
            if q and q not in path.lower():
                continue
            results.append(normalize_result(
                source="github",
                external_id=f"{repo}:{path}",
                title=path.rsplit("/", 1)[-1],
                url=f"https://github.com/{repo}/blob/HEAD/{path}",
                author=repo.split("/")[0],
                published_at=None,
                workflow_url=f"{RAW}/{repo}/HEAD/{path}",
                tags=[repo.split("/")[-1]],
                extra={"repo": repo, "path": path},
            ))
            if len(results) >= limit:
                return results
    return results


async def get_workflow(result):
    url = result.get("workflow_url")
    if not url:
        return None
    try:
        return await fetch_json(url)
    except Exception:
        return None
