# ComfyUI AI Executor

ComfyUI 插件：从提需求到出图/出视频的一站式 AI 执行者。

- 在线搜索工作流：Civitai / ComfyWorkflows / OpenArt / GitHub 合集 + 本地工作流
- 每条结果展示：**发布日期、底模 (base model)、样例图/样例视频**、作者、原链接
- 自动检查缺失的自定义节点与模型文件
- 一键安装缺失节点（git clone + pip，仅新增，不改动任何现有节点/ComfyUI 代码）
- 模型下载（HuggingFace 优先，可切换 hf-mirror）
- 参数注入、随机种子、提交队列、进度跟踪
- 可选 LLM（任意 OpenAI 兼容 API，如 Kimi / DeepSeek）根据自然语言需求自动挑选工作流

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/zzx4998/ComfyUI-AI-Executor.git
```

重启 ComfyUI，点击右下角 **AI** 悬浮按钮打开面板。

## 使用流程

1. 在面板中展开 "LLM 设置"，填入 OpenAI 兼容 API 的 base_url / api_key / model（可选）
2. 输入自然语言需求，勾选来源站点，点 "搜索工作流" 或 "AI 帮我选"
3. 结果卡片显示发布日期、底模、样例图/视频，点击卡片获取工作流 JSON
4. 面板显示缺失节点/模型 → "安装缺失节点"（装完需重启 ComfyUI）
5. 点 "运行" 提交到 ComfyUI 队列，在界面查看进度与结果

## API（供其他工具调用）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai_executor/search?query=&sources=` | 聚合搜索 |
| POST | `/ai_executor/workflow` | 拉取工作流 JSON |
| POST | `/ai_executor/classify` | 工作流功能分类（任务方向/输入槽/提示词槽/尺寸槽/输出节点）|
| GET | `/ai_executor/env` | 环境清单（全部节点名 + 已有模型）|
| POST | `/ai_executor/deps/check` | 缺失节点/模型检查 |
| POST | `/ai_executor/install/nodes` | 安装缺失节点（后台任务）|
| POST | `/ai_executor/install/model` | 下载模型（url 或 repo_id+filename）|
| GET | `/ai_executor/jobs/{id}` | 任务进度 |
| POST | `/ai_executor/upload` | 上传输入素材（multipart 字段 `image`）|
| POST | `/ai_executor/run` | 参数注入并提交运行 |
| GET | `/ai_executor/run_status/{prompt_id}` | 执行状态与产物 |

## opencode 代理模式（核心玩法）

插件是 opencode 的 ComfyUI 专用工具系统：opencode 代理读取规则手册，自主完成
"需求理解 → 翻译扩充检索 → 筛选工作流 → 装依赖 → 参数注入 → 运行 → 失败自愈"。

1. 安装 opencode：`npm i -g opencode-ai`，并给它配好 LLM（`opencode auth login`）
2. 面板中展开 **"AI 代理 (opencode)"**，点 "启动"（插件会以 `opencode/` 目录为工作目录拉起 `opencode serve`，加载其中的 `AGENTS.md` 规则手册和 `opencode.json` 权限配置）
3. 输入需求，点 **"▶ 派单给 AI 代理执行需求"**，日志区实时显示代理的每一步
4. `opencode/opencode.json` 已限制代理权限：禁止编辑/写文件、bash 仅放行 curl 等只读与 API 调用命令——代理只能用环境，不能动环境

## 设计约束

- 只新增 `custom_nodes/ComfyUI-AI-Executor` 目录，不修改 ComfyUI 本体及任何已有节点的代码
- 节点安装通过 `git clone` 新增目录；模型下载写入 `models/` 对应子目录
- 设置保存在插件目录 `config.json`（已 gitignore，API Key 不会入库）
