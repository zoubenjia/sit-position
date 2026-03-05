"""本地 HTTP 服务器接收 OAuth 回调。

安全措施：
- 使用随机端口避免端口冲突
- 验证 state 参数防止 CSRF
- 服务器只处理一次请求后自动关闭
"""

import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from sit_monitor.i18n import t

log = logging.getLogger(__name__)


class OAuthCallbackResult:
    """OAuth 回调结果"""

    def __init__(self):
        self.code: str = ""
        self.error: str = ""
        self.ready = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    """处理 OAuth 回调请求"""

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        result: OAuthCallbackResult = self.server._oauth_result
        expected_state: str = self.server._oauth_state

        # 验证 state 参数（Supabase 托管 OAuth 时跳过，由 Supabase 负责 CSRF 验证）
        skip_state = getattr(self.server, "_oauth_skip_state", False)
        if not skip_state:
            state = params.get("state", [""])[0]
            if state != expected_state:
                result.error = t("oauth.csrf_error")
                self._send_response(t("oauth.auth_security_fail"), 400)
                result.ready.set()
                return

        # 检查 error
        error = params.get("error", [""])[0]
        if error:
            desc = params.get("error_description", [error])[0]
            result.error = desc
            self._send_response(t("oauth.auth_failed_desc", desc=desc), 400)
            result.ready.set()
            return

        # 获取 code
        code = params.get("code", [""])[0]
        if not code:
            # Supabase 可能把 access_token 放在 fragment 中
            # fragment 不会发送到服务器，需要 JS 转发
            self._send_fragment_extractor()
            return

        result.code = code
        self._send_response(t("oauth.auth_success"), 200)
        result.ready.set()

    def do_POST(self):
        """接收 JS 转发的 fragment 参数"""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        params = parse_qs(body)

        result: OAuthCallbackResult = self.server._oauth_result
        access_token = params.get("access_token", [""])[0]
        if access_token:
            result.code = f"token:{access_token}"
            self._send_response(t("oauth.auth_success_short"), 200)
        else:
            result.error = t("oauth.no_token")
            self._send_response(t("oauth.auth_failed"), 400)
        result.ready.set()

    def _send_response(self, message: str, status: int):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        close_hint = t("oauth.close_page")
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
        <title>Sit Monitor - OAuth</title>
        <style>body{{font-family:system-ui;display:flex;justify-content:center;
        align-items:center;height:100vh;margin:0;background:#f5f5f5}}
        .card{{background:white;padding:2rem;border-radius:1rem;box-shadow:0 2px 10px rgba(0,0,0,0.1);
        text-align:center;max-width:400px}}</style></head>
        <body><div class="card"><h2>{"✅" if status == 200 else "❌"} {message}</h2>
        <p>{close_hint}</p></div></body></html>"""
        self.wfile.write(html.encode())

    def _send_fragment_extractor(self):
        """返回 JS 页面，提取 URL fragment 中的 token 并 POST 回来"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        completing = t("oauth.completing")
        js_success = t("oauth.js_success")
        js_error = t("oauth.js_error")
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
        <title>Sit Monitor - OAuth</title></head><body>
        <p>{completing}</p>
        <script>
        const hash = window.location.hash.substring(1);
        if (hash) {{
            fetch(window.location.pathname, {{method: 'POST',
                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                body: hash
            }}).then(() => document.body.innerHTML = '<h2>{js_success}</h2>');
        }} else {{
            document.body.innerHTML = '<h2>{js_error}</h2>';
        }}
        </script></body></html>"""
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        log.debug("OAuth callback: %s", format % args)


class OAuthCallbackServer:
    """一次性 OAuth 回调 HTTP 服务器"""

    def __init__(self, port: int = 0):
        self.state = secrets.token_urlsafe(32)
        self.result = OAuthCallbackResult()
        self._server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        self._server._oauth_result = self.result
        self._server._oauth_state = self.state
        self._thread = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def redirect_url(self) -> str:
        return f"http://localhost:{self.port}/callback"

    def start(self):
        """启动服务器（后台线程，持续监听直到收到结果）"""
        def _serve_until_done():
            while not self.result.ready.is_set():
                self._server.handle_request()
        self._thread = threading.Thread(target=_serve_until_done, daemon=True)
        self._thread.start()

    def wait(self, timeout: float = 120) -> OAuthCallbackResult:
        """等待回调完成"""
        self.result.ready.wait(timeout=timeout)
        self._server.server_close()
        return self.result

    def stop(self):
        """手动关闭"""
        self._server.server_close()
