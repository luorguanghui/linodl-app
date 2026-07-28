"""Shared browser session with optional CloakBrowser fallback."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from .profile_coordinator import profile_coordinator

# Use vendored cloakbrowser instead of system-installed version.
_VENDOR_DIR = str(Path(__file__).resolve().parent.parent.parent / "vendor")
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

# If a system-installed cloakbrowser was already imported, reload from vendor.
_vendor_init = os.path.join(_VENDOR_DIR, "cloakbrowser", "__init__.py")
if "cloakbrowser" in sys.modules:
    _mod = sys.modules["cloakbrowser"]
    _mod_file = getattr(_mod, "__file__", "") or ""
    if os.path.normpath(_mod_file) != os.path.normpath(_vendor_init):
        del sys.modules["cloakbrowser"]


BASE_URL = "https://www.linovelib.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}

ANTI_DETECT_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
"""


class ChallengeState(str, Enum):
    """Classification of the browser page returned by an anti-bot check."""

    NORMAL = "normal"
    CHALLENGE = "challenge"
    UNKNOWN = "unknown"


def assess_challenge(html: str | None) -> ChallengeState:
    """Classify page HTML without treating Cloudflare's generic JS as a block."""
    if not html or not html.strip():
        return ChallengeState.UNKNOWN

    text = html.lower()
    strong_markers = (
        "just a moment",
        "cf-browser-verify",
        "cf-challenge",
        "checking your browser",
        "verify you are human",
        "cf-turnstile",
    )
    if any(marker in text for marker in strong_markers):
        return ChallengeState.CHALLENGE

    if (
        'id="textcontent"' in text
        or '<div class="volume clearfix">' in text
        or "/novel/" in text and "<h1" in text
        or "<html" in text
        or "<body" in text
    ):
        return ChallengeState.NORMAL

    return ChallengeState.UNKNOWN


def is_cloudflare_challenge(html: str | None) -> bool:
    """Return True only for HTML with strong challenge evidence."""
    return assess_challenge(html) is ChallengeState.CHALLENGE


