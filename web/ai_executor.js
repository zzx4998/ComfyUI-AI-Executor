import { app } from "../../../scripts/app.js";

const API = "/ai_executor";

const state = {
  results: [],
  selected: null,
  workflow: null,
  deps: null,
  jobs: {},
};

const LLM_PRESETS = [
  { name: "选择服务商...", base: "", model: "" },
  { name: "Kimi (月之暗面)", base: "https://api.moonshot.cn/v1", model: "kimi-k2-0905-preview" },
  { name: "DeepSeek", base: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { name: "通义千问 (阿里)", base: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { name: "智谱 GLM", base: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
  { name: "硅基流动 SiliconFlow", base: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen2.5-7B-Instruct" },
  { name: "火山方舟 (字节)", base: "https://ark.cn-beijing.volces.com/api/v3", model: "" },
  { name: "OpenAI", base: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { name: "OpenRouter", base: "https://openrouter.ai/api/v1", model: "" },
  { name: "Groq", base: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile" },
  { name: "Gemini (Google)", base: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.0-flash" },
  { name: "Ollama (本地)", base: "http://127.0.0.1:11434/v1", model: "qwen2.5" },
  { name: "自定义", base: "", model: "" },
];

function helpIcon(tip) {
  const s = el("span", { class: "aie-help", "data-tip": tip }, "?");
  s.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); });
  s.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); });
  return s;
}

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    e.append(c instanceof Node ? c : document.createTextNode(c));
  }
  return e;
}

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  return r.json();
}

