import { app } from "../../../scripts/app.js";

const API = "/ai_executor";

const state = {
  results: [],
  selected: null,
  workflow: null,
  deps: null,
  jobs: {},
};

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

  const title = el("div", { style: "display:flex;justify-content:space-between;margin-bottom:8px;" }, [
    el("b", {}, "AI Executor"),
    el("a", { href: "#", style: "color:#888", onclick: (e) => { e.preventDefault(); root.style.display = "none"; } }, "✕"),
  ]);

  const llmBox = el("details", { style: "margin-bottom:8px;" }, [
    el("summary", {}, "LLM 设置 (OpenAI 兼容 API)"),
    el("input", { id: "aie-llm-base", placeholder: "base_url 如 https://api.moonshot.cn/v1", style: "width:100%;margin:4px 0;background:#111;color:#ddd;border:1px solid #444;padding:4px;" }),
    el("input", { id: "aie-llm-key", placeholder: "api_key", type: "password", style: "width:100%;margin:4px 0;background:#111;color:#ddd;border:1px solid #444;padding:4px;" }),
    el("input", { id: "aie-llm-model", placeholder: "model 如 kimi-k2 / deepseek-chat", style: "width:100%;margin:4px 0;background:#111;color:#ddd;border:1px solid #444;padding:4px;" }),
    el("button", { style: "margin:4px 0;", onclick: saveLLMSettings }, "保存设置"),
  ]);

  const reqBox = el("div", { style: "margin-bottom:8px;" }, [
    el("textarea", { id: "aie-req", placeholder: "用自然语言描述需求,例如: 把这张照片变成吉卜力风格并放大到4K", style: "width:100%;height:48px;background:#111;color:#ddd;border:1px solid #444;padding:4px;" }),
    el("div", { style: "display:flex;gap:4px;margin-top:4px;" }, [
      el("button", { onclick: () => doSearch() }, "搜索工作流"),
      el("button", { onclick: () => aiPick() }, "AI 帮我选"),
    ]),
  ]);

  const srcRow = el("div", { style: "margin-bottom:6px;display:flex;gap:6px;flex-wrap:wrap;" },
    ["local", "civitai", "comfyworkflows", "openart", "github"].map(s =>
      el("label", { style: "cursor:pointer;" }, [
        el("input", { type: "checkbox", class: "aie-src", value: s, checked: s === "local" || s === "civitai" ? "checked" : null }), " " + s,
      ])
    ));

  const list = el("div", { id: "aie-results" });
  const detail = el("div", { id: "aie-detail", style: "margin-top:8px;" });
  const log = el("pre", { id: "aie-log", style: "background:#111;padding:6px;max-height:160px;overflow:auto;white-space:pre-wrap;margin-top:8px;" });

  root.append(title, llmBox, reqBox, srcRow, list, detail, log);
  document.body.append(root);

  const fab = el("button", { style: `
    position:fixed;bottom:80px;right:10px;z-index:9999;border-radius:50%;width:44px;height:44px;
    background:#5a4fcf;color:#fff;border:none;cursor:pointer;font-size:18px;`,
    onclick: () => { root.style.display = root.style.display === "none" ? "block" : "none"; } }, "AI");
  document.body.append(fab);

  loadLLMSettings();
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

app.registerExtension({
  name: "AIExecutor.Panel",
  async setup() {
    buildPanel();
  },
});
