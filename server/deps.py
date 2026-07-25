import os
import re

import folder_paths
import nodes

MODEL_EXTS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf",
              ".onnx", ".sft", ".pkl", ".tflite", ".engine")


def normalize_workflow(wf):
    if not isinstance(wf, dict):
        return None
    if "nodes" in wf and isinstance(wf["nodes"], list):
        return {"__ui_format__": True, "wf": wf}
    for k, v in wf.items():
        if isinstance(v, dict) and "class_type" in v:
            return wf
    return None


def ui_to_api(wf):
    api = {}
    for node in wf.get("nodes", []):
        nid = str(node.get("id"))
        class_type = node.get("type")
        if not class_type:
            continue
        inputs = {}
        widgets = node.get("widgets_values") or []
        inputs["__widgets__"] = widgets
        for inp in node.get("inputs", []) or []:
            if inp.get("link") is not None:
                inputs[inp["name"]] = [str(inp["link"]), 0]
        api[nid] = {"class_type": class_type, "inputs": inputs}
    return api


def get_class_types(wf):
    api = normalize_workflow(wf)
    if api is None:
        return set()
    if isinstance(api, dict) and api.get("__ui_format__"):
        api = ui_to_api(api["wf"])
    return {v["class_type"] for v in api.values() if isinstance(v, dict) and "class_type" in v}


def check_nodes(wf):
    wanted = get_class_types(wf)
    registered = set(nodes.NODE_CLASS_MAPPINGS.keys())
    missing = sorted(wanted - registered)
    return {"required": sorted(wanted), "missing": missing}


def _all_model_files():
    found = {}
    for folder in folder_paths.folder_names_and_paths.keys():
        try:
            for name in folder_paths.get_filename_list(folder):
                found.setdefault(os.path.basename(name).lower(), []).append(f"{folder}/{name}")
        except Exception:
            continue
    return found


def extract_model_refs(wf):
    api = normalize_workflow(wf)
    if api is None:
        return []
    if isinstance(api, dict) and api.get("__ui_format__"):
        api = ui_to_api(api["wf"])
    refs = []
    for nid, node in api.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        for key, val in inputs.items():
            vals = val if isinstance(val, list) and key == "__widgets__" else [val]
            for v in vals:
                if isinstance(v, str) and v.lower().endswith(MODEL_EXTS):
                    refs.append({"node": nid, "class_type": node.get("class_type"),
                                 "field": key, "filename": v})
    seen = set()
    out = []
    for r in refs:
        k = r["filename"].lower()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def check_models(wf):
    refs = extract_model_refs(wf)
    have = _all_model_files()
    missing = []
    present = []
    for r in refs:
        base = os.path.basename(r["filename"]).lower()
        if base in have:
            present.append({**r, "found_at": have[base][0]})
        else:
            missing.append(r)
    return {"required": refs, "present": present, "missing": missing}


def full_check(wf):
    return {"nodes": check_nodes(wf), "models": check_models(wf)}