async function post(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function fmtDate(s) {
  if (!s) return "-";
  try { return new Date(s).toLocaleDateString(); } catch { return s; }
}

function buildPanel() {
  const root = el("div", { id: "aie-panel", style: `
    position:fixed;top:50px;right:10px;width:420px;max-height:85vh;overflow-y:auto;
    background:#1e1e28;color:#ddd;border:1px solid #444;border-radius:8px;
    z-index:9999;padding:12px;font-size:12px;display:none;box-shadow:0 4px 24px #000a;
  `});

  const title = el("div", { style: "display:flex;justify-content:space-between;margin-bottom:8px;cursor:move;user-select:none;" }, [
    el("b", {}, "AI Executor"),
    el("a", { href: "#", style: "color:#888", onclick: (e) => { e.preventDefault(); root.style.display = "none"; } }, "✕"),
  ]);
  let pdrag = null;
  title.addEventListener("pointerdown", (e) => {
    if (e.target.tagName === "A") return;
    pdrag = { sx: e.clientX, sy: e.clientY, ox: root.offsetLeft, oy: root.offsetTop };
    title.setPointerCapture(e.pointerId);
  });
  title.addEventListener("pointermove", (e) => {
    if (!pdrag) return;
    root.style.left = Math.max(0, Math.min(window.innerWidth - 100, pdrag.ox + e.clientX - pdrag.sx)) + "px";
    root.style.top = Math.max(0, Math.min(window.innerHeight - 60, pdrag.oy + e.clientY - pdrag.sy)) + "px";
    root.style.right = "auto";
  });
  title.addEventListener("pointerup", () => { pdrag = null; });

  const llmBox = el("details", { class: "aie-card" }, [
    el("summary", {}, ["LLM 设置 (OpenAI 兼容 API) ", helpIcon("给「AI 帮我选」用的轻量 LLM。选择服务商会自动填 base_url 和推荐模型;也可以点「连接」用你的 Key 实时拉取该账号可用的模型列表,再从下拉框选择。")]),
    el("select", { id: "aie-llm-preset", class: "aie-input",
      onchange: (e) => {
        const p = LLM_PRESETS[e.target.selectedIndex];
        if (p && p.base) {
          document.getElementById("aie-llm-base").value = p.base;
          const m = document.getElementById("aie-llm-model");
          if (p.model) m.value = p.model;
        }
      } },
      LLM_PRESETS.map(p => el("option", {}, p.name))),
    el("input", { id: "aie-llm-base", class: "aie-input", placeholder: "base_url 如 https://api.moonshot.cn/v1" }),
    el("div", { style: "display:flex;gap:4px;align-items:center;" }, [
      el("input", { id: "aie-llm-key", class: "aie-input", placeholder: "api_key", type: "password", style: "flex:1;margin:4px 0;" }),
      el("button", { class: "aie-btn", onclick: llmConnect }, "连接"),
    ]),
    el("input", { id: "aie-llm-model", class: "aie-input", placeholder: "model 如 kimi-k2 / deepseek-chat", list: "aie-llm-models" }),
    el("datalist", { id: "aie-llm-models" }),
    el("button", { class: "aie-btn", style: "margin:4px 0;", onclick: saveLLMSettings }, "保存设置"),
  ]);

  const reqBox = el("div", { class: "aie-card" }, [
    el("div", { style: "font-weight:600;color:#cfd2e0;" }, ["需求 ", helpIcon("用自然语言描述你要做的事,中文即可。点「搜索工作流」手动挑;点「AI 帮我选」让上面的 LLM 挑;或在下方「AI 代理」区派单给 opencode 全自动执行。")]),
    el("textarea", { id: "aie-req", class: "aie-input", placeholder: "例如: 把这张照片变成吉卜力风格并放大到4K", style: "height:48px;" }),
    el("div", { style: "display:flex;gap:4px;margin-top:4px;" }, [
      el("button", { class: "aie-btn", onclick: () => doSearch() }, "搜索工作流"),
      el("button", { class: "aie-btn", onclick: () => aiPick() }, "AI 帮我选"),
    ]),
  ]);

  const srcRow = el("div", { class: "aie-card", style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center;" },
    [["来源 ", helpIcon("勾选搜索哪些站点: local=本地工作流库; civitai/comfyworkflows/openart/github=在线工作流站。在线站点建议挂代理。")],
     ...["local", "civitai", "comfyworkflows", "openart", "github"].map(s =>
      el("label", { style: "cursor:pointer;" }, [
        el("input", { type: "checkbox", class: "aie-src", value: s, checked: s === "local" || s === "civitai" ? "checked" : null }), " " + s,
      ])
    )]);

  const ocBox = el("details", { class: "aie-card" }, [
    el("summary", {}, ["AI 代理 (opencode) ", helpIcon("全自动模式: opencode 代理读取内置规则手册,自主完成 需求理解→翻译扩充检索→筛选工作流→装缺失节点/模型→参数注入→运行→失败重试。首次使用按下方向导完成安装和配置。也可以把「AI Executor Agent」节点拖到画布里用。")]),
    el("div", { style: "display:flex;gap:4px;align-items:center;margin:4px 0;" }, [
      el("span", { id: "aie-oc-dot", style: "width:8px;height:8px;border-radius:50%;background:#666;display:inline-block;" }),
      el("span", { id: "aie-oc-status", style: "color:#999;flex:1;" }, "未检测"),
      el("button", { class: "aie-btn", onclick: ocStart }, "启动"),
      el("button", { class: "aie-btn", onclick: ocStop }, "停止"),
    ]),
    el("button", { class: "aie-btn aie-btn-primary", style: "width:100%;margin:2px 0;padding:6px;",
      onclick: ocDispatch }, "▶ 派单给 AI 代理执行需求"),
    el("button", { class: "aie-btn", style: "width:100%;margin:2px 0;", onclick: ocAbort }, "中止当前任务"),
    (() => { const d = el("div"); buildOcSetup(d); return d; })(),
  ]);

  const listHead = el("div", { style: "font-weight:600;color:#cfd2e0;margin:2px 0;" }, ["搜索结果 ", helpIcon("点击卡片拉取工作流 JSON 并自动检查依赖。卡片显示: 来源/标题/发布日期/底模/作者/样例图。")]);
  const list = el("div", { id: "aie-results" });
  const detail = el("div", { id: "aie-detail", style: "margin-top:8px;" });
  const log = el("pre", { id: "aie-log", style: "background:#14141d;border:1px solid #2e2e3a;border-radius:6px;padding:6px;max-height:160px;overflow:auto;white-space:pre-wrap;margin-top:8px;" });

  root.append(title, llmBox, reqBox, srcRow, ocBox, listHead, list, detail, log);
  document.body.append(root);

  const styleTag = el("style", {}, `
    #aie-fab {
      position: fixed; z-index: 9999; padding: 0 16px; height: 38px;
      border: none; border-radius: 19px; cursor: grab; touch-action: none;
      font: 600 13px/38px "Segoe UI", sans-serif; letter-spacing: .5px; color: #fff;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      box-shadow: 0 3px 12px rgba(102,126,234,.45), inset 0 1px 0 rgba(255,255,255,.25);
      transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
      user-select: none; white-space: nowrap;
    }
    #aie-fab:hover {
      transform: translateY(-2px) scale(1.05);
      filter: brightness(1.15);
      box-shadow: 0 6px 20px rgba(102,126,234,.6), inset 0 1px 0 rgba(255,255,255,.3);
    }
    #aie-fab:active { transform: scale(.97); filter: brightness(.95); }
    #aie-fab.dragging { cursor: grabbing; transition: none; transform: scale(1.03); filter: brightness(1.05); }
    #aie-panel { background: #1b1b26; border: 1px solid #3d3d55; border-radius: 10px; }
    #aie-panel .aie-card { background: #22222f; border: 1px solid #34343f; border-radius: 8px; padding: 8px; margin-bottom: 8px; }
    #aie-panel summary { cursor: pointer; font-weight: 600; padding: 2px 0; color: #cfd2e0; }
    #aie-panel summary:hover { color: #fff; }
    .aie-input { width: 100%; margin: 4px 0; background: #14141d; color: #ddd; border: 1px solid #3d3d4d;
      padding: 6px 8px; border-radius: 6px; font-size: 12px; box-sizing: border-box; transition: border-color .15s; }
    .aie-input:focus { border-color: #667eea; outline: none; }
    .aie-btn { background: #2b2b3c; color: #ccc; border: 1px solid #46465a; padding: 5px 12px;
      border-radius: 6px; cursor: pointer; font-size: 12px; transition: all .15s; }
    .aie-btn:hover { background: #383850; border-color: #667eea; color: #fff; transform: translateY(-1px); }
    .aie-btn-primary { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; border: none; }
    .aie-btn-primary:hover { filter: brightness(1.2); transform: translateY(-1px); }
    .aie-help { display: inline-flex; align-items: center; justify-content: center; width: 15px; height: 15px;
      border-radius: 50%; background: #3a3a4e; color: #8fa3c8; font-size: 10px; font-weight: 700;
      margin-left: 6px; cursor: help; position: relative; vertical-align: middle; flex: none; }
    .aie-help:hover { background: #667eea; color: #fff; }
    .aie-help:hover::after { content: attr(data-tip); position: absolute; left: 22px; top: -6px;
      background: rgba(10,10,18,.97); border: 1px solid #555; padding: 8px 10px; border-radius: 8px;
      width: 240px; white-space: pre-wrap; z-index: 10001; color: #ddd; font-size: 11px; font-weight: 400;
      line-height: 1.6; box-shadow: 0 4px 16px #000a; pointer-events: none; }
  `);
  document.head.append(styleTag);
  const savedPos = JSON.parse(localStorage.getItem("aie-fab-pos") || "null");
  const fab = el("button", { id: "aie-fab" }, "✦ AI Executor");
  if (savedPos) {
    fab.style.left = savedPos.x + "px";
    fab.style.top = savedPos.y + "px";
  } else {
    fab.style.bottom = "80px";
    fab.style.right = "10px";
  }
  let drag = null;
  fab.addEventListener("pointerdown", (e) => {
    drag = { sx: e.clientX, sy: e.clientY, ox: fab.offsetLeft, oy: fab.offsetTop, moved: false };
    fab.setPointerCapture(e.pointerId);
  });
  fab.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (drag.moved) {
      fab.classList.add("dragging");
      fab.style.left = Math.max(0, Math.min(window.innerWidth - fab.offsetWidth, drag.ox + dx)) + "px";
      fab.style.top = Math.max(0, Math.min(window.innerHeight - fab.offsetHeight, drag.oy + dy)) + "px";
      fab.style.right = "auto";
      fab.style.bottom = "auto";
    }
  });
  fab.addEventListener("pointerup", (e) => {
    fab.classList.remove("dragging");
    if (!drag) return;
    if (drag.moved) {
      localStorage.setItem("aie-fab-pos", JSON.stringify({ x: fab.offsetLeft, y: fab.offsetTop }));
    } else {
      togglePanel(root, fab);
    }
    drag = null;
  });
  document.body.append(fab);

  loadLLMSettings();
}

