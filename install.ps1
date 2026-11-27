#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ProjectDir "win_mcp_server.py"
$ConfigPath = Join-Path $ProjectDir "config.json"

Write-Host "=== 1. 安装 Python 依赖 ===" -ForegroundColor Cyan
pip install -r (Join-Path $ProjectDir "requirements.txt")

Write-Host "`n=== 2. 检查 Tailscale ===" -ForegroundColor Cyan
if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 Tailscale，正在通过 winget 安装..."
    winget install --id Tailscale.Tailscale -e --source winget
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Host "请先在桌面右下角登录 Tailscale，并在管理后台开启 MagicDNS 和 HTTPS 后重新运行此脚本。" -ForegroundColor Yellow
    exit 0
}

Write-Host "正在配置 Tailscale Funnel (映射本地 8000 端口)..."
tailscale funnel --bg 8000

$TsStatus = tailscale status --json | ConvertFrom-Json
$DnsName = $TsStatus.Self.DNSName.TrimEnd(".")
if (-not $DnsName) {
    $DnsName = Read-Host "未能自动获取域名，请手动输入你的 Tailscale 域名 (如 xxx.tailxxxx.ts.net)"
}
$PublicUrl = "https://$DnsName"

Write-Host "`n=== 3. 生成配置文件 config.json ===" -ForegroundColor Cyan
$DefaultWorkDir = Join-Path $env:USERPROFILE "GeminiWorkspace"
$WorkDir = Read-Host "请输入默认工作目录 (用于相对路径与命令执行，直接回车默认: $DefaultWorkDir)"
if ([string]::IsNullOrWhiteSpace($WorkDir)) { $WorkDir = $DefaultWorkDir }

$AuthPassword = Read-Host "请设置 OAuth 授权密码 (直接回车自动生成随机强密码)"
if ([string]::IsNullOrWhiteSpace($AuthPassword)) {
    $Bytes = New-Object byte[] 12
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($Bytes)
    $AuthPassword = [Convert]::ToBase64String($Bytes)
}

$ConfigObj = @{
    public_url       = $PublicUrl
    work_dir         = $WorkDir
    auth_password    = $AuthPassword
    port             = 8000
    allowed_commands = @("git", "python", "pip", "node", "npm", "pytest", "uv")
}
$ConfigObj | ConvertTo-Json -Depth 3 | Set-Content -Path $ConfigPath -Encoding UTF8

Write-Host "`n=== 4. 配置开机无窗口后台自启 ===" -ForegroundColor Cyan
$PythonW = (Get-Command pythonw).Source
$Action = New-ScheduledTaskAction -Execute $PythonW -Argument "`"$ScriptPath`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "Gemini-MCP-Server" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName "Gemini-MCP-Server"
Start-Sleep -Seconds 2

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "部署完成！请前往 gemini.google.com 绑定：" -ForegroundColor Green
Write-Host "MCP Server URL : $PublicUrl/mcp" -ForegroundColor Yellow
Write-Host "授权密码       : $AuthPassword" -ForegroundColor Yellow
Write-Host "默认工作目录   : $WorkDir"
Write-Host "==========================================" -ForegroundColor Green
