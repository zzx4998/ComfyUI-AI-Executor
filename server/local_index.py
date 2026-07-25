import json
import os

import folder_paths

from . import deps

COMFY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

SEARCH_DIRS = [
    os.path.join(COMFY_DIR, "my_workflows"),
    os.path.join(COMFY_DIR, "user", "default", "workflows"),
]


def scan_local_workflows():
    out = []
    for d in SEARCH_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for name in files:
                if not name.lower().endswith(".json"):
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        wf = json.load(f)
                except Exception:
                    continue
                class_types = deps.get_class_types(wf)
                if not class_types:
                    continue
                models = [r["filename"] for r in deps.extract_model_refs(wf)]
                out.append({
                    "source": "local",
                    "id": path,
                    "title": name,
                    "path": path,
                    "published_at": None,
                    "base_model": None,
                    "samples": [],
                    "tags": [],
                    "node_count": len(class_types),
                    "models": models,
                })
    return out


def search(query, limit=50):
    q = (query or "").lower()
    results = []
    for item in scan_local_workflows():
        hay = (item["title"] + " " + " ".join(item["models"])).lower()
        if q and q not in hay:
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def load_workflow(path):
    path = os.path.normpath(path)
    allowed = any(path.startswith(os.path.normpath(d)) for d in SEARCH_DIRS if os.path.isdir(d))
    if not allowed:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
