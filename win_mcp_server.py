import base64
import hashlib
import json
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import uvicorn
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"
TOKEN_STORE = BASE_DIR / ".mcp_tokens.json"

if not CONFIG_FILE.exists():
    raise FileNotFoundError("未找到 config.json，请先运行 install.ps1 生成配置文件。")

CONFIG = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
PUBLIC_URL = CONFIG["public_url"].rstrip("/")
PUBLIC_HOST = urlparse(PUBLIC_URL).hostname
WORK_DIR = Path(CONFIG["work_dir"]).resolve()
WORK_DIR.mkdir(parents=True, exist_ok=True)
AUTH_PASSWORD = CONFIG["auth_password"]
PORT = int(CONFIG.get("port", 8000))
ALLOWED_COMMANDS = set(
    CONFIG.get("allowed_commands", ["git", "python", "pip", "node", "npm", "pytest", "uv"])
)
FORBIDDEN_CHARS = {";", "&", "|", ">", "<", "`", "$", "\n", "\r"}

AUTH_CODES: dict[str, dict] = {}


def _load_tokens() -> dict:
    if TOKEN_STORE.exists():
        return json.loads(TOKEN_STORE.read_text(encoding="utf-8"))
    return {"access_tokens": [], "refresh_tokens": []}


def _save_token(access_token: str, refresh_token: str):
    data = _load_tokens()
    data["access_tokens"].append(access_token)
    data["refresh_tokens"].append(refresh_token)
    TOKEN_STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


allowed_hosts = ["127.0.0.1:*", "localhost:*"]
if PUBLIC_HOST:
    allowed_hosts.extend([PUBLIC_HOST, f"{PUBLIC_HOST}:*"])

mcp = FastMCP(
    "Windows-PC-Control",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    ),
)


def _safe_path(rel_path: str) -> Path:
    target = (WORK_DIR / rel_path).resolve()
    if not target.is_relative_to(WORK_DIR):
        raise ValueError(f"拒绝访问工作目录 ({WORK_DIR}) 以外的路径")
    return target


@mcp.tool()
def list_files(sub_dir: str = ".") -> list[str]:
    """列出工作目录下指定子目录的文件和文件夹"""
    target = _safe_path(sub_dir)
    return [p.name + ("/" if p.is_dir() else "") for p in sorted(target.iterdir())]


@mcp.tool()
def read_file(path: str) -> str:
    """读取工作目录内的文本文件内容"""
    return _safe_path(path).read_text(encoding="utf-8")


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """向工作目录内写入文本文件（自动创建父目录）"""
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入: {target.relative_to(WORK_DIR)}"


@mcp.tool()
def read_image(path: str) -> Image:
    """读取工作目录内的图片文件（支持 jpg/png/webp 等）"""
    return Image(path=str(_safe_path(path)))


@mcp.tool()
def run_command(command: str) -> str:
    """在工作目录下安全执行白名单内的开发命令（最长 30 秒）"""
    if any(ch in command for ch in FORBIDDEN_CHARS):
        return "拒绝执行：命令包含禁止的特殊字符。"
    try:
        args = shlex.split(command, posix=False)
    except ValueError as e:
        return f"命令解析失败: {e}"
    if not args:
        return "拒绝执行：命令为空。"

    cmd_name = args[0].strip('"').strip("'").lower()
    if cmd_name.endswith(".exe"):
        cmd_name = cmd_name[:-4]
    if cmd_name not in ALLOWED_COMMANDS:
        return f"拒绝执行：'{cmd_name}' 不在白名单中。允许: {', '.join(sorted(ALLOWED_COMMANDS))}"

    executable = shutil.which(cmd_name)
    if not executable:
        return f"执行失败：系统中找不到命令 '{cmd_name}'。"
    args[0] = executable

    try:
        res = subprocess.run(
            args, cwd=WORK_DIR, shell=False, capture_output=True, text=True, timeout=30
        )
        return f"Exit Code: {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    except subprocess.TimeoutExpired:
        return "执行失败：命令运行超过 30 秒已强制终止。"


