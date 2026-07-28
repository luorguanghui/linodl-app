import sys
import types

from linodl.core import browser as browser_module
from linodl.core.browser import BASE_URL, BrowserSession, is_cloudflare_challenge
from linodl.core.downloader import extract_image_urls
from linodl.gui.workers import perform_cloudflare_warmup


def test_detects_cloudflare_challenge_markers():
    html = """
    <html><title>Just a moment...</title>
    <div id="cf-browser-verify"></div>
    <script src="/cdn-cgi/challenge-platform/h/b/orchestrate/managed/v1"></script>
    </html>
    """

    assert is_cloudflare_challenge(html)


def test_ignores_normal_chapter_html():
    html = '<div id="TextContent">正常章节正文</div>'

    assert not is_cloudflare_challenge(html)


def test_generic_cloudflare_script_on_normal_page_is_not_a_challenge():
    html = """
    <html>
      <body>
        <h1>正常作品页</h1>
        <a href="/novel/1.html">作品详情</a>
        <script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>
      </body>
    </html>
    """

    assert browser_module.assess_challenge(html) is browser_module.ChallengeState.NORMAL


def test_blank_html_has_unknown_challenge_state():
    assert browser_module.assess_challenge("") is browser_module.ChallengeState.UNKNOWN


def test_extract_image_urls_filters_loading_placeholders():
    html = """
    <img src="https://www.linovelib.com/sloading.gif">
    <img data-src="https://img.readpai.com/book/1.jpg?abc=1">
    <img src="https://img.readpai.com/book/sloading.png">
    <img src="https://cdn.example.com/ignored.jpg">
    <img src="//img.readpai.com/book/2.png">
    """

    assert extract_image_urls(html) == [
        "https://img.readpai.com/book/1.jpg?abc=1",
        "https://img.readpai.com/book/2.png",
    ]


class _FakeContext:
    def __init__(self, cookies=None):
        self._cookies = cookies or []

    def cookies(self, url=None):
        return self._cookies

    def close(self):
        pass


class _ChallengeThenClearPage:
    url = BASE_URL

    def __init__(self):
        self.goto_urls = []

    def content(self):
        if self.goto_urls:
            return '<html><a href="/novel/1.html">ok</a></html>'
        return "<html><title>Just a moment...</title><div>verify you are human</div></html>"

    def goto(self, url, timeout=30000, wait_until="domcontentloaded"):
        self.goto_urls.append(url)
        self.url = url


def test_wait_for_challenge_clear_reopens_target_after_clearance_cookie():
    session = BrowserSession()
    session.engine = "cloak"
    session.context = _FakeContext(cookies=[{"name": "cf_clearance", "value": "token"}])
    session.page = _ChallengeThenClearPage()

    assert session.wait_for_challenge_clear(
        "search-form",
        timeout_ms=50,
        poll_ms=1,
        target_url=BASE_URL,
    )
    assert session.page.goto_urls == [BASE_URL]


class _SwitchingSession(BrowserSession):
    def __init__(self):
        super().__init__(anti_bot_mode="auto")
        self.goto_urls = []

    def _start_playwright(self):
        self.engine = "playwright"
        self.context = _FakeContext()
        self.page = self

    def _start_cloak(self):
        self.engine = "cloak"
        self.context = _FakeContext()
        self.page = self

    def content(self):
        if self.engine == "playwright":
            return "<html><title>Just a moment...</title><div>cf-challenge</div></html>"
        return '<html><a href="/novel/1.html">ok</a></html>'

    def goto(self, url, timeout=30000, wait_until="domcontentloaded"):
        self.goto_urls.append((self.engine, url))
        self.url = url


def test_navigate_with_challenge_retry_reopens_url_after_switching_to_cloak():
    session = _SwitchingSession()

    assert session.navigate_with_challenge_retry(BASE_URL, "search-home", timeout_ms=50)
    assert session.goto_urls == [("playwright", BASE_URL), ("cloak", BASE_URL)]


class _HeadlessVerificationSession(BrowserSession):
    def __init__(self, verification_callback):
        super().__init__(
            headless=True,
            anti_bot_mode="cloak",
            verification_callback=verification_callback,
        )
        self.goto_urls = []
        self.verified = False

    def start(self, prefer_cloak=False):
        self.engine = "cloak"
        self.context = _FakeContext()
        self.page = self
        return self

    def close(self):
        self.context = None
        self.page = None
        self.engine = ""

    def goto(self, url, timeout=30000, wait_until="domcontentloaded"):
        self.goto_urls.append(url)

    def content(self):
        if self.verified:
            return '<html><a href="/novel/1.html">正常内容</a></html>'
        return "<html><title>Just a moment...</title><div>verify you are human</div></html>"


def test_headless_challenge_uses_visible_verification_callback_then_resumes():
    calls = []
    session = None

    def verify(url, reason):
        calls.append((url, reason))
        session.verified = True
        return True

    session = _HeadlessVerificationSession(verify)

    assert session.navigate_with_challenge_retry(BASE_URL, "search-home", timeout_ms=50)
    assert calls == [(BASE_URL, "search-home")]
    assert session.goto_urls == [BASE_URL, BASE_URL]


