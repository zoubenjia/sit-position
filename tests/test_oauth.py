"""OAuth 流程 mock 测试"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from sit_monitor.cloud.oauth_server import OAuthCallbackServer


class TestOAuthCallbackServer:
    def test_server_starts_on_random_port(self):
        server = OAuthCallbackServer()
        server.start()
        assert server.port > 0
        assert "localhost" in server.redirect_url
        assert server.state  # state 不为空
        server.stop()

    def test_state_is_unique(self):
        s1 = OAuthCallbackServer()
        s2 = OAuthCallbackServer()
        assert s1.state != s2.state

    def test_redirect_url_format(self):
        server = OAuthCallbackServer()
        server.start()
        assert server.redirect_url.startswith("http://localhost:")
        assert "/callback" in server.redirect_url
        server.stop()

    def test_callback_with_correct_state(self):
        server = OAuthCallbackServer()
        server.start()

        import urllib.request
        url = f"http://localhost:{server.port}/callback?code=test123&state={server.state}"

        def fetch():
            time.sleep(0.1)
            try:
                urllib.request.urlopen(url, timeout=5)
            except Exception:
                pass

        t = threading.Thread(target=fetch, daemon=True)
        t.start()

        result = server.wait(timeout=5)
        assert result.code == "test123"
        assert result.error == ""

    def test_callback_with_wrong_state(self):
        server = OAuthCallbackServer()
        server.start()

        import urllib.request
        url = f"http://localhost:{server.port}/callback?code=test123&state=wrong"

        def fetch():
            time.sleep(0.1)
            try:
                urllib.request.urlopen(url, timeout=5)
            except Exception:
                pass

        t = threading.Thread(target=fetch, daemon=True)
        t.start()

        result = server.wait(timeout=5)
        assert result.code == ""
        assert "CSRF" in result.error

    def test_callback_with_error(self):
        server = OAuthCallbackServer()
        server.start()

        import urllib.request
        url = f"http://localhost:{server.port}/callback?error=access_denied&error_description=User+denied&state={server.state}"

        def fetch():
            time.sleep(0.1)
            try:
                urllib.request.urlopen(url, timeout=5)
            except Exception:
                pass

        t = threading.Thread(target=fetch, daemon=True)
        t.start()

        result = server.wait(timeout=5)
        assert result.code == ""
        assert "denied" in result.error.lower()


class TestSocialAuth:
    @patch("sit_monitor.cloud.social_auth.webbrowser")
    def test_google_oauth_no_url(self, mock_browser):
        """Supabase 未配置 Google OAuth 时应返回错误"""
        client = MagicMock()
        client.get_oauth_url.return_value = None

        from sit_monitor.cloud.social_auth import start_google_oauth
        result = start_google_oauth(client, timeout=1)
        assert result["success"] is False
        assert "Supabase" in result.get("error", "")
