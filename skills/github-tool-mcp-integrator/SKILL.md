---
name: github-tool-mcp-integrator
description: Import open-source GitHub skills (SKILL.md or workflow prompts), download and install GitHub skills into local .agents/skills directories, run or wrap GitHub tool scripts via local Windows PC Control MCP on D drive, and integrate third-party GitHub MCP servers into Gemini via Tailscale Funnel. Use when the user shares a GitHub URL, asks to search/download/import a GitHub skill or prompt workflow, wants to clone and run a Python/Node/uv tool locally, asks to wrap a script into win_mcp_server.py, or wants to deploy and connect an open-source MCP server.
---

# github-tool-mcp-integrator

将 GitHub 上的开源 Skill、工具脚本或 MCP Server 按统一流程下载、安装并接入本地 Windows 环境与 Gemini，同时保持非 C 盘存储、权限安全与 Git 同步。

## When to Use

- 用户要求搜索、下载 GitHub 上的开源 Skill，并安装到本地项目（如 `.agents/skills/<skill-name>`）或导入为 Gemini 自定义技能。
- 用户提供 GitHub 仓库链接、原始 `SKILL.md` 或工作流提示词，要求导入并保存为自定义技能。
- 用户希望通过本地 `Windows PC Control` 克隆并运行 GitHub 上的 Python、Node.js 或 `uv` 工具脚本。
- 用户希望把高频使用的 GitHub 脚本封装为新的 `@mcp.tool()` 写入本地 `win_mcp_server.py`。
- 用户希望在本地部署 GitHub 上的开源 MCP Server，并通过 Tailscale Funnel 接入 Gemini Custom apps。

## Steps

首先判断用户目标属于下方哪一类工作流，若存在多选则按“先确定目标仓库/内容 -> 执行对应流程 -> 验证结果”顺序推进。

### Workflow A: 下载或复用 GitHub 开源 Skill

1. **获取内容：**
   - 若用户直接粘贴了 `SKILL.md` / 提示词，直接进入审阅。
   - 若用户提供 GitHub 链接或要求搜索并下载某个开源 Skill，通过本地 `Windows PC Control` 执行 `git clone --depth 1 <repo_url>` 拉取到 D 盘临时目录（如 `D:\GeminiWorkspace\tmp_<name>`），读取其中的 `SKILL.md` 与目录结构。
2. **安装到本地或导入 Gemini：**
   - **安装到本地目录（如 `.agents/skills`）：** 将目标 Skill 目录完整复制到用户指定的非 C 盘目标路径，清理临时目录，并运行 Skill 自带的 CLI 检查或示例命令确认本地依赖正常。
   - **导入为 Gemini 自定义技能：** 审阅开源 Skill，保留核心触发条件、步骤与验证标准，移除硬编码的 C 盘路径或无关平台配置，生成规范的 `SKILL.md` 并保存。
3. **验证结果：** 确认文件已落盘或技能已保存，给出一条可直接调用或测试的命令 / 提示词。

### Workflow B: 通过 Windows PC Control 运行或封装 GitHub 工具脚本

1. **检查连接与盘符：** 先确认 `Windows PC Control` 在线，所有克隆与依赖安装一律放在 D 盘工作目录下（默认如 `D:\GeminiWorkspace\tools`），避免写入 C 盘。
2. **克隆与检查：** 使用白名单命令 `git clone <repo_url>` 拉取代码，读取 `README.md` 与依赖文件（`requirements.txt`、`pyproject.toml`、`package.json`），向用户简要说明所需运行环境与安全风险。
3. **安装与运行：** 按项目类型使用白名单命令（`pip`、`uv`、`npm`、`python`、`node`）安装依赖并执行脚本；验证标准为退出码为 `0` 且输出符合预期。
4. **封装为 MCP 工具（高频复用时）：**
   - 在 `win_mcp_server.py` 中新增 `@mcp.tool()` 函数，所有涉及文件路径的参数必须复用 `_safe_path(..., write=...)` 以维持 C 盘只读与敏感路径黑名单保护。
   - 运行 `python -m py_compile win_mcp_server.py` 校验语法无报错。
   - 同步更新 `README.md` 工具列表，执行 `git add`、`git commit` 与 `git push origin main`。
   - 提醒用户重启 `Gemini-MCP-Server` 计划任务，并在 Gemini 右侧 **Developer Mode -> Tool schemas** 点击 **Sync schema** 验证工具总数增加。

### Workflow C: 接入 GitHub 开源 MCP Server

1. **评估传输协议：** 检查目标仓库是否原生支持 Streamable HTTP / SSE；若仅支持 `stdio`，说明需要通过 HTTP 桥接工具（如 `mcp-proxy`）转换后再暴露。
2. **本地部署（D 盘）：** 将仓库克隆至 D 盘目录并安装依赖，配置独立本地端口（避开主服务已占用的 `8000` 端口，例如 `8001`），在前台试运行确认端口正常监听。
3. **公网暴露：** 生成 Tailscale Funnel 映射命令（如使用独立路径或端口映射，避免覆盖现有 `/mcp` 入口），并给出安全提示（强认证、不用时可关闭 Funnel）。
4. **绑定与验证：** 引导用户前往 `gemini.google.com` -> **Settings** -> **Connected Apps** -> **Custom apps** -> **Add a custom app** 添加新的 MCP Server URL 并完成连接，验证工具列表可正常加载。

## Gotchas

- 不要直接向 C 盘克隆仓库或安装依赖，始终优先使用 D 盘目录并遵守 C 盘写保护与敏感路径黑名单。
- 当 `Windows PC Control` 返回 `MCP session with server terminated` 或 `401 Unauthorized` 时，先引导用户排查本地服务进程或重新授权，不要盲目重复调用。
- 封装新工具到 `win_mcp_server.py` 后，本地必须重启服务且在 Gemini 侧点击 **Sync schema** 才会生效，仅刷新网页不会更新工具列表。
- 修改 `gemini-windows-mcp` 仓库代码后，务必执行语法校验并同步 `git commit` 和 `git push`。
