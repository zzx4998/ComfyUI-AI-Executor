import { app } from "../../../scripts/app.js";

const API = "/ai_executor";

const LLM_PRESETS = [
  { name: "选择服务商...", base: "", model: "" },
  { name: "Kimi For Coding (订阅)", base: "https://api.kimi.com/coding/v1", model: "k3", proto: "anthropic" },
  { name: "GLM Coding Plan (智谱订阅)", base: "https://open.bigmodel.cn/api/coding/paas/v4", model: "glm-5.2", proto: "openai" },
  { name: "阿里 Coding Plan (订阅)", base: "https://coding.dashscope.aliyuncs.com/v1", model: "qwen3-coder-plus", proto: "openai" },
  { name: "腾讯 Coding Plan (订阅)", base: "https://api.lkeap.cloud.tencent.com/coding/v3", model: "hunyuan-2.0-instruct", proto: "openai" },
  { name: "MiniMax Coding Plan (订阅)", base: "https://api.minimaxi.com/anthropic/v1", model: "MiniMax-M2.5", proto: "anthropic" },
  { name: "Kimi 开放平台 (按量)", base: "https://api.moonshot.cn/v1", model: "kimi-k3", proto: "openai" },
  { name: "DeepSeek", base: "https://api.deepseek.com/v1", model: "deepseek-chat", proto: "openai" },
  { name: "通义千问 (阿里)", base: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus", proto: "openai" },
  { name: "智谱 GLM", base: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash", proto: "openai" },
  { name: "硅基流动 SiliconFlow", base: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen2.5-7B-Instruct", proto: "openai" },
  { name: "火山方舟 (字节)", base: "https://ark.cn-beijing.volces.com/api/v3", model: "", proto: "openai" },
  { name: "OpenAI", base: "https://api.openai.com/v1", model: "gpt-4o-mini", proto: "openai" },
  { name: "OpenRouter", base: "https://openrouter.ai/api/v1", model: "", proto: "openai" },
  { name: "Groq", base: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile", proto: "openai" },
  { name: "Gemini (Google)", base: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.0-flash", proto: "openai" },
  { name: "Ollama (本地)", base: "http://127.0.0.1:11434/v1", model: "qwen2.5", proto: "openai" },
  { name: "自定义", base: "", model: "", proto: "openai" },
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
    el("summary", {}, ["LLM 设置 (全局唯一配置入口) ", helpIcon("在这里配置一次,同时用于「AI 帮我选」和 opencode 代理。选择服务商自动填地址和推荐模型;订阅类(Coding Plan) Key 请选带「订阅」字样的预设。保存后自动同步给 opencode 并重启其服务。")]),
    el("select", { id: "aie-llm-preset", class: "aie-input",
      onchange: (e) => {
        const p = LLM_PRESETS[e.target.selectedIndex];
        if (p && p.base) {
          document.getElementById("aie-llm-base").value = p.base;
          document.getElementById("aie-llm-proto").value = p.proto || "openai";
          const m = document.getElementById("aie-llm-model");
          if (p.model) m.value = p.model;
        }
      } },
      LLM_PRESETS.map(p => el("option", {}, p.name))),
    el("input", { id: "aie-llm-proto", type: "hidden", value: "openai" }),
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
    el("div", { style: "font-weight:600;color:#cfd2e0;" }, ["需求 ", helpIcon("用自然语言描述你要做的事,中文即可。点「派单」后 opencode 代理全自动完成: 理解需求→翻译扩充检索→筛选工作流→装缺失节点/模型→参数注入→运行→失败重试。可在下方「AI 代理」区或「AI Executor Agent」节点里看实时过程。")]),
    el("textarea", { id: "aie-req", class: "aie-input", placeholder: "例如: 把这张照片变成吉卜力风格并放大到4K", style: "height:48px;" }),
    el("div", { style: "display:flex;gap:4px;margin-top:4px;" }, [
      el("button", { class: "aie-btn aie-btn-primary", style: "flex:1;padding:7px;", onclick: ocDispatch }, "▶ 派单给 AI 代理执行"),
      el("button", { class: "aie-btn", onclick: ocAbort }, "中止"),
    ]),
  ]);

  const ocBox = el("details", { class: "aie-card" }, [
    el("summary", {}, ["AI 代理 (opencode) ", helpIcon("opencode 服务状态与配置向导。首次使用按提示完成安装;LLM 配置在上方「LLM 设置」里,保存后自动同步。代理执行过程会显示在下面日志区。")]),
    el("div", { style: "display:flex;gap:4px;align-items:center;margin:4px 0;" }, [
      el("span", { id: "aie-oc-dot", style: "width:8px;height:8px;border-radius:50%;background:#666;display:inline-block;" }),
      el("span", { id: "aie-oc-status", style: "color:#999;flex:1;" }, "未检测"),
      el("button", { class: "aie-btn", onclick: ocStart }, "启动"),
      el("button", { class: "aie-btn", onclick: ocStop }, "停止"),
    ]),
    (() => { const d = el("div"); buildOcSetup(d); return d; })(),
  ]);

  const log = el("pre", { id: "aie-log", style: "background:#14141d;border:1px solid #2e2e3a;border-radius:6px;padding:6px;max-height:160px;overflow:auto;white-space:pre-wrap;margin-top:8px;" });

  root.append(title, llmBox, reqBox, ocBox, log);
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

function fmtMB(b) { return (b / 1048576).toFixed(1); }

function watchJob(jobId, barBox, onDone) {
  let lastBytes = 0, lastTime = Date.now();
  const t = setInterval(async () => {
    const j = await api(`/jobs/${jobId}`);
    if (barBox) {
      const pct = j.total ? Math.min(100, (j.progress / j.total * 100)) : 0;
      const now = Date.now();
      const speed = (j.progress - lastBytes) / 1048576 / ((now - lastTime) / 1000 || 1);
      lastBytes = j.progress; lastTime = now;
      const attempt = j.attempt ? ` | 第 ${j.attempt}/${j.attempts} 次尝试` : "";
      barBox.innerHTML = "";
      const track = el("div", { style: "background:#14141d;border:1px solid #2e2e3a;border-radius:6px;height:14px;overflow:hidden;" });
      track.append(el("div", { style: `width:${pct}%;height:100%;background:linear-gradient(90deg,#667eea,#764ba2);transition:width .5s;` }));
      barBox.append(track, el("div", { style: "color:#9ab;font-size:11px;margin-top:2px;" },
        j.status === "running"
          ? `${fmtMB(j.progress)} / ${j.total ? fmtMB(j.total) : "?"} MB (${pct.toFixed(0)}%) | ${speed.toFixed(1)} MB/s${attempt}`
          : `${j.status}${attempt}`));
    }
    if (j.status === "done" || j.status === "failed") {
      clearInterval(t);
      onDone && onDone(j);
    }
  }, 1000);
  return t;
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
  const proto = document.getElementById("aie-llm-proto").value;
  const base = document.getElementById("aie-llm-base").value.trim().replace(/\/$/, "");
  const key = document.getElementById("aie-llm-key").value.trim();
  if (!base) { logmsg("请先填 base_url"); return; }
  if (!key) logmsg("Key 栏为空,将使用已保存的 Key 连接");
  logmsg("连接 " + base + " ...");
  try {
    const r = await post("/llm/models", { base, api_key: key, proto });
    if (!r.ok) { logmsg("连接失败: " + (r.error || "")); return; }
    const ids = r.models || [];
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
    document.getElementById("aie-llm-model").value = cfg.llm.model || "";
    document.getElementById("aie-llm-proto").value = cfg.llm.proto || "openai";
    const keyInput = document.getElementById("aie-llm-key");
    keyInput.value = "";
    keyInput.placeholder = cfg.llm.has_key ? "已保存 Key (留空保持不变,输入新 Key 则替换)" : "api_key";
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
      proto: document.getElementById("aie-llm-proto").value || "openai",
    },
  });
  logmsg("LLM 设置已保存,正在同步到 opencode 并重启服务...");
  await post("/opencode/stop", {});
  const r = await post("/opencode/start", {});
  logmsg(r.ok ? "opencode 已用该 API 重启,默认模型 = aie-custom/" + document.getElementById("aie-llm-model").value
              : "opencode 未启动(" + (r.error || "") + "),设置将在下次启动时生效");
  ocRefreshStatus();
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
      auth: "opencode 未配置 LLM。请直接在「LLM 设置」里选服务商填 Key 保存,会自动同步",
      model: "opencode 未选择默认模型。请在「LLM 设置」里填模型名并保存",
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
    line.textContent = "✘ 未安装 opencode — 选择安装目录后自动下载官方独立二进制(无需 Node.js,自动走启动器代理)";
    const def = await api("/opencode/default_install_dir");
    const dirInput = el("input", { class: "aie-input", value: def.dir || "", style: "flex:1;margin:4px 0;" });
    const timeoutInput = el("input", { class: "aie-input", type: "number", value: 120, min: 0, title: "秒", style: "width:70px;margin:4px 0;" });
    const retryChk = el("input", { type: "checkbox", checked: "checked" });
    const retryMax = el("input", { class: "aie-input", type: "number", value: 3, min: 1, max: 10, style: "width:50px;margin:4px 0;" });
    const barBox = el("div", { style: "margin:4px 0;" });
    const installBtn = el("button", { class: "aie-btn aie-btn-primary", style: "margin:4px 0;", onclick: async () => {
      const dest = dirInput.value.trim();
      if (!dest) return;
      installBtn.disabled = true;
      installBtn.textContent = "安装中...";
      logmsg("下载安装 opencode 到 " + dest + " ...");
      const r = await post("/opencode/install", {
        dir: dest,
        timeout_sec: parseInt(timeoutInput.value || "120", 10),
        auto_retry: retryChk.checked,
        retry_max: parseInt(retryMax.value || "3", 10),
      });
      watchJob(r.job_id, barBox, (j) => {
        logmsg(j.status === "done" ? "opencode 安装完成: " + (j.saved_to || "") : "安装失败: " + (j.error || ""));
        buildOcSetup(container);
        ocRefreshStatus();
      });
    } }, "确认安装");
    container.append(
      el("div", { style: "display:flex;gap:4px;align-items:center;" }, [
        dirInput,
        el("button", { class: "aie-btn", onclick: () => openDirPicker(dirInput) }, "浏览"),
      ]),
      el("div", { style: "display:flex;gap:6px;align-items:center;color:#999;font-size:11px;flex-wrap:wrap;" }, [
        "停滞超时(秒,0=不限)", timeoutInput,
        el("label", { style: "cursor:pointer;" }, [retryChk, " 超时自动重下"]),
        "次数", retryMax,
      ]),
      barBox,
      installBtn,
      el("div", { style: "color:#777;font-size:11px;" }, [
        "或 ",
        el("a", { href: "#", style: "color:#7aa2f7;", onclick: async (e) => {
          e.preventDefault();
          logmsg("改用 npm 安装 (需要 Node.js)...");
          const r = await post("/opencode/install", {});
          watchJob(r.job_id, barBox, (j) => {
            logmsg(j.status === "done" ? "npm 安装完成" : "npm 安装失败: " + (j.error || ""));
            buildOcSetup(container);
          });
        } }, "用 npm 安装 (需要 Node.js)"),
      ]),
    );
    return;
  }
  if (st.stage === "start") {
    line.textContent = "● opencode 已安装,服务未运行";
    container.append(el("div", { style: "display:flex;gap:4px;align-items:center;margin:4px 0;" }, [
      el("button", { class: "aie-btn aie-btn-primary", onclick: async () => { await ocStart(); buildOcSetup(container); } }, "启动服务"),
      el("button", { class: "aie-btn", onclick: async (e) => {
        if (!confirm("确认卸载 opencode?将删除二进制和配置")) return;
        const r = await post("/opencode/uninstall", {});
        logmsg(r.ok ? "已卸载" : "部分文件被占用,请重启 ComfyUI 后再卸载: " + (r.locked || []).join(", "));
        buildOcSetup(container);
        ocRefreshStatus();
      } }, "卸载"),
    ]));
    return;
  }
  line.textContent = "● 未配置模型 — 请在上方「LLM 设置」选择服务商、填 Key、保存,将自动同步到这里";
  const syncBtn = el("button", { class: "aie-btn aie-btn-primary", style: "margin:4px 0;", onclick: async () => {
    syncBtn.disabled = true;
    logmsg("从 LLM 设置同步并重启 opencode...");
    await post("/opencode/stop", {});
    const r = await post("/opencode/start", {});
    logmsg(r.ok ? "opencode 已用 LLM 设置重启" : "启动失败: " + (r.error || "请先在 LLM 设置中填好 API"));
    buildOcSetup(container);
    ocRefreshStatus();
  } }, "从 LLM 设置同步并重启服务");
  container.append(syncBtn);
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
