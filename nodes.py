import asyncio
import time

from comfy.cli_args import args

from .server import opencode_bridge

API_BASE = f"http://127.0.0.1:{getattr(args, 'port', 8188)}/ai_executor"


def _collect_final_text(session_id):
    msgs = asyncio.run(opencode_bridge.messages(session_id))
    if not isinstance(msgs, list):
        return ""
    for m in reversed(msgs):
        if (m.get("info") or {}).get("role") != "assistant":
            continue
        texts = [p.get("text", "") for p in (m.get("parts") or []) if p.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return ""


class AIExecutorAgent:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "requirement": ("STRING", {"multiline": True, "default": ""}),
            "timeout_sec": ("INT", {"default": 1800, "min": 60, "max": 7200, "step": 60}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("summary",)
    FUNCTION = "execute"
    CATEGORY = "AIExecutor"
    DESCRIPTION = "Dispatch the requirement to the local opencode agent; it searches workflows, installs dependencies and runs them in ComfyUI. Returns the agent's final summary."

    def execute(self, requirement, timeout_sec):
        if not requirement.strip():
            return ("",)
        health = asyncio.run(opencode_bridge.health())
        if not health:
            started = opencode_bridge.start()
            if not started.get("ok"):
                return (f"[AIExecutor] opencode unavailable: {started.get('error')}",)
            for _ in range(30):
                if asyncio.run(opencode_bridge.health()):
                    break
                time.sleep(0.5)
        result = asyncio.run(opencode_bridge.dispatch(
            requirement=requirement,
            api_base=API_BASE,
        ))
        if not result.get("ok"):
            return (f"[AIExecutor] dispatch failed: {result.get('error')}",)
        sid = result["session_id"]
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            time.sleep(5)
            try:
                statuses = asyncio.run(opencode_bridge.session_status())
                st = (statuses or {}).get(sid) or {}
                if st.get("type") == "idle":
                    break
            except Exception:
                pass
        text = _collect_final_text(sid)
        return (text or f"[AIExecutor] session {sid} finished without summary",)


NODE_CLASS_MAPPINGS = {"AIExecutorAgent": AIExecutorAgent}
NODE_DISPLAY_NAME_MAPPINGS = {"AIExecutorAgent": "AI Executor Agent (opencode)"}
