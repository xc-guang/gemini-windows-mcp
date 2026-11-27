# Gemini Windows MCP Server

通过 **MCP (Model Context Protocol) + 标准 OAuth 2.0 + Tailscale Funnel**，让网页端和手机端 Gemini App 安全远程控制你的 Windows 电脑。无需购买域名，无需公网 IP，开机静默后台运行。

## 核心特性

- **原生兼容 Gemini App**：完整实现标准 OAuth 2.0（含动态客户端注册与 PKCE）和 Streamable HTTP 协议。
- **零成本永久域名**：基于 Tailscale Funnel 免费获取永久固定 HTTPS 域名。
- **灵活的目录访问与命令防护**：
  - **全盘路径支持**：文件操作工具（`list_files`、`read_file`、`write_file`、`read_image`）支持访问本机任意绝对路径（可跨目录、跨盘符）；传入相对路径时默认基于 `config.json` 中的 `work_dir`。
  - **命令白名单**：`run_command` 默认在 `work_dir` 中执行，仅允许运行白名单内的开发命令（默认 `git` / `python` / `pip` / `node` / `npm` / `pytest` / `uv`），禁止 Shell 注入字符，单次执行超时 30 秒。
- **开箱即用工具**：`list_files`、`read_file`、`write_file`、`read_image`、`run_command`。
- **静默后台运行**：自动配置 Windows 任务计划程序，使用 `pythonw.exe` 无黑框自启。

> **安全提示**：由于已开放本机任意绝对路径的读写权限，请务必在 `config.json` 中使用高强度 OAuth 授权密码，避免操作 `C:\Windows` 等系统关键目录；长期不使用时建议执行 `tailscale funnel --https=443 off` 关闭公网穿透。

## 快速开始（3 分钟）

### 前置条件

1. Windows 10 / 11，已安装 **Python 3.10+**（安装时勾选 Add to PATH）。
2. 注册免费 [Tailscale](https://tailscale.com/) 账号，登录客户端后在后台 **DNS** 页面开启 **MagicDNS** 与 **HTTPS Certificates**。

### 第一步：克隆并一键部署

以**管理员身份**打开 PowerShell，执行：

```powershell
git clone https://github.com/xc-guang/gemini-windows-mcp.git
cd gemini-windows-mcp
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

> 若终端提示开启 Funnel 权限，点击终端给出的链接在网页确认即可。

脚本完成后会输出你的 **`MCP Server URL`** 和 **`授权密码`**。

### 第二步：在 Gemini 中绑定

1. 打开 [gemini.google.com](https://gemini.google.com) → 左下角 **Settings** → **Connected Apps** → **Custom apps** → **Add a custom app**。
2. 填入脚本输出的 **MCP Server URL**（格式：`https://xxx.tailxxxx.ts.net/mcp`），点击 **Next**。
3. 在弹出的授权网页中输入 **授权密码** 并确认。
4. 点击 **Connect** 完成保存。

### 第三步：开始使用

在任意 Gemini 对话框（网页端或手机 App）中直接 `@Windows PC Control`：

- `@Windows PC Control 列出工作目录的文件`
- `@Windows PC Control 帮我写一个 python 脚本并运行`
- `@Windows PC Control 读取 D:\Images\demo.png，告诉我图里是什么`（支持任意绝对路径）

## 常用维护命令

修改配置后重启服务（编辑 `config.json` 后生效）：

```powershell
taskkill /f /im pythonw.exe
Start-ScheduledTask -TaskName "Gemini-MCP-Server"
```

关闭公网穿透：

```powershell
tailscale funnel --https=443 off
```