function togglePanel(root, fab) {
  if (root.style.display !== "none") { root.style.display = "none"; return; }
  openPanel(root, fab);
}

function openPanel(root, fab) {
  root.style.display = "block";
  const r = (fab || document.getElementById("aie-fab")).getBoundingClientRect();
  const pw = root.offsetWidth || 420;
  const ph = root.offsetHeight || 500;
  let x = Math.max(10, Math.min(r.right - pw, window.innerWidth - pw - 10));
  let y = r.bottom + 10;
  if (y + ph > window.innerHeight - 10) y = Math.max(10, r.top - ph - 10);
  root.style.left = x + "px";
  root.style.top = y + "px";
  root.style.right = "auto";
}

function openDirPicker(targetInput) {
  const overlay = el("div", { style: "position:fixed;inset:0;background:#000a;z-index:10002;display:flex;align-items:center;justify-content:center;" });
  const box = el("div", { style: "width:420px;max-height:60vh;background:#1b1b26;border:1px solid #3d3d55;border-radius:10px;padding:12px;color:#ddd;font-size:12px;display:flex;flex-direction:column;" });
  const pathLine = el("div", { style: "color:#9ab;margin-bottom:6px;word-break:break-all;" });
  const listBox = el("div", { style: "flex:1;overflow-y:auto;background:#14141d;border:1px solid #2e2e3a;border-radius:6px;padding:4px;min-height:200px;" });
  let current = "";
  async function load(path) {
    const r = await api("/opencode/browse?path=" + encodeURIComponent(path));
    if (r.error) { pathLine.textContent = "无法访问: " + path; return; }
    current = r.path;
    pathLine.textContent = r.path || "选择磁盘";
    listBox.innerHTML = "";
    const up = el("div", { style: "padding:4px 6px;cursor:pointer;color:#7aa2f7;border-radius:4px;", onclick: () => load(r.parent ?? "") }, "⬅ .. (上一级)");
    up.addEventListener("mouseenter", () => up.style.background = "#22222f");
    up.addEventListener("mouseleave", () => up.style.background = "");
    listBox.append(up);
    for (const d of r.dirs || []) {
      const item = el("div", { style: "padding:4px 6px;cursor:pointer;border-radius:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;", onclick: () => load(d) }, "📁 " + d);
      item.addEventListener("mouseenter", () => item.style.background = "#22222f");
      item.addEventListener("mouseleave", () => item.style.background = "");
      listBox.append(item);
    }
  }
  const btnRow = el("div", { style: "display:flex;gap:6px;justify-content:flex-end;margin-top:8px;" }, [
    el("button", { class: "aie-btn", onclick: () => overlay.remove() }, "取消"),
    el("button", { class: "aie-btn aie-btn-primary", onclick: () => {
      if (current) targetInput.value = current;
      overlay.remove();
    } }, "选择此目录"),
  ]);
  box.append(pathLine, listBox, btnRow);
  overlay.append(box);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.append(overlay);
  load(targetInput.value.trim() || "");
}

