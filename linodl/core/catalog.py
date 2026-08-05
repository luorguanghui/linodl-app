"""Catalog fetching and parsing for linovelib.com."""

import re
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

from ..models.novel import Chapter, NovelInfo, Volume
from .browser import BASE_URL, BrowserSession, is_cloudflare_challenge


class CatalogDirectFetchFailed(RuntimeError):
    """Raised when a catalog needs the browser fallback."""


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


def fetch_catalog_direct(catalog_url: str) -> str:
    """Fetch catalog HTML without starting a browser session."""
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
    except Exception as exc:
        raise CatalogDirectFetchFailed("direct catalog request failed") from exc
    raise CatalogDirectFetchFailed("direct catalog request was rejected")


def fetch_catalog_via_browser(catalog_url: str, session: BrowserSession) -> str:
    """Fetch catalog HTML through an already-configured browser session."""
    return _fetch_via_browser(normalize_catalog_url(catalog_url), session)


def fetch_catalog(catalog_url: str, browser_session=None) -> str:
    """Fetch catalog HTML, falling back to the browser when direct HTTP fails."""
    try:
        return fetch_catalog_direct(catalog_url)
    except CatalogDirectFetchFailed:
        pass

    if browser_session is not None:
        return fetch_catalog_via_browser(catalog_url, browser_session)

    with BrowserSession(headless=True, anti_bot_mode="cloak") as session:
        return fetch_catalog_via_browser(catalog_url, session)


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


def _fetch_volume_page_urls(vol_page_url: str) -> dict[str, str]:
    """Return chapter URLs that the catalog masks behind javascript links."""
    try:
        import cloudscraper

        scraper = cloudscraper.create_scraper()
        resp = scraper.get(
            vol_page_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        return {
            unescape(re.sub(r"<[^>]+>", "", title)).strip(): url
            for url, title in re.findall(
                r'<a[^>]*href="(/novel/\d+/\d+\.html)"[^>]*>([^<]+)</a>',
                resp.text,
            )
        }
    except Exception:
        return {}


def _resolve_volume_page_urls(volume_page_urls: dict[int, str]) -> dict[int, dict[str, str]]:
    """Resolve protected volume links concurrently, with a small site-friendly limit."""
    if not volume_page_urls:
        return {}

    resolved: dict[int, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(volume_page_urls))) as executor:
        futures = {
            executor.submit(_fetch_volume_page_urls, page_url): volume_index
            for volume_index, page_url in volume_page_urls.items()
        }
        for future in as_completed(futures):
            volume_index = futures[future]
            try:
                resolved[volume_index] = future.result()
            except Exception:
                resolved[volume_index] = {}
    return resolved


def _infer_masked_chapter_urls(chapters: list[tuple[str, str]]) -> dict[str, str]:
    """Recover a masked URL only when its two neighbouring chapter IDs agree."""
    inferred = {}
    for position, (url, raw_title) in enumerate(chapters):
        if "javascript:" not in url or position == 0 or position == len(chapters) - 1:
            continue
        previous = re.fullmatch(r"/novel/(\d+)/(\d+)\.html", chapters[position - 1][0])
        following = re.fullmatch(r"/novel/(\d+)/(\d+)\.html", chapters[position + 1][0])
        if (
            previous is None
            or following is None
            or previous.group(1) != following.group(1)
            or int(following.group(2)) != int(previous.group(2)) + 2
        ):
            continue
        title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        inferred[title] = (
            f"/novel/{previous.group(1)}/{int(previous.group(2)) + 1}.html"
        )
    return inferred


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

    volume_specs = []
    volume_page_urls = {}

    for volume_index, block in enumerate(blocks):
        vol_match = re.search(r"<h2[^>]*><a[^>]*>([^<]+)</a>", block)
        vol_name = sanitize(unescape(vol_match.group(1)).strip()) if vol_match else "Unknown"

        chapters = re.findall(
            r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL
        )

        volume = Volume(name=vol_name)
        text_idx = 0
        novel_id_match = re.search(r'/novel/(\d+)/', block)
        novel_id = novel_id_match.group(1) if novel_id_match else None

        has_js_links = any("javascript:" in url for url, _ in chapters)
        inferred_urls = _infer_masked_chapter_urls(chapters)
        has_unresolved_js_links = any(
            "javascript:" in url
            and unescape(re.sub(r"<[^>]+>", "", title)).strip() not in inferred_urls
            for url, title in chapters
        )
        if has_js_links and has_unresolved_js_links and novel_id:
            vol_page_match = re.search(r'/novel/\d+/(vol_\d+)\.html', block)
            if vol_page_match:
                volume_page_urls[volume_index] = (
                    f"https://www.linovelib.com/novel/{novel_id}/"
                    f"{vol_page_match.group(1)}.html"
                )

        volume_specs.append((vol_name, chapters, inferred_urls))

    resolved_volume_page_urls = _resolve_volume_page_urls(volume_page_urls)

    for volume_index, (vol_name, chapters, inferred_urls) in enumerate(volume_specs):
        volume = Volume(name=vol_name)
        text_idx = 0
        resolved_urls = {
            **inferred_urls,
            **resolved_volume_page_urls.get(volume_index, {}),
        }

        for url, title in chapters:
            title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
            # Skip non-chapter links (volume covers, etc.)
            if not re.match(r'/novel/\d+/\d+\.html$', url) and "javascript:" not in url:
                continue

            # Resolve javascript:cid(0) links
            if "javascript:" in url:
                # Try to get URL from volume page first
                if title in resolved_urls:
                    url = resolved_urls[title]
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
