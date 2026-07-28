# ComfyUI AI Executor

ComfyUI 插件：opencode 驱动的图像/视频任务执行者。自然语言提需求 → AI 代理搜索在线工作流并解说 → 你看样例选定 → 自动装依赖 → 画布打开。

## 核心流程（人机协同）

```
需求(中文)
 → 阶段0 代理解析需求为结构化JSON,向你确认
 → 阶段1 翻译+扩充检索词,在线搜索(Civitai/OpenArt/GitHub合集)
 → 阶段2 候选卡片上报面板: 标题/发布日期/底模/原文说明/推荐理由/原站样例图视频
 → 阶段3 你在面板点选(代理无权擅自选定,服务端token强制)
 → 阶段4 保存工作流 → 依赖检查 → 装缺失节点/模型(HuggingFace优先)
         → 需要重启时面板弹确认,守护进程自动重启ComfyUI且代理不断线
         → 「在画布中打开」一键加载
```

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/zzx4998/ComfyUI-AI-Executor.git
```

重启 ComfyUI，点右下角 **✦ AI Executor** 按钮（可拖动）。

## 首次配置（全程在面板内完成）

1. 插件自动检测缺什么并弹出提示
2. 「AI 代理」区：选目录 → 自动下载 opencode 官方独立二进制（无需 Node.js，自动走启动器/环境变量代理，带进度条/超时/自动重下）
3. 「LLM 设置」：选服务商（含 Kimi/GLM/阿里/腾讯/MiniMax 各家 Coding Plan 订阅预设）→ 填 Key → 连接拉模型列表 → 保存（自动同步为 opencode 默认模型并重启其服务）

## 架构

- **插件后端**（aiohttp 挂在 ComfyUI 上）：搜索部 API（search/workflow/classify/candidates）+ 使用部 API（save/deps/install/run/system）
- **opencode serve**：AI 代理，读取 `opencode/AGENTS.md` 固定流水线，通过 `/session/{id}/command` 执行 `comfyui_task` 命令；权限锁定（禁改文件，bash 仅放行 curl）
- **supervisor 守护进程**：WMI 拉起的独立进程（不受启动器 Job Object 约束），托管 opencode 生命周期，负责重启 ComfyUI（快照启动命令/环境变量/cwd），ComfyUI 重启时代理会话不断线
- **token 状态机**：代理上报候选才发 token，用户选定才激活，无 token 时 save/run/restart 接口一律 403——流程严格性由服务端保证，不靠提示词自觉

## 设计约束

- 不修改 ComfyUI 本体、其他插件代码、环境依赖
- API Key 不落盘到 git（运行时配置 gitignore，注入走环境变量）
- 代理禁止读本地文件找工作流/图片，禁止自行生成样例图，禁止擅自选定工作流