async function llmConnect() {
  const base = document.getElementById("aie-llm-base").value.trim().replace(/\/$/, "");
  const key = document.getElementById("aie-llm-key").value.trim();
  if (!base || !key) { logmsg("请先填 base_url 和 api_key 再连接"); return; }
  logmsg("连接 " + base + " ...");
  try {
    const resp = await fetch(base + "/models", { headers: { "Authorization": "Bearer " + key } });
    if (!resp.ok) { logmsg("连接失败: HTTP " + resp.status); return; }
    const data = await resp.json();
    const ids = (data.data || []).map(m => m.id).filter(Boolean).sort();
    if (!ids.length) { logmsg("连接成功但模型列表为空"); return; }
    const dl = document.getElementById("aie-llm-models");
    dl.innerHTML = "";
    for (const id of ids) dl.append(el("option", { value: id }));
    document.getElementById("aie-llm-model").value = ids[0];
    logmsg(`连接成功,拉取到 ${ids.length} 个模型,已在模型栏提供下拉选择`);
  } catch (e) {
    logmsg("连接失败: " + e);
  }
}

function logmsg(m) {
  const l = document.getElementById("aie-log");
  if (l) l.textContent += m + "\n";
}

async function loadLLMSettings() {
  const cfg = await api("/settings");
  if (cfg.llm) {
    document.getElementById("aie-llm-base").value = cfg.llm.base_url || "";
    document.getElementById("aie-llm-key").value = cfg.llm.api_key || "";
    document.getElementById("aie-llm-model").value = cfg.llm.model || "";
    const idx = LLM_PRESETS.findIndex(p => p.base && p.base === cfg.llm.base_url);
    document.getElementById("aie-llm-preset").selectedIndex = idx >= 0 ? idx : LLM_PRESETS.length - 1;
  }
}

async function saveLLMSettings() {
  await post("/settings", {
    llm: {
      base_url: document.getElementById("aie-llm-base").value.trim(),
      api_key: document.getElementById("aie-llm-key").value.trim(),
      model: document.getElementById("aie-llm-model").value.trim(),
    },
  });
  logmsg("LLM 设置已保存");
}

function selectedSources() {
  return [...document.querySelectorAll(".aie-src:checked")].map(x => x.value);
}

async function doSearch() {
  const q = document.getElementById("aie-req").value.trim();
  const r = await api(`/search?query=${encodeURIComponent(q)}&sources=${selectedSources().join(",")}`);
  state.results = r.results || [];
  if (r.errors && Object.keys(r.errors).length) logmsg("部分来源出错: " + JSON.stringify(r.errors));
  renderResults();
}