class BrowserSession:
    """Owns one persistent browser context and can restart it with CloakBrowser."""

    def __init__(
        self,
        headless: bool = True,
        anti_bot_mode: str = "cloak",
        proxy: str = "",
        geoip: bool = False,
        profile_dir: str = "",
        progress_callback: Callable[[str], None] | None = None,
        humanize: bool = True,
        cancel_event=None,
        profile_wait_callback: Callable[[str], None] | None = None,
    ):
        self.headless = headless
        self.anti_bot_mode = anti_bot_mode if anti_bot_mode in {"auto", "playwright", "cloak"} else "auto"
        self.proxy = proxy
        self.geoip = geoip
        self.profile_dir = profile_dir or str(Path.home() / ".linodl-browser")
        self.progress_callback = progress_callback
        self.humanize = humanize
        self.cancel_event = cancel_event
        self.profile_wait_callback = profile_wait_callback

        self.engine = ""
        self._playwright = None
        self.context = None
        self.page = None
        self._profile_lease = None

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _report(self, message: str):
        if self.progress_callback:
            self.progress_callback(message)
        else:
            print(f"  [browser] {message}", file=sys.stderr)

    def start(self, prefer_cloak: bool = False) -> "BrowserSession":
        if self.context:
            return self

        use_cloak = self.anti_bot_mode == "cloak" or (
            prefer_cloak and self.anti_bot_mode != "playwright"
        )
        engine = "cloak" if use_cloak else "playwright"
        lease = profile_coordinator.acquire(
            self._profile_path(engine),
            cancel_event=self.cancel_event,
            wait_callback=self.profile_wait_callback,
        )
        lease.__enter__()
        self._profile_lease = lease
        try:
            if use_cloak:
                self._start_cloak()
            else:
                self._start_playwright()
        except BaseException:
            self._release_profile_lease()
            raise
        return self

    def close(self):
        try:
            if self.context:
                self.context.close()
        finally:
            try:
                self.context = None
                self.page = None
                if self._playwright:
                    self._playwright.stop()
                    self._playwright = None
                self.engine = ""
            finally:
                self._release_profile_lease()

    def _release_profile_lease(self):
        lease = self._profile_lease
        self._profile_lease = None
        if lease is not None:
            lease.__exit__(None, None, None)

    def restart_with_cloak(self, reason: str = "") -> bool:
        """Restart the session with CloakBrowser when auto fallback is allowed."""
        if self.anti_bot_mode == "playwright" or self.engine == "cloak":
            return False
        self._report(
            "cloudflare_retry: opening visible CloakBrowser"
            f"{f' ({reason})' if reason else ''}"
        )
        self.close()
        self.start(prefer_cloak=True)
        return True

    def ensure_cloak(self, reason: str = "") -> bool:
        """Ensure we are using CloakBrowser, switching from Playwright if allowed."""
        if self.engine == "cloak":
            return True
        if self.anti_bot_mode == "playwright":
            return False
        return self.restart_with_cloak(reason)

    def navigate_with_challenge_retry(
        self,
        url: str,
        reason: str = "",
        timeout_ms: int = 300000,
    ) -> bool:
        """Navigate to a URL, handling Cloudflare challenges by switching to
        CloakBrowser and waiting for the user to complete verification.

        If verification sets a clearance cookie but leaves the browser on the
        challenge page, we reopen the target URL so the saved profile can use
        the new clearance state immediately.

        Returns True once the page loads without a challenge."""
        self.start()

        # Try initial navigation with retry on failure.
        loaded = False
        for attempt in range(3):
            try:
                wait = "domcontentloaded" if attempt < 2 else "commit"
                timeout = 30000 if attempt == 0 else (45000 if attempt == 1 else 60000)
                self.page.goto(url, timeout=timeout, wait_until=wait)
                if wait == "domcontentloaded":
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass
                loaded = True
                break
            except Exception as exc:
                self._report(
                    f"navigation attempt {attempt + 1} failed: {exc}"
                    f"{f' ({reason})' if reason else ''}"
                )
                if attempt < 2:
                    time.sleep(2)

        if not loaded:
            self._report(
                f"navigation failed after retries: {url}"
                f"{f' ({reason})' if reason else ''}"
            )
            return False

        if not self.page_has_challenge():
            return True

        previous_engine = self.engine
        if not self.ensure_cloak(reason):
            return False

        if previous_engine != "cloak":
            self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
            if not self.page_has_challenge():
                return True

        if not self.wait_for_challenge_clear(reason, timeout_ms, target_url=url):
            return False

        if not self.page_has_challenge():
            self._report(
                "verification passed, page content revealed"
                f"{f' ({reason})' if reason else ''}"
            )
            return True

        self._report(
            "challenge still present after verification, reloading"
            f"{f' ({reason})' if reason else ''}"
        )
        self.page.goto(url, timeout=45000, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        return not self.page_has_challenge()

    def goto(self, url: str, timeout: int = 30000, wait_until: str = "domcontentloaded"):
        self.start()
        return self.page.goto(url, timeout=timeout, wait_until=wait_until)

    def content(self) -> str:
        self.start()
        return self.page.content()

    def page_has_challenge(self) -> bool:
        try:
            return is_cloudflare_challenge(self.content())
        except Exception:
            return False

    def wait_for_challenge_clear(
        self,
        reason: str = "",
        timeout_ms: int = 300000,
        poll_ms: int = 1000,
        target_url: str | None = None,
    ) -> bool:
        """Wait for a Cloudflare challenge to be resolved.

        CloakBrowser with humanize=True in headed mode can auto-resolve
        Turnstile. We wait briefly for auto-resolve, then ask the user
        to click if the challenge persists."""
        if not self.page_has_challenge():
            return True
        if self.engine != "cloak":
            return False

        # Brief pause to let challenge page fully render before checking cookies.
        time.sleep(2)

        # Try reopening once if a valid clearance cookie already exists.
        if self._reopen_target_after_clearance(target_url, reason):
            return True

        # When humanize is enabled, wait briefly for auto-resolve first.
        if self.humanize:
            self._report(
                "cloudflare_retry: CloakBrowser 正在尝试自动通过验证..."
                f"{f' ({reason})' if reason else ''}"
            )
            auto_deadline = time.time() + 15
            while time.time() < auto_deadline:
                time.sleep(poll_ms / 1000)
                try:
                    if not self.page_has_challenge():
                        self._report("cloudflare_retry: auto-resolved verification")
                        return True
                except Exception:
                    pass

        self._report(
            "cloudflare_retry: 请在 CloakBrowser 窗口中点击「验证您是真人」\n"
            "完成后不要关闭浏览器窗口，程序会自动继续。\n"
            "最长等待 5 分钟。"
        )
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            time.sleep(poll_ms / 1000)
            try:
                if not self.page_has_challenge():
                    self._report("cloudflare_retry: verification passed")
                    # Navigate to target URL after verification so the saved
                    # profile picks up the new clearance cookie.
                    if target_url:
                        try:
                            self.page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                        except Exception:
                            pass
                    return True
            except Exception:
                pass
        self._report(
            "cloudflare_retry: verification timed out.\n"
            "已保存的 CloakBrowser profile 会继续复用:\n"
            f"  {self._profile_path('cloak')}"
        )
        return False

    def _has_cloudflare_clearance(self) -> bool:
        if not self.context:
            return False
        try:
            cookies = self.context.cookies(BASE_URL)
        except TypeError:
            cookies = self.context.cookies()
        except Exception:
            return False
        return any((cookie.get("name") or "").lower() == "cf_clearance" for cookie in cookies)

    def _clear_cloudflare_cookies(self) -> None:
        """Remove stale cf_clearance cookies so a fresh challenge is triggered."""
        if not self.context:
            return
        try:
            cookies = self.context.cookies(BASE_URL)
        except TypeError:
            cookies = self.context.cookies()
        except Exception:
            return
        stale = [c for c in cookies if (c.get("name") or "").lower() == "cf_clearance"]
        if stale:
            remaining = [c for c in cookies if (c.get("name") or "").lower() != "cf_clearance"]
            try:
                self.context.clear_cookies()
                for c in remaining:
                    self.context.add_cookies([c])
            except Exception:
                pass
            self._report("cloudflare_retry: cleared stale cf_clearance cookie")

    def _reopen_target_after_clearance(self, target_url: str | None, reason: str = "") -> bool:
        if not target_url or not self._has_cloudflare_clearance():
            return False
        self._report(
            "cloudflare_retry: clearance cookie saved, reopening target page"
            f"{f' ({reason})' if reason else ''}"
        )
        self.page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
        return not self.page_has_challenge()

    def _profile_path(self, engine: str) -> str:
        path = Path(os.path.expanduser(self.profile_dir)) / engine
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _set_default_page(self):
        pages = getattr(self.context, "pages", [])
        self.page = pages[0] if pages else self.context.new_page()
        if self.engine != "cloak":
            try:
                self.page.add_init_script(ANTI_DETECT_JS)
            except Exception:
                pass

    def _start_playwright(self):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        proxy = {"server": self.proxy} if self.proxy else None
        self.context = self._playwright.chromium.launch_persistent_context(
            self._profile_path("playwright"),
            headless=self.headless,
            user_agent=DEFAULT_USER_AGENT,
            locale="zh-CN",
            viewport=DEFAULT_VIEWPORT,
            proxy=proxy,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.engine = "playwright"
        self._set_default_page()

    def _start_cloak(self):
        from cloakbrowser import launch_persistent_context

        profile_path = self._profile_path("cloak")
        kwargs = self._cloak_launch_kwargs()

        try:
            self.context = launch_persistent_context(profile_path, **kwargs)
        except TypeError as exc:
            message = str(exc)
            if "humanize" not in message and "human_preset" not in message:
                raise
            # Older CloakBrowser versions don't support humanize.
            kwargs.pop("humanize", None)
            kwargs.pop("human_preset", None)
            self._report(
                "WARNING: humanize not supported by this CloakBrowser version. "
                "Browser will run without human-like input simulation."
            )
            self.context = launch_persistent_context(profile_path, **kwargs)

        self.engine = "cloak"
        self._set_default_page()

    def _cloak_launch_kwargs(self) -> dict:
        profile_path = self._profile_path("cloak")
        # Deterministic fingerprint seed per profile path for consistency.
        fingerprint_seed = str(
            int(hashlib.md5(profile_path.encode()).hexdigest()[:8], 16) % 90000 + 10000
        )

        kwargs = {
            "headless": self.headless,
            "args": [f"--fingerprint={fingerprint_seed}"],
            "humanize": self.humanize,
            "human_preset": "careful",
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
            if self.geoip:
                kwargs["geoip"] = True
            else:
                kwargs["locale"] = "zh-CN"
        else:
            kwargs["locale"] = "zh-CN"
        return kwargs
