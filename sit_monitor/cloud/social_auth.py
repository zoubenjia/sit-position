"""社交登录：Google OAuth 流程封装。

设计原则：
- 匿名（设备）认证保持默认
- 社交登录可选绑定，绑定后 user_id 不变
- 绑定前明确提示用户数据关联含义
"""

import logging
import webbrowser

from sit_monitor.cloud.oauth_server import OAuthCallbackServer
from sit_monitor.i18n import t

log = logging.getLogger(__name__)


def start_google_oauth(cloud_client, timeout: float = 120) -> dict:
    """启动 Google OAuth 流程。

    1. 启动本地回调服务器
    2. 获取 Supabase OAuth URL（带 state 参数）
    3. 打开浏览器
    4. 等待回调
    5. 交换 token

    Returns:
        {"success": True/False, "message": "...", "url": "..."(如需手动打开)}
    """
    # 启动本地回调服务器（随机端口）
    server = OAuthCallbackServer()
    server.start()

    redirect_url = server.redirect_url

    # 获取 OAuth URL
    oauth_url = cloud_client.get_oauth_url(
        provider="google",
        redirect_url=redirect_url,
    )
    if not oauth_url:
        server.stop()
        return {"success": False, "error": t("social_auth.no_url")}

    # 追加 state 参数
    separator = "&" if "?" in oauth_url else "?"
    oauth_url_with_state = f"{oauth_url}{separator}state={server.state}"

    # 打开浏览器
    try:
        webbrowser.open(oauth_url_with_state)
    except Exception:
        server.stop()
        return {
            "success": False,
            "url": oauth_url_with_state,
            "message": t("social_auth.no_browser"),
        }

    # 等待回调
    result = server.wait(timeout=timeout)

    if result.error:
        return {"success": False, "error": result.error}

    if not result.code:
        return {"success": False, "error": t("social_auth.timeout")}

    # 处理 token（如果 Supabase 直接返回了 access_token）
    if result.code.startswith("token:"):
        token = result.code[6:]
        cloud_client.access_token = token
        profile = cloud_client.get_user_profile_from_provider()
        name = profile.get("full_name", "")
        name_suffix = f"（{name}）" if name else ""
        return {
            "success": True,
            "message": t("social_auth.google_linked", name_suffix=name_suffix),
            "profile": profile,
        }

    # 用 code 换取 session
    if cloud_client.exchange_code_for_session(result.code):
        profile = cloud_client.get_user_profile_from_provider()
        name = profile.get("full_name", "")
        name_suffix = f"（{name}）" if name else ""
        return {
            "success": True,
            "message": t("social_auth.google_linked", name_suffix=name_suffix),
            "profile": profile,
        }

    return {"success": False, "error": t("social_auth.token_failed")}
