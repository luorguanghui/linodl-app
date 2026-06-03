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
        novel_id_match = re.search(r'/novel/(\d+)/', block)
        novel_id = novel_id_match.group(1) if novel_id_match else None

        # Check if this volume has javascript:cid(0) links that need URL resolution
        has_js_links = any("javascript:" in url for url, _ in chapters)

        # If has JS links, fetch the volume page to get correct URLs
        volume_page_urls = {}
        if has_js_links and novel_id:
            # Find the volume page URL
            vol_page_match = re.search(r'/novel/\d+/(vol_\d+)\.html', block)
            if vol_page_match:
                vol_page_url = f"https://www.linovelib.com/novel/{novel_id}/{vol_page_match.group(1)}.html"
                try:
                    import cloudscraper
                    import time
                    time.sleep(1)  # Avoid rate limiting
                    scraper = cloudscraper.create_scraper()
                    resp = scraper.get(vol_page_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    }, timeout=15)
                    if resp.status_code == 200:
                        # Extract chapter URLs from volume page
                        vol_chapters = re.findall(
                            r'<a[^>]*href="(/novel/\d+/\d+\.html)"[^>]*>([^<]+)</a>',
                            resp.text
                        )
                        for url, title in vol_chapters:
                            title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
                            volume_page_urls[title] = url
                except Exception:
                    pass  # Fall back if volume page fetch fails

        for url, title in chapters:
            title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
            # Skip non-chapter links (volume covers, etc.)
            if not re.match(r'/novel/\d+/\d+\.html$', url) and "javascript:" not in url:
                continue

            # Resolve javascript:cid(0) links
            if "javascript:" in url:
                # Try to get URL from volume page first
                if title in volume_page_urls:
                    url = volume_page_urls[title]
                else:
                    # Skip chapters that can't be resolved
                    volume.skipped_chapters.append({
                        "title": title,
                        "url": url,
                        "reason": "content_unavailable",
                    })
                    continue

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