function renderResults() {
  const list = document.getElementById("aie-results");
  list.innerHTML = "";
  for (const item of state.results) {
    const card = el("div", { style: "border:1px solid #333;border-radius:6px;padding:6px;margin:6px 0;cursor:pointer;background:#25252f;",
      onclick: () => selectResult(item) });
    card.append(el("div", { style: "font-weight:bold;" }, `[${item.source}] ${item.title || "(untitled)"}`));
    card.append(el("div", { style: "color:#999;" },
      `发布: ${fmtDate(item.published_at)} | 底模: ${item.base_model || "-"} | 作者: ${item.author || "-"}`));
    if (item.samples && item.samples.length) {
      const row = el("div", { style: "display:flex;gap:4px;margin-top:4px;flex-wrap:wrap;" });
      for (const s of item.samples.slice(0, 4)) {
        if (s.type === "video") {
          row.append(el("video", { src: s.url, style: "width:90px;height:90px;object-fit:cover;border-radius:4px;", muted: true, loop: true, autoplay: true }));
        } else {
          row.append(el("img", { src: s.url, style: "width:90px;height:90px;object-fit:cover;border-radius:4px;", loading: "lazy" }));
        }
      }
      card.append(row);
    }
    list.append(card);
  }
  if (!state.results.length) list.append(el("div", { style: "color:#777;" }, "无结果"));
}

async function selectResult(item) {
  state.selected = item;
  logmsg(`获取工作流: ${item.title}`);
  const r = await post("/workflow", item);
  if (r.error) { logmsg("获取失败: " + r.error); state.workflow = null; renderDetail(); return; }
  state.workflow = r.workflow;
  const check = await post("/deps/check", { workflow: state.workflow });
  state.deps = check;
  renderDetail();
}

function renderDetail() {
  const d = document.getElementById("aie-detail");
  d.innerHTML = "";
  if (!state.selected) return;
  d.append(el("div", { style: "font-weight:bold;" }, state.selected.title));
  if (state.selected.url) d.append(el("a", { href: state.selected.url, target: "_blank", style: "color:#7aa2f7;" }, "原始页面 ↗"));
  if (!state.workflow) return;
  const missN = state.deps?.nodes?.missing || [];
  const missM = state.deps?.models?.missing || [];
  d.append(el("div", { style: "margin-top:6px;" }, `缺失节点: ${missN.length ? missN.join(", ") : "无"}`));
  d.append(el("div", {}, `缺失模型: ${missM.length ? missM.map(m => m.filename).join(", ") : "无"}`));
  const btnRow = el("div", { style: "display:flex;gap:4px;margin-top:6px;flex-wrap:wrap;" });
  if (missN.length) btnRow.append(el("button", { onclick: installNodes }, "安装缺失节点"));
  if (missM.length) btnRow.append(el("button", { onclick: () => logmsg("请对每个缺失模型提供下载地址(repo_id/filename 或直链),使用 /ai_executor/install/model") }, "模型下载说明"));
  btnRow.append(el("button", { onclick: runWorkflow, style: "background:#2d6a4f;color:#fff;" }, "运行"));
  d.append(btnRow);
}

async function installNodes() {
  const miss = state.deps?.nodes?.missing || [];
  const r = await post("/install/nodes", { class_types: miss });
  pollJob(r.job_id);
}

async function pollJob(jid) {
  const t = setInterval(async () => {
    const j = await api(`/jobs/${jid}`);
    logmsg(`[${j.kind}] ${j.status} ${j.progress}/${j.total} ${j.error || ""}`);
    if (j.status === "done" || j.status === "failed") {
      clearInterval(t);
      if (j.needs_restart) logmsg("节点安装完成,请重启 ComfyUI 后重新检查依赖");
      if (j.saved_to) logmsg("已保存: " + j.saved_to);
      if (state.workflow && j.kind === "nodes") {
        state.deps = await post("/deps/check", { workflow: state.workflow });
        renderDetail();
      }
    }
  }, 1500);
}

