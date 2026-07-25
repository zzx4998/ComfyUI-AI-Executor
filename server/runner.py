import copy
import os
import random
import uuid

import execution
import folder_paths
from server import PromptServer


def inject_params(workflow, params):
    wf = copy.deepcopy(workflow)
    applied = []
    for nid, fields in (params or {}).items():
        nid = str(nid)
        if nid not in wf or not isinstance(wf[nid], dict):
            continue
        node = wf[nid]
        inputs = node.setdefault("inputs", {})
        for field, value in (fields or {}).items():
            if field in inputs or field == "widgets_values":
                inputs[field] = value
                applied.append({"node": nid, "field": field})
            elif field == "__widgets__":
                inputs["__widgets__"] = value
                applied.append({"node": nid, "field": field})
            else:
                inputs[field] = value
                applied.append({"node": nid, "field": field, "created": True})
    return wf, applied


def randomize_seeds(workflow):
    wf = workflow
    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        for key in list(inputs.keys()):
            if key.lower() in ("seed", "noise_seed") and isinstance(inputs[key], (int, float)):
                inputs[key] = random.randint(0, 2**63 - 1)
    return wf


def save_input_image(filename, data):
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    safe = os.path.basename(filename)
    dest = os.path.join(input_dir, safe)
    with open(dest, "wb") as f:
        f.write(data)
    return safe


def queue_prompt(workflow, extra_data=None):
    server = PromptServer.instance
    valid = execution.validate_prompt(workflow)
    if not valid[0]:
        return {"ok": False, "error": "validate_prompt failed", "detail": valid[1], "node_errors": valid[3] if len(valid) > 3 else None}
    prompt_id = uuid.uuid4().hex
    number = server.number
    server.number += 1
    extra_data = extra_data or {}
    outputs = valid[2]
    server.prompt_queue.put((number, prompt_id, workflow, extra_data, outputs))
    return {"ok": True, "prompt_id": prompt_id, "number": number}


def run_status(prompt_id):
    server = PromptServer.instance
    history = server.prompt_queue.get_history(prompt_id=prompt_id)
    if prompt_id not in history:
        running = any(x[1] == prompt_id for x in server.prompt_queue.currently_running.values())
        queued = any(x[1] == prompt_id for x in server.prompt_queue.queue)
        return {"status": "running" if running else ("queued" if queued else "unknown")}
    entry = history[prompt_id]
    outputs = []
    for nid, out in (entry.get("outputs") or {}).items():
        for key in ("images", "gifs", "videos"):
            for f in out.get(key, []) or []:
                outputs.append({
                    "node": nid,
                    "filename": f.get("filename"),
                    "subfolder": f.get("subfolder", ""),
                    "type": f.get("type", "output"),
                    "view_url": f"/view?filename={f.get('filename')}&subfolder={f.get('subfolder', '')}&type={f.get('type', 'output')}",
                })
    status = entry.get("status") or {}
    return {
        "status": "done" if status.get("completed") else ("error" if status.get("status_str") == "error" else "running"),
        "messages": status.get("messages", []),
        "outputs": outputs,
    }
