from .deps import normalize_workflow, ui_to_api

TASK_SIGNATURES = [
    ("video_generate", ["WanImageToVideo", "SVD_img2vid", "HunyuanVideo", "MochiLoader", "LTXVLoader", "FramePack"]),
    ("video_io", ["VHS_LoadVideo", "VHS_VideoCombine"]),
    ("image_upscale", ["ImageUpscaleWithModel", "UltimateSDUpscale", "SeedVR2"]),
    ("face_detail", ["FaceDetailer", "DetailerForEach", "ReActorFaceSwap", "PulidFlux"]),
    ("inpaint", ["InpaintCropAndStitch", "SetLatentNoiseMask", "VAEEncodeForInpaint"]),
    ("outpaint", ["ImagePadForOutpaint", "FooocusInpaint"]),
    ("controlnet_guided", ["ControlNetApply", "ControlNetApplyAdvanced", "ACN_AdvancedControlNetApply"]),
    ("ipadapter_style", ["IPAdapterAdvanced", "IPAdapterApply", "IPAdapterUnifiedLoader"]),
    ("background_remove", ["RemBG", "BiRefNet", "RMBG"]),
    ("segmentation", ["SAMModelLoader", "GroundingDino", "Florence2ModelLoader"]),
    ("img2img", ["VAEEncode"]),
    ("text2img", ["EmptyLatentImage", "EmptySD3LatentImage"]),
    ("llm_assist", ["OllamaGenerate", "QwenVL", "PromptAssistant"]),
]

IMAGE_INPUT_NODES = {"LoadImage", "LoadImageMask", "LoadImageOutput", "VHS_LoadImagePath", "VHS_LoadVideo", "VHS_LoadVideoPath"}
TEXT_PROMPT_NODES = {"CLIPTextEncode", "CLIPTextEncodeSDXL", "CLIPTextEncodeFlux", "BNK_CLIPTextEncodeAdvanced", "smZ CLIPTextEncode"}
OUTPUT_NODES = {"SaveImage", "PreviewImage", "VHS_VideoCombine", "SaveAnimatedWEBP", "SaveAnimatedPNG", "VHS_SaveImage"}
LATENT_SIZE_NODES = {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyMochiLatentVideo", "EmptyHunyuanLatentVideo"}
MODEL_LOADER_NODES = {"CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader", "DiffusionModelLoader", "LoraLoader", "LoraLoaderModelOnly", "VAELoader", "ControlNetLoader", "UpscaleModelLoader", "CLIPLoader", "DualCLIPLoader", "TripleCLIPLoader"}


def _api_dict(wf):
    api = normalize_workflow(wf)
    if api is None:
        return None
    if isinstance(api, dict) and api.get("__ui_format__"):
        pseudo = {}
        for node in api["wf"].get("nodes", []):
            nid = str(node.get("id"))
            ctype = node.get("type")
            if not ctype:
                continue
            pseudo[nid] = {"class_type": ctype,
                           "inputs": {"__widgets__": node.get("widgets_values") or []}}
        return pseudo
    return api


def classify(wf):
    api = _api_dict(wf)
    if api is None:
        return {"error": "workflow must be API format (id -> {class_type, inputs}); convert UI format first"}
    types = {nid: n.get("class_type", "") for nid, n in api.items() if isinstance(n, dict)}
    type_set = set(types.values())

    tasks = []
    for task, keys in TASK_SIGNATURES:
        if any(any(k.lower() in t.lower() for t in type_set) for k in keys):
            tasks.append(task)

    image_inputs = []
    text_slots = []
    seed_slots = []
    size_slots = []
    outputs = []
    loaders = []
    for nid, ctype in types.items():
        inputs = api[nid].get("inputs", {})
        widgets = inputs.get("__widgets__") or []
        if ctype in IMAGE_INPUT_NODES:
            image_inputs.append({"node": nid, "class_type": ctype, "field": "image" if "image" in inputs else next(iter(inputs), None)})
        if ctype in TEXT_PROMPT_NODES:
            cur = inputs.get("text", "")
            if not isinstance(cur, str) or not cur:
                cur = next((w for w in widgets if isinstance(w, str) and w.strip()), "")
            text_slots.append({"node": nid, "class_type": ctype, "field": "text", "current": cur})
        for k, v in inputs.items():
            if isinstance(v, (int, float)) and k.lower() in ("seed", "noise_seed"):
                seed_slots.append({"node": nid, "field": k})
            if ctype in LATENT_SIZE_NODES and k in ("width", "height") and isinstance(v, (int, float)):
                size_slots.append({"node": nid, "field": k, "current": v})
        if widgets:
            for w in widgets:
                if isinstance(w, int) and w > 10000:
                    seed_slots.append({"node": nid, "field": "widgets(guess)", "current": w})
                    break
            if ctype in LATENT_SIZE_NODES:
                nums = [w for w in widgets if isinstance(w, (int, float)) and 16 <= w <= 8192]
                for i, name in enumerate(("width", "height")):
                    if i < len(nums):
                        size_slots.append({"node": nid, "field": name + "(widgets)", "current": nums[i]})
        if ctype in OUTPUT_NODES:
            outputs.append({"node": nid, "class_type": ctype})
        if ctype in MODEL_LOADER_NODES:
            for k, v in inputs.items():
                if isinstance(v, str) and v.lower().endswith((".safetensors", ".ckpt", ".gguf", ".pt", ".pth")):
                    loaders.append({"node": nid, "class_type": ctype, "field": k, "model": v})

    return {
        "tasks": tasks,
        "node_count": len(types),
        "class_types": sorted(type_set),
        "image_inputs": image_inputs,
        "text_slots": text_slots,
        "seed_slots": seed_slots,
        "size_slots": size_slots,
        "outputs": outputs,
        "model_loaders": loaders,
    }