async function aiPick() {
  const req = document.getElementById("aie-req").value.trim();
  if (!req) return;
  if (!state.results.length) await doSearch();
  const cfg = await api("/settings");
  const llm = cfg.llm || {};
  if (!llm.base_url || !llm.api_key || !llm.model) { logmsg("请先配置 LLM API"); return; }
  const candidates = state.results.slice(0, 10).map((r, i) =>
    `${i}. [${r.source}] ${r.title} | 发布:${fmtDate(r.published_at)} | 底模:${r.base_model || "-"} | tags:${(r.tags || []).join(",")}`).join("\n");
  try {
    const resp = await fetch(llm.base_url.replace(/\/$/, "") + "/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + llm.api_key },
      body: JSON.stringify({
        model: llm.model,
        messages: [
          { role: "system", content: "你是ComfyUI工作流选择助手。根据用户需求,从候选工作流列表中选择最合适的一个。只回复序号数字。" },
          { role: "user", content: `需求: ${req}\n\n候选:\n${candidates}` },
        ],
        temperature: 0.2,
      }),
    });
    const data = await resp.json();
    const text = data.choices?.[0]?.message?.content || "";
    const idx = parseInt(text.match(/\d+/)?.[0] ?? "-1", 10);
    if (idx >= 0 && idx < state.results.length) {
      logmsg(`AI 选择了 #${idx}`);
      selectResult(state.results[idx]);
    } else {
      logmsg("AI 未能解析选择: " + text);
    }
  } catch (e) {
    logmsg("LLM 调用失败: " + e);
  }
}

async function runWorkflow() {
  if (!state.workflow) return;
  const r = await post("/run", { workflow: state.workflow, randomize_seed: true });
  if (r.ok) logmsg("已提交, prompt_id=" + r.prompt_id);
  else logmsg("提交失败: " + (r.error || "") + " " + JSON.stringify(r.node_errors || r.detail || ""));
}

const oc = { session: null, timer: null, lastMsgCount: 0 };

async function ocRefreshStatus() {
  const dot = document.getElementById("aie-oc-dot");
  const txt = document.getElementById("aie-oc-status");
  if (!dot) return;
  try {
    const s = await api("/opencode/status");
    if (!s.installed) {
      dot.style.background = "#c0392b";
      txt.textContent = "未安装 opencode (npm i -g opencode-ai)";
    } else if (s.running) {
      dot.style.background = "#27ae60";
      txt.textContent = `运行中 :${s.port} (v${s.health?.version || "?"})`;
    } else {
      dot.style.background = "#e67e22";
      txt.textContent = "已安装,未运行";
    }
  } catch {
    dot.style.background = "#c0392b";
    txt.textContent = "检测失败";
  }
}

async function ocStart() {
  logmsg("启动 opencode serve...");
  const r = await post("/opencode/start", {});
  if (r.ok) logmsg(r.ready ? `opencode 就绪 (端口 ${r.port})` : "已拉起,等待就绪中...");
  else logmsg("启动失败: " + (r.error || ""));
  ocRefreshStatus();
}

async function ocStop() {
  await post("/opencode/stop", {});
  logmsg("已停止 opencode");
  ocRefreshStatus();
}

async function ocDispatch() {
  const req = document.getElementById("aie-req").value.trim();
  if (!req) { logmsg("请先输入需求"); return; }
  const r = await post("/opencode/dispatch", { requirement: req });
  if (!r.ok) { logmsg("派单失败: " + (r.error || "")); return; }
  oc.session = r.session_id;
  oc.lastMsgCount = 0;
  logmsg("已派单, session=" + r.session_id + " — AI 代理开始工作");
  if (oc.timer) clearInterval(oc.timer);
  oc.timer = setInterval(ocPoll, 3000);
}

async function ocAbort() {
  if (!oc.session) return;
  await post(`/opencode/abort/${oc.session}`, {});
  logmsg("已发送中止");
}

async function ocPoll() {
  if (!oc.session) return;
  try {
    const msgs = await api(`/opencode/messages/${oc.session}`);
    if (!Array.isArray(msgs)) return;
    for (const m of msgs) {
      const role = m.info?.role;
      for (const p of m.parts || []) {
        if (p.type === "text" && p.text && role === "assistant") {
          const key = m.info.id + p.id;
          if (oc["seen_" + key]) continue;
          oc["seen_" + key] = true;
          logmsg("[代理] " + p.text.slice(0, 1500));
        } else if (p.type === "tool" && p.state?.status === "completed") {
          const key = m.info.id + p.id;
          if (oc["seen_" + key]) continue;
          oc["seen_" + key] = true;
          logmsg("[工具] " + (p.tool || "") + " ✓");
        }
      }
    }
    const statuses = await api("/opencode/sessions_status");
    const st = statuses?.[oc.session];
    if (st && st.type === "idle") {
      clearInterval(oc.timer);
      oc.timer = null;
      logmsg("— 代理任务结束 —");
    }
  } catch (e) { /* keep polling */ }
}