class _LaunchContext:
    pages = []

    def new_page(self):
        return types.SimpleNamespace(content=lambda: "")


def test_start_cloak_uses_cloakbrowser_fingerprint_defaults_without_custom_ua(monkeypatch, tmp_path):
    captured = {}

    def fake_launch_persistent_context(profile_path, **kwargs):
        captured["profile_path"] = profile_path
        captured["kwargs"] = kwargs
        return _LaunchContext()

    fake_module = types.SimpleNamespace(launch_persistent_context=fake_launch_persistent_context)
    monkeypatch.setitem(sys.modules, "cloakbrowser", fake_module)

    session = BrowserSession(profile_dir=str(tmp_path), anti_bot_mode="cloak")
    session._start_cloak()

    assert "user_agent" not in captured["kwargs"]
    assert captured["kwargs"]["humanize"] is True
    assert captured["kwargs"]["human_preset"] == "careful"
    assert captured["kwargs"]["headless"] is True


def test_start_cloak_geoip_omits_locale_and_custom_viewport(monkeypatch, tmp_path):
    captured = {}

    def fake_launch_persistent_context(profile_path, **kwargs):
        captured["profile_path"] = profile_path
        captured["kwargs"] = kwargs
        return _LaunchContext()

    fake_module = types.SimpleNamespace(launch_persistent_context=fake_launch_persistent_context)
    monkeypatch.setitem(sys.modules, "cloakbrowser", fake_module)

    session = BrowserSession(
        profile_dir=str(tmp_path),
        anti_bot_mode="cloak",
        proxy="socks5://127.0.0.1:1080",
        geoip=True,
    )
    session._start_cloak()

    assert captured["kwargs"]["geoip"] is True
    assert captured["kwargs"]["proxy"] == "socks5://127.0.0.1:1080"
    assert "locale" not in captured["kwargs"]
    assert "viewport" not in captured["kwargs"]


def test_project_loads_vendored_cloakbrowser_052():
    import cloakbrowser

    module_path = cloakbrowser.__file__.replace("\\", "/")
    assert "/vendor/cloakbrowser/" in module_path
    assert cloakbrowser.__version__ == "0.5.2"


class _BlankWarmupSession:
    def __init__(self, html="<html><head></head><body></body></html>"):
        self.started = False
        self.closed = False
        self.goto_urls = []
        self.page = self
        self._html = html

    def start(self, prefer_cloak=False):
        self.started = prefer_cloak

    def navigate_with_challenge_retry(self, url, reason="", timeout_ms=300000):
        self.goto_urls.append(url)
        return True

    def goto(self, url, timeout=30000, wait_until="domcontentloaded"):
        self.goto_urls.append(url)

    def wait_for_load_state(self, state, timeout=5000):
        pass

    def page_has_challenge(self):
        return False

    def content(self):
        return self._html

    def _has_cloudflare_clearance(self):
        return True

    def _clear_cloudflare_cookies(self):
        pass


def test_cloudflare_warmup_does_not_succeed_on_blank_page():
    session = _BlankWarmupSession()

    ok, message = perform_cloudflare_warmup(session, timeout_ms=50)

    assert ok is False
    assert "页面未加载完成" in message
    assert session.goto_urls == [BASE_URL]


def test_cloudflare_warmup_confirms_search_page_before_success():
    session = _BlankWarmupSession(
        '<html><body><a href="/novel/1/catalog">linovelib 小说搜索入口</a></body></html>'
    )

    ok, message = perform_cloudflare_warmup(session, timeout_ms=50)

    assert ok is True
    assert "验证成功完成" in message
    assert session.goto_urls == [BASE_URL, f"{BASE_URL}/S6/"]


def test_cloudflare_warmup_accepts_normal_pages_without_clearance_cookie():
    session = _BlankWarmupSession(
        '<html><body><a href="/novel/1/catalog">linovelib 小说搜索入口</a></body></html>'
    )
    session._has_cloudflare_clearance = lambda: False

    ok, message = perform_cloudflare_warmup(session, timeout_ms=20)

    assert ok is True
    assert "浏览器档案已保存" in message


class _SearchChallengeWarmupSession(_BlankWarmupSession):
    def __init__(self):
        super().__init__(
            '<html><body><a href="/novel/1/catalog">linovelib 小说搜索入口</a></body></html>'
        )
        self.challenge_urls = set()

    def page_has_challenge(self):
        return self.goto_urls[-1].endswith("/S6/") if self.goto_urls else False

    def navigate_with_challenge_retry(self, url, reason="", timeout_ms=300000):
        self.goto_urls.append(url)
        return True


def test_cloudflare_warmup_confirms_search_page_with_challenge_retry():
    session = _SearchChallengeWarmupSession()

    ok, message = perform_cloudflare_warmup(session, timeout_ms=50)

    assert ok is True
    assert "验证成功完成" in message
    assert session.goto_urls == [BASE_URL, f"{BASE_URL}/S6/"]