# ================= 标准 OAuth 2.0 端点 =================
async def protected_resource_metadata(request: Request):
    return JSONResponse({
        "resource": f"{PUBLIC_URL}/mcp",
        "authorization_servers": [PUBLIC_URL],
        "bearer_methods_supported": ["header"],
    })


async def auth_server_metadata(request: Request):
    return JSONResponse({
        "issuer": PUBLIC_URL,
        "authorization_endpoint": f"{PUBLIC_URL}/oauth/authorize",
        "token_endpoint": f"{PUBLIC_URL}/oauth/token",
        "registration_endpoint": f"{PUBLIC_URL}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
    })


async def oauth_register(request: Request):
    body = await request.json()
    return JSONResponse({
        "client_id": f"gemini-{secrets.token_hex(8)}",
        "client_secret": secrets.token_hex(16),
        "client_name": body.get("client_name", "Gemini"),
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": body.get("token_endpoint_auth_method", "none"),
    }, status_code=201)


async def oauth_authorize(request: Request):
    if request.method == "GET":
        p = request.query_params
        html = f"""
        <html><body style="font-family:sans-serif;max-width:360px;margin:80px auto;text-align:center;">
          <h2>授权 Gemini 访问此电脑</h2>
          <form method="post">
            <input type="hidden" name="redirect_uri" value="{p.get('redirect_uri', '')}"/>
            <input type="hidden" name="state" value="{p.get('state', '')}"/>
            <input type="hidden" name="code_challenge" value="{p.get('code_challenge', '')}"/>
            <input type="password" name="password" placeholder="输入 config.json 中的授权密码" required
                   style="width:100%;padding:10px;margin:12px 0;box-sizing:border-box;"/>
            <button type="submit" style="width:100%;padding:10px;background:#1a73e8;color:#fff;border:none;border-radius:4px;cursor:pointer;">
              确认授权
            </button>
          </form>
        </body></html>
        """
        return HTMLResponse(html)

    form = await request.form()
    if form.get("password") != AUTH_PASSWORD:
        return HTMLResponse("<h3>密码错误，请返回重试。</h3>", status_code=403)

    code = secrets.token_urlsafe(32)
    AUTH_CODES[code] = {
        "code_challenge": form.get("code_challenge", ""),
        "expires_at": time.time() + 300,
    }
    params = {"code": code}
    if form.get("state"):
        params["state"] = form.get("state")
    return RedirectResponse(f"{form.get('redirect_uri')}?{urlencode(params)}", status_code=302)


async def oauth_token(request: Request):
    ctype = request.headers.get("content-type", "")
    data = await request.json() if "application/json" in ctype else await request.form()
    grant_type = data.get("grant_type")

    if grant_type == "authorization_code":
        code = data.get("code", "")
        record = AUTH_CODES.pop(code, None)
        if not record or record["expires_at"] < time.time():
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

        if record["code_challenge"]:
            verifier = data.get("code_verifier", "").encode()
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=").decode()
            if digest != record["code_challenge"]:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

    elif grant_type == "refresh_token":
        if data.get("refresh_token") not in _load_tokens()["refresh_tokens"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    _save_token(access_token, refresh_token)
    return JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": 31536000,
    })


app = mcp.streamable_http_app()
app.routes.extend([
    Route("/.well-known/oauth-protected-resource", protected_resource_metadata, methods=["GET"]),
    Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata, methods=["GET"]),
    Route("/.well-known/oauth-authorization-server", auth_server_metadata, methods=["GET"]),
    Route("/oauth/register", oauth_register, methods=["POST"]),
    Route("/oauth/authorize", oauth_authorize, methods=["GET", "POST"]),
    Route("/oauth/token", oauth_token, methods=["POST"]),
])


class OAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(("/.well-known/", "/oauth/")):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token not in _load_tokens()["access_tokens"]:
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={
                    "WWW-Authenticate": f'Bearer resource_metadata="{PUBLIC_URL}/.well-known/oauth-protected-resource"'
                },
            )
        return await call_next(request)


app.add_middleware(OAuthMiddleware)

if __name__ == "__main__":
    run_kwargs = {"host": "127.0.0.1", "port": PORT}
    if sys.stdout is None:
        run_kwargs["log_config"] = None
    uvicorn.run(app, **run_kwargs)