app.registerExtension({
  name: "AIExecutor.Panel",
  async setup() {
    buildPanel();
    ocRefreshStatus();
    onboardingReminder();
  },
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "AIExecutorAgent") return;
    const orig = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      orig?.apply(this, arguments);
      const box = el("div", { style: "width:400px;padding:6px;background:#1e1e28;color:#ddd;font-size:12px;border-radius:6px;" });
      const setupDiv = el("div");
      buildOcSetup(setupDiv);
      box.append(setupDiv, el("hr", { style: "border:none;border-top:1px solid #333;margin:6px 0;" }));
      attachOcChat(box);
      this.addDOMWidget("oc_chat", "custom", box, { serialize: false, hideOnZoom: false });
      this.setSize([430, 640]);
    };
  },
});

async function onboardingReminder() {
  try {
    const st = await api("/opencode/onboarding");
    if (st.stage === "ready") return;
    const hints = {
      install: "未检测到 opencode。请在面板/节点中选择安装目录并确认,将自动下载官方独立二进制(无需 Node.js)",
      start: "opencode 已安装但未运行。请在面板/节点中点「启动」",
      auth: "opencode 未配置 LLM API Key。请在面板/节点中完成配置",
      model: "opencode 未选择默认模型。请在面板/节点中选择模型",
    };
    openPanel(document.getElementById("aie-panel"));
    logmsg("⚠ AI 代理未完成配置: " + (hints[st.stage] || st.stage));
  } catch { /* ignore */ }
}

async function buildOcSetup(container) {
  container.innerHTML = "";
  const st = await api("/opencode/onboarding");
  const line = el("div", { style: "margin:4px 0;color:#bbb;" });
  container.append(line);
  if (st.stage === "ready") {
    line.textContent = `✔ opencode 就绪 (provider: ${(st.detail.connected || []).join(", ")}, 模型: ${st.detail.current_model || "-"})`;
    return;
  }
  if (st.stage === "install") {
    line.textContent = "✘ 未安装 opencode — 选择安装目录后自动下载官方独立二进制(无需 Node.js)";
    const def = await api("/opencode/default_install_dir");
    const dirInput = el("input", { class: "aie-input", value: def.dir || "", style: "flex:1;margin:4px 0;" });
    const installBtn = el("button", { class: "aie-btn aie-btn-primary", style: "margin:4px 0;", onclick: async () => {
      const dest = dirInput.value.trim();
      if (!dest) return;
      installBtn.disabled = true;
      installBtn.textContent = "安装中...";
      logmsg("下载安装 opencode 到 " + dest + " ...");
      const r = await post("/opencode/install", { dir: dest });
      const t = setInterval(async () => {
        const j = await api(`/jobs/${r.job_id}`);
        if (j.status === "done" || j.status === "failed") {
          clearInterval(t);
          logmsg(j.status === "done" ? "opencode 安装完成: " + (j.saved_to || "") : "安装失败: " + (j.error || ""));
          buildOcSetup(container);
          ocRefreshStatus();
        }
      }, 2000);
    } }, "确认安装");
    container.append(
      el("div", { style: "display:flex;gap:4px;align-items:center;" }, [
        dirInput,
        el("button", { class: "aie-btn", onclick: () => openDirPicker(dirInput) }, "浏览"),
      ]),
      installBtn,
      el("div", { style: "color:#777;font-size:11px;" }, [
        "或 ",
        el("a", { href: "#", style: "color:#7aa2f7;", onclick: async (e) => {
          e.preventDefault();
          logmsg("改用 npm 安装 (需要 Node.js)...");
          const r = await post("/opencode/install", {});
          const t = setInterval(async () => {
            const j = await api(`/jobs/${r.job_id}`);
            if (j.status === "done" || j.status === "failed") {
              clearInterval(t);
              logmsg(j.status === "done" ? "npm 安装完成" : "npm 安装失败: " + (j.error || ""));
              buildOcSetup(container);
            }
          }, 2000);
        } }, "用 npm 安装 (需要 Node.js)"),
      ]),
    );
    return;
  }
  if (st.stage === "start") {
    line.textContent = "● opencode 已安装,服务未运行";
    container.append(el("button", { style: "margin:4px 0;", onclick: async () => { await ocStart(); buildOcSetup(container); } }, "启动服务"));
    return;
  }
  line.textContent = st.stage === "auth" ? "● 需要配置 LLM provider 的 API Key" : "● 需要选择默认模型";
  const prov = await api("/opencode/providers");
  const list = prov.providers || [];
  const sel = el("select", { class: "aie-input" });
  for (const p of list) sel.append(el("option", { value: p.id }, `${p.name}${p.connected ? " ✔" : ""}`));
  const key = el("input", { type: "password", placeholder: "api_key", class: "aie-input", style: "flex:1;margin:4px 0;" });
  const connMsg = el("span", { style: "color:#999;font-size:11px;" });
  const modelSel = el("select", { class: "aie-input", style: "display:none;" });
  const saveBtn = el("button", { class: "aie-btn aie-btn-primary", style: "margin:4px 0;display:none;", onclick: async () => {
    const r = await post("/opencode/auth", { provider: sel.value, api_key: key.value.trim(), model: modelSel.value });
    logmsg(r.ok ? "opencode 配置已保存" : "配置失败: " + (r.error || r.response || ""));
    buildOcSetup(container);
    ocRefreshStatus();
  } }, "保存配置");
  const connectBtn = el("button", { class: "aie-btn", onclick: async () => {
    const pid = sel.value, k = key.value.trim();
    if (!k) { connMsg.textContent = "请先输入 api_key"; return; }
    connMsg.textContent = "连接中...";
    const r = await post("/opencode/auth", { provider: pid, api_key: k });
    if (!r.ok) { connMsg.textContent = "连接失败: " + (r.error || r.response || ""); return; }
    const prov2 = await api("/opencode/providers");
    const p = (prov2.providers || []).find(x => x.id === pid);
    if (!p || !p.connected) { connMsg.textContent = "Key 已保存但 provider 未连接,请检查 Key"; return; }
    const models = p.models || [];
    modelSel.innerHTML = "";
    for (const m of models) modelSel.append(el("option", { value: m }, m));
    if (models.length) {
      modelSel.style.display = "";
      saveBtn.style.display = "";
      connMsg.textContent = `连接成功,${models.length} 个模型可选,请选择后保存`;
    } else {
      connMsg.textContent = "连接成功,但该 provider 未返回模型列表";
    }
  } }, "连接");
  container.append(sel, el("div", { style: "display:flex;gap:4px;align-items:center;" }, [key, connectBtn]), connMsg, modelSel, saveBtn);
}

