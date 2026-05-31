"""Login helpers for linovelib.com."""

import re

from .browser import BASE_URL, is_cloudflare_challenge


def check_logged_in(page_or_session) -> bool:
    """Quick check if already logged in via persistent browser profile."""
    browser_session = page_or_session if hasattr(page_or_session, "page") else None
    page = browser_session.page if browser_session is not None else page_or_session
    try:
        if browser_session is not None:
            browser_session.navigate_with_challenge_retry(BASE_URL, "check-login")
            page = browser_session.page
        else:
            page.goto(BASE_URL, timeout=15000, wait_until="domcontentloaded")
        return _check_logged_in(page)
    except Exception:
        return False


def login(page_or_session, username: str, password: str):
    """Log into linovelib.com. Returns (success: bool, message: str)."""
    if not username or not password:
        return False, "login_failed: missing username or password"

    browser_session = page_or_session if hasattr(page_or_session, "page") else None
    page = browser_session.page if browser_session is not None else page_or_session

    # Check if already logged in before attempting login
    if check_logged_in(page_or_session):
        return True, "已处于登录状态"

    if browser_session is not None:
        browser_session.navigate_with_challenge_retry(f"{BASE_URL}/login.php", "login")
        page = browser_session.page
    else:
        page.goto(f"{BASE_URL}/login.php", timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

    try:
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)
        page.select_option('select[name="usecookie"]', "315360000")
        page.click('input[type="submit"]')
        page.wait_for_timeout(1000)
    except Exception as exc:
        return False, f"login_failed: {exc}"

    if is_cloudflare_challenge(page.content()) and browser_session is not None:
        if not browser_session.ensure_cloak("login-submit"):
            return False, "login_failed: cloudflare challenge"
        browser_session.wait_for_challenge_clear("login-submit")
        page = browser_session.page

    content = page.content()
    if "密码错误" in content or "密码不正确" in content:
        return False, "login_failed: 密码错误"
    if "用户名不存在" in content or "账号不存在" in content:
        return False, "login_failed: 用户名/账号不存在"
    if "验证码" in content:
        return False, "login_failed: 需要验证码验证，请切换 headed 模式手动处理"
    if "登录失败" in content:
        return False, "login_failed"

    if page.url.rstrip("/").endswith("login.php"):
        err = page.query_selector(".error, .alert, [class*='error']")
        if err:
            return False, f"login_failed: {err.inner_text().strip()}"
        return False, "login_failed: 请检查账号密码"

    if _check_logged_in(page):
        return True, "登录成功"

    return False, "login_failed: 登录状态未知，可尝试继续下载"


def _check_logged_in(page) -> bool:
    """Check if user is logged in by looking for user menu indicators."""
    try:
        content = page.content()
        if "退出" in content or "会员中心" in content or "书架" in content:
            return True
        if re.search(r"欢迎[您你]", content):
            return True
    except Exception:
        pass
    return False
