"""Catalog fetching and parsing for linovelib.com."""

import re
import warnings
from html import unescape

from ..models.novel import Chapter, NovelInfo, Volume
from .browser import BASE_URL, BrowserSession, is_cloudflare_challenge


def sanitize(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def normalize_catalog_url(url: str) -> str:
    """Convert a novel detail page URL to a catalog URL."""
    if not url:
        return ""
    m = re.match(rf"{re.escape(BASE_URL)}/novel/(\d+)(?:/catalog|/|\.html)?$", url.rstrip("/"))
    if m:
        return f"{BASE_URL}/novel/{m.group(1)}/catalog"
    if "/catalog" not in url:
        m = re.search(r"/novel/(\d+)", url)
        if m:
            return f"{BASE_URL}/novel/{m.group(1)}/catalog"
    return url


def fetch_catalog(catalog_url: str, browser_session=None) -> str:
    """Fetch catalog HTML, normalising the URL and falling back to the browser."""
    catalog_url = normalize_catalog_url(catalog_url)

    try:
        _suppress_requests_dependency_warning()
        import cloudscraper

        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = scraper.get(catalog_url, headers=headers, timeout=30)
        if resp.status_code == 200 and not is_cloudflare_challenge(resp.text):
            return resp.text
        if browser_session is None:
            with BrowserSession(headless=True, anti_bot_mode="cloak") as session:
                return _fetch_via_browser(catalog_url, session)
    except Exception:
        if browser_session is None:
            with BrowserSession(headless=True, anti_bot_mode="cloak") as session:
                return _fetch_via_browser(catalog_url, session)

    return _fetch_via_browser(catalog_url, browser_session)


def _fetch_via_browser(catalog_url: str, session: BrowserSession) -> str:
    if not session.navigate_with_challenge_retry(catalog_url, "catalog"):
        raise Exception("catalog_failed: cloudflare challenge")
    html = session.content()
    if is_cloudflare_challenge(html):
        raise Exception("catalog_failed: cloudflare challenge")
    return html


def _suppress_requests_dependency_warning():
    warnings.filterwarnings("ignore", message="urllib3 .* doesn't match.*")
    warnings.filterwarnings("ignore", message=".*charset_normalizer.*")
    try:
        from requests.exceptions import RequestsDependencyWarning

        warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
    except Exception:
        pass


def parse_catalog(html: str):
    """Parse catalog HTML into (list[Volume], NovelInfo)."""
    novel_info = NovelInfo()
    volumes = []

    id_match = re.search(r"/novel/(\d+)/catalog", html)
    if not id_match:
        id_match = re.search(r'"articleid"\s*:\s*[\'"](\d+)[\'"]', html)
    if not id_match:
        id_match = re.search(r"/novel/(\d+)\.html", html)
    if id_match:
        novel_info.novel_id = id_match.group(1)

    title_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    if title_match:
        novel_info.title = unescape(title_match.group(1)).strip()

    author_match = re.search(r"作者[：:]\s*<a[^>]*>([^<]+)</a>", html)
    if author_match:
        novel_info.author = unescape(author_match.group(1)).strip()

    catalog_match = re.search(r'href="(/novel/\d+/catalog)"', html)
    if catalog_match:
        novel_info.catalog_url = BASE_URL + catalog_match.group(1)
    elif novel_info.novel_id:
        novel_info.catalog_url = f"{BASE_URL}/novel/{novel_info.novel_id}/catalog"

    blocks = re.split(r'<div class="volume clearfix">', html)[1:]

    for block in blocks:
        vol_match = re.search(r"<h2[^>]*><a[^>]*>([^<]+)</a>", block)
        vol_name = sanitize(unescape(vol_match.group(1)).strip()) if vol_match else "Unknown"

        chapters = re.findall(
            r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL
        )

        volume = Volume(name=vol_name)
        text_idx = 0
        last_chapter_id = None
        novel_id_match = re.search(r'/novel/(\d+)/', block)
        novel_id = novel_id_match.group(1) if novel_id_match else None

        # Pre-scan: find the first valid chapter ID for inferring URLs at the start
        first_valid_id = None
        for url, _ in chapters:
            id_match = re.match(r'/novel/\d+/(\d+)\.html$', url)
            if id_match:
                first_valid_id = int(id_match.group(1))
                break

        pending_js_chapters = []  # chapters with javascript: URLs waiting to be inferred

        for url, title in chapters:
            title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
            # Skip non-chapter links (volume covers, etc.)
            if not re.match(r'/novel/\d+/\d+\.html$', url) and "javascript:" not in url:
                continue

            # Try to infer URL for javascript:cid(0) links
            if "javascript:" in url:
                if novel_id and last_chapter_id is not None:
                    # Infer from previous chapter ID
                    inferred_id = last_chapter_id + 1
                    url = f"/novel/{novel_id}/{inferred_id}.html"
                    last_chapter_id = inferred_id
                elif novel_id and first_valid_id is not None:
                    # At the start of volume - infer from first valid ID
                    inferred_id = first_valid_id - 1
                    url = f"/novel/{novel_id}/{inferred_id}.html"
                    # Don't update last_chapter_id since we're going backwards
                    first_valid_id = inferred_id
                else:
                    # Can't infer URL, record as skipped
                    volume.skipped_chapters.append({
                        "title": title,
                        "url": url,
                        "reason": "content_unavailable",
                    })
                    continue
            else:
                # Extract chapter ID from URL
                id_match = re.match(r'/novel/\d+/(\d+)\.html$', url)
                if id_match:
                    last_chapter_id = int(id_match.group(1))

            is_illus = title in ("插图", "插圖", "插画", "插畫")
            if is_illus:
                volume.chapters.append(Chapter(
                    index=0,
                    url=url,
                    title=title,
                    is_illustration=True,
                    volume_name=vol_name,
                ))
            else:
                text_idx += 1
                volume.chapters.append(Chapter(
                    index=text_idx,
                    url=url,
                    title=title,
                    is_illustration=False,
                    volume_name=vol_name,
                ))

        volumes.append(volume)

    novel_info.chapter_count = sum(v.text_count for v in volumes)
    return volumes, novel_info