function attachOcChat(container) {
  const chat = el("div", { style: "background:#111;border:1px solid #333;border-radius:6px;padding:6px;height:280px;overflow-y:auto;margin:4px 0;" });
  const input = el("textarea", { placeholder: "输入任务,例如: 搜索一个 flux 文生图工作流并跑一张赛博朋克城市", style: "width:100%;height:44px;background:#111;color:#ddd;border:1px solid #444;padding:4px;" });
  const btn = el("button", { style: "margin-top:4px;background:#2d6a4f;color:#fff;border:none;padding:5px 14px;border-radius:4px;cursor:pointer;" }, "发送");
  let session = null, timer = null;
  const seen = new Set();
  const addMsg = (who, text, color) => {
    const d = el("div", { style: `margin:4px 0;padding:4px 6px;border-radius:4px;background:${color};white-space:pre-wrap;word-break:break-word;` });
    d.textContent = `${who}: ${text}`;
    chat.append(d);
    chat.scrollTop = chat.scrollHeight;
  };
  const poll = async () => {
    if (!session) return;
    try {
      const msgs = await api(`/opencode/messages/${session}`);
      if (Array.isArray(msgs)) for (const m of msgs) {
        const role = m.info?.role;
        for (const p of m.parts || []) {
          const key = (m.info?.id || "") + ":" + (p.id || Math.random());
          if (seen.has(key)) continue;
          if (p.type === "text" && p.text) {
            seen.add(key);
            addMsg(role === "user" ? "我" : "代理", p.text, role === "user" ? "#264f78" : "#1f2d1f");
          } else if (p.type === "tool" && (p.state?.status === "completed" || p.state?.status === "error")) {
            seen.add(key);
            addMsg("工具", `${p.tool || ""} ${p.state.status === "completed" ? "✓" : "✗"} ${p.state?.title || ""}`, "#2a2a3a");
          }
        }
      }
      const statuses = await api("/opencode/sessions_status");
      if (statuses?.[session]?.type === "idle") {
        clearInterval(timer);
        timer = null;
        addMsg("系统", "— 任务结束 —", "#333");
      }
    } catch { /* keep polling */ }
  };
  btn.addEventListener("click", async () => {
    const req = input.value.trim();
    if (!req) return;
    input.value = "";
    addMsg("我", req, "#264f78");
    const r = await post("/opencode/dispatch", { requirement: req });
    if (!r.ok) { addMsg("系统", "派单失败: " + (r.error || ""), "#4a1f1f"); return; }
    session = r.session_id;
    if (timer) clearInterval(timer);
    timer = setInterval(poll, 2500);
  });
  container.append(chat, input, btn);
}
