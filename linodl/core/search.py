"""Novel search for linovelib.com with browser and HTTP fallbacks."""

import re
import sys
import warnings

from ..models.novel import NovelInfo
from .browser import BASE_URL, BrowserSession, DEFAULT_USER_AGENT, is_cloudflare_challenge


SEARCH_URL = f"{BASE_URL}/S6/"
HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Referer": f"{BASE_URL}/",
}


class SearchEngine:
    def __init__(self, debug: bool = False, browser_session: BrowserSession | None = None):
        self.debug = debug
        self.browser_session = browser_session

    def search(self, keyword: str) -> list[NovelInfo]:
        """Search novels by keyword."""
        self._log("Trying browser form search...")
        html = self._try_browser_form(keyword)
        if html:
            results = self._parse_results(html)
            if results:
                return results

        self._log("Trying cloudscraper direct search...")
        html = self._try_cloudscraper_post(keyword)
        if html:
            results = self._parse_results(html)
            if results:
                return results

        self._log("Trying browser rank title match...")
        results = self._try_browser_direct(keyword)
        if results:
            return results

        self._log("Trying public listing pages...")
        results = self._try_public_listing_pages(keyword)
        if results:
            return results

        self._log("Trying Bing site search fallback...")
        results = self._try_bing_fallback(keyword)
        if results:
            return results

        self._log("Trying Google site search fallback...")
        results = self._try_google_fallback(keyword)
        if results:
            return results

        raise Exception("所有搜索方式均失败，请尝试直接提供小说目录 URL")

    def _log(self, msg: str):
        if self.debug:
            print(f"  [search] {msg}", file=sys.stderr)

    def _with_session(self, func):
        if self.browser_session is not None:
            self.browser_session.start()
            return func(self.browser_session)
        with BrowserSession(headless=True, anti_bot_mode="cloak") as session:
            return func(session)

    def _try_browser_direct(self, keyword: str) -> list[NovelInfo] | None:
        def run(session: BrowserSession):
            try:
                urls = [f"{BASE_URL}/top.html"] + [
                    f"{BASE_URL}/topfull/postdate/{page}.html" for page in range(1, 6)
                ]
                found = []
                seen = set()
                for url in urls:
                    session.navigate_with_challenge_retry(url, "search-browse")
                    html = session.content()
                    results = self._parse_results(html)
                    matched = self._filter_results_by_keyword(results, keyword)
                    for novel in matched:
                        if novel.novel_id and novel.novel_id not in seen:
                            seen.add(novel.novel_id)
                            found.append(novel)
                    if found:
                        return found
                return None
            except Exception as e:
                self._log(f"Browser direct error: {e}")
                return None

        return self._with_session(run)

    def _filter_results_by_keyword(
        self,
        results: list[NovelInfo],
        keyword: str,
    ) -> list[NovelInfo]:
        normalized = (keyword or "").strip().lower()
        if not normalized:
            return []
        return [
            novel for novel in results
            if normalized in (novel.title or "").lower()
        ]

    def _try_public_listing_pages(self, keyword: str) -> list[NovelInfo] | None:
        from .catalog import fetch_catalog

        urls = [
            *(f"{BASE_URL}/topfull/postdate/{page}.html" for page in range(1, 21)),
            *(f"{BASE_URL}/top/postdate/{page}.html" for page in range(1, 11)),
            *(f"{BASE_URL}/topfull/update/{page}.html" for page in range(1, 11)),
        ]
        found: list[NovelInfo] = []
        seen = set()
        empty_streak = 0
        for url in urls:
            try:
                html = fetch_catalog(url, browser_session=self.browser_session)
                matches = self._filter_results_by_keyword(self._parse_results(html), keyword)
                if matches:
                    empty_streak = 0
                    for novel in matches:
                        if novel.novel_id and novel.novel_id not in seen:
                            seen.add(novel.novel_id)
                            found.append(novel)
                else:
                    empty_streak += 1
                    if empty_streak >= 5:
                        break
            except Exception as e:
                self._log(f"Listing page failed {url}: {e}")
                empty_streak += 1
                if empty_streak >= 5:
                    break
        self._log(f"Listing pages found {len(found)} results across {len(seen)} URLs")
        return found or None

    def _try_browser_form(self, keyword: str) -> str | None:
        def run(session: BrowserSession):
            try:
                for attempt in range(3):
                    if not self._open_search_home(session):
                        return None
                    if not self._submit_search_form(session, keyword):
                        return None

                    html = self._content_after_navigation(session)

                    if self._looks_like_results(html):
                        return html

                    if is_cloudflare_challenge(html):
                        self._log("Cloudflare challenge on search results, resolving...")
                        if not session.ensure_cloak("search-form"):
                            return None

                        # Step 1: Clear challenge on the current /S6/ page itself.
                        # After Turnstile resolves, the page should auto-reload to results.
                        current_url = session.page.url
                        cleared = session.wait_for_challenge_clear(
                            "search-form", target_url=current_url, timeout_ms=120000
                        )
                        if cleared:
                            html = self._content_after_navigation(session)
                            if self._looks_like_results(html):
                                return html

                        # Step 2: /S6/ may still be blocked. Clear on home page,
                        # then re-submit search with the fresh clearance cookie.
                        self._log("Re-clearing on home page and re-submitting search...")
                        if not session.wait_for_challenge_clear("search-form", target_url=BASE_URL, timeout_ms=120000):
                            return None
                        if not self._submit_search_form(session, keyword):
                            return None
                        html = self._content_after_navigation(session)
                        if self._looks_like_results(html):
                            return html
                        if is_cloudflare_challenge(html):
                            self._log("Search still blocked after two clearance attempts")
                        continue

                    if attempt == 0 and "/S6" in session.page.url:
                        continue
            except Exception as e:
                self._log(f"Browser form error: {e}")
            return None

        return self._with_session(run)

    def _open_search_home(self, session: BrowserSession) -> bool:
        return session.navigate_with_challenge_retry(
            BASE_URL, "search-home", timeout_ms=300000
        )

    def _submit_search_form(self, session: BrowserSession, keyword: str) -> bool:
        selectors = [
            'input[name="searchkey"]',
            "#searchkey",
            "input.search-text",
            ".search-text",
            'form[name="t_frmsearch"] input[type="text"]',
        ]
        for sel in selectors:
            try:
                loc = session.page.locator(sel)
                loc.wait_for(state="visible", timeout=3000)
                loc.click()
                loc.fill(keyword)
                submit = session.page.locator(
                    'form[name="t_frmsearch"] input[type="submit"], input.search-btn'
                )
                try:
                    submit.first.click(timeout=2000)
                except Exception:
                    session.page.keyboard.press("Enter")
                return True
            except Exception:
                continue
        return False

    def _content_after_navigation(self, session: BrowserSession) -> str:
        try:
            session.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        last_error = None
        for _ in range(3):
            try:
                return session.content()
            except Exception as exc:
                last_error = exc
                session.page.wait_for_timeout(500)
        raise last_error

    def _looks_like_results(self, html: str) -> bool:
        if len(html) < 1000:
            return False
        if is_cloudflare_challenge(html):
            return False
        return bool(re.search(r"/novel/\d+\.html", html))

    def _try_cloudscraper_post(self, keyword: str) -> str | None:
        try:
            _suppress_requests_dependency_warning()
            import cloudscraper

            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            resp = scraper.post(SEARCH_URL, data={"searchkey": keyword}, headers=HEADERS, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 1000 and not is_cloudflare_challenge(resp.text):
                return resp.text
        except Exception:
            pass
        return None

    def _try_bing_fallback(self, keyword: str) -> list[NovelInfo] | None:
        return self._try_search_engine_fallback(
            keyword, "Bing",
            "https://www.bing.com/search",
            {"q": f"site:linovelib.com {keyword}", "setlang": "zh-cn"},
        )

    def _try_google_fallback(self, keyword: str) -> list[NovelInfo] | None:
        return self._try_search_engine_fallback(
            keyword, "Google",
            "https://www.google.com/search",
            {"q": f"site:linovelib.com {keyword}", "hl": "zh-CN"},
        )

    def _try_search_engine_fallback(self, keyword: str, name: str, url: str, params: dict) -> list[NovelInfo] | None:
        try:
            _suppress_requests_dependency_warning()
            import cloudscraper

            scraper = cloudscraper.create_scraper()
            resp = scraper.get(
                url,
                params=params,
                headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                self._log(f"{name} returned {resp.status_code}")
                return None

            results = []
            seen = set()
            novel_matches = re.findall(
                r'<a[^>]*href="https?://(?:www\.)?linovelib\.com/novel/(\d+)(?:\.html)?"[^>]*>([^<]+)</a>',
                resp.text,
            )
            for nid, title in novel_matches:
                if nid in seen:
                    continue
                seen.add(nid)
                title_clean = re.sub(r"<[^>]+>", "", title).strip()
                if title_clean:
                    results.append(NovelInfo(
                        novel_id=nid,
                        title=title_clean,
                        catalog_url=f"{BASE_URL}/novel/{nid}/catalog",
                    ))
            self._log(f"{name} found {len(results)} results")
            return results[:30] if results else None
        except Exception as e:
            self._log(f"{name} error: {e}")
        return None

    def _parse_results(self, html: str) -> list[NovelInfo]:
        results = []
        by_id = {}

        # Generic UI labels that should NOT be treated as novel titles.
        _UI_LABELS = re.compile(
            r"^(书籍详情|查看详情|立即阅读|开始阅读|阅读原文|查看全文|更多详情|查看详情页|点击阅读)$"
        )

        novel_blocks = re.findall(
            r'<a[^>]*href="(/novel/(\d+)\.html)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        for href, nid, inner in novel_blocks:
            novel = by_id.get(nid)
            if novel is None:
                novel = NovelInfo(novel_id=nid, catalog_url=f"{BASE_URL}/novel/{nid}/catalog")
                by_id[nid] = novel
                results.append(novel)
            title_match = re.search(r"<h3[^>]*>([^<]+)</h3>", inner)
            if title_match:
                novel.title = title_match.group(1).strip()
            elif not novel.title and not re.search(r"<[^>]+>", inner):
                title = inner.strip()
                if title and not _UI_LABELS.match(title):
                    novel.title = title

        if not results:
            list_items = re.findall(
                r'<li[^>]*>.*?<a[^>]*href="(/novel/(\d+)\.html)"[^>]*>([^<]+)</a>',
                html,
                re.DOTALL,
            )
            for href, nid, title in list_items:
                if nid not in by_id:
                    results.append(NovelInfo(
                        novel_id=nid,
                        title=title.strip(),
                        catalog_url=f"{BASE_URL}/novel/{nid}/catalog",
                    ))
                    by_id[nid] = results[-1]

        if not results:
            broad = re.findall(r'href="(/novel/(\d+)\.html)"', html)
            for href, nid in broad:
                if nid not in by_id:
                    results.append(NovelInfo(
                        novel_id=nid,
                        catalog_url=f"{BASE_URL}/novel/{nid}/catalog",
                    ))
                    by_id[nid] = results[-1]

        for novel in results:
            am = re.search(
                rf'/novel/{novel.novel_id}\.html.*?作者[：:]\s*<a[^>]*>([^<]+)</a>',
                html,
                re.DOTALL,
            )
            if am:
                novel.author = am.group(1).strip()
                continue

            rank_author = re.search(
                rf'/novel/{novel.novel_id}\.html.*?rank_d_b_cate[^>]*title="([^"]+)"',
                html,
                re.DOTALL,
            )
            if rank_author:
                novel.author = rank_author.group(1).strip()
        return results[:50]


def _suppress_requests_dependency_warning():
    warnings.filterwarnings("ignore", message="urllib3 .* doesn't match.*")
    warnings.filterwarnings("ignore", message=".*charset_normalizer.*")
    try:
        from requests.exceptions import RequestsDependencyWarning

        warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
    except Exception:
        pass
