"""Chapter and illustration download engine."""

import hashlib
import os
import random
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from urllib.parse import urljoin

from ..models.novel import Chapter, ChapterIssue, DownloadResult, NovelInfo, VerificationResult, Volume
from .browser import BASE_URL, is_cloudflare_challenge


def sanitize(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def img_fname(url: str) -> str:
    """Deterministic filename from image URL. Same URL → same filename always."""
    ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
    digest = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"{digest}{ext}"


def extract_image_urls(html: str) -> list[str]:
    """Extract real readpai image URLs and skip lazy-loading placeholders."""
    urls = re.findall(r'(?:src|data-src)=["\'](https?:)?//([^"\']+)["\']', html)
    result = []
    seen = set()
    for scheme, rest in urls:
        url = f"{scheme or 'https:'}//{rest}"
        if "readpai.com" not in url or "sloading" in url:
            continue
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def download_image(url: str, filepath: str, context=None):
    """Download a single image using the browser request context when available."""
    if context is not None:
        resp = context.request.get(
            url,
            headers={"Referer": "https://www.linovelib.com/"},
            timeout=30000,
        )
        if not resp.ok:
            raise RuntimeError(f"image_failed: HTTP {resp.status}")
        with open(filepath, "wb") as f:
            f.write(resp.body())
        return

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "Referer": "https://www.linovelib.com/",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(filepath, "wb") as f:
            f.write(resp.read())


class Downloader:
    def __init__(
        self,
        output_dir: str = "novel_output",
        delay_range: tuple = (0.3, 1.0),
        progress_callback: Callable = None,
    ):
        self.output_dir = output_dir
        self.delay_min, self.delay_max = delay_range
        self.progress_callback = progress_callback
        self.failed_chapters = []
        self._force_chapters = set()  # (volume_name, chapter_index) for retry

    def _report(self, msg: str):
        if self.progress_callback:
            self.progress_callback(msg)

    def _delay(self, scale: float = 1.0):
        time.sleep(random.uniform(
            self.delay_min * scale, self.delay_max * scale
        ))

    def _download_images_parallel(self, img_urls, img_dir, browser_session, prefix=""):
        """Download images in parallel. Filename is URL-based so duplicates
        are automatically skipped regardless of which chapter references them."""

        def _download_one(img_url):
            filename = img_fname(img_url)
            img_path = os.path.join(img_dir, filename)
            if os.path.exists(img_path):
                return filename
            try:
                download_image(img_url, img_path)
            except Exception:
                pass
            return filename

        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(_download_one, img_urls))

    def download(
        self,
        volumes: list[Volume],
        selected_volume_names: set,
        novel_info: NovelInfo,
        page=None,
        browser_session=None,
    ) -> DownloadResult:
        if browser_session is not None:
            browser_session.start()
            page = browser_session.page
        if page is None:
            raise ValueError("A Playwright page or BrowserSession is required")

        result = DownloadResult(
            novel_title=novel_info.title,
            total_text=sum(
                1
                for v in volumes if v.name in selected_volume_names
                for c in v.chapters if not c.is_illustration
            ),
            total_illus=sum(
                1
                for v in volumes if v.name in selected_volume_names
                for c in v.chapters if c.is_illustration
            ),
        )

        all_chapters = [
            (vol.name, ch)
            for vol in volumes if vol.name in selected_volume_names
            for ch in vol.chapters
        ]

        total = len(all_chapters)
        prev_vol = None

        for i, (vol_name, ch) in enumerate(all_chapters):
            if browser_session is not None:
                page = browser_session.page

            if prev_vol and vol_name != prev_vol:
                self._check_volume(prev_vol, all_chapters)
                time.sleep(random.uniform(0.5, 1.0))

            try:
                prev_vol = vol_name
                vol_dir = os.path.join(self.output_dir, vol_name)
                os.makedirs(vol_dir, exist_ok=True)

                if ch.is_illustration:
                    ok, skipped = self._download_illustration(
                        vol_dir, ch, i, total, page, browser_session
                    )
                else:
                    ok, skipped = self._download_text_chapter(
                        vol_dir, ch, i, total, page, browser_session
                    )

                if browser_session is not None:
                    page = browser_session.page

                if ok:
                    result.success += 1
                elif skipped:
                    result.skipped += 1
                else:
                    result.failed += 1
                    self.failed_chapters.append(f"{BASE_URL}{ch.url}")

                self._delay()

            except Exception as e:
                self._report(f"ERROR: {e}")
                self.failed_chapters.append(f"{BASE_URL}{ch.url}")
                result.failed += 1
                time.sleep(random.uniform(2, 3))

            prev_vol = vol_name

        if prev_vol:
            self._check_volume(prev_vol, all_chapters)

        result.output_dir = os.path.abspath(self.output_dir)
        return result

    def _load_page(self, page, browser_session, url: str, label: str):
        if browser_session is not None:
            browser_session.navigate_with_challenge_retry(url, label)
            return browser_session.page, browser_session.content()
        for attempt in range(2):
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            html = page.content()
            if not is_cloudflare_challenge(html):
                return page, html
        return page, page.content()

    def _download_illustration(self, vol_dir, ch: Chapter, idx, total, page, browser_session):
        img_dir = os.path.join(vol_dir, "插图")
        os.makedirs(img_dir, exist_ok=True)
        existing = os.listdir(img_dir) if os.path.exists(img_dir) else []
        force = (ch.volume_name, 0) in self._force_chapters

        if existing and not force:
            self._report(f"[{idx+1}/{total}] [{ch.volume_name}] 插图... SKIP ({len(existing)} images)")
            return False, True

        if force:
            self._report(f"[{idx+1}/{total}] [{ch.volume_name}] 插图... [RETRY] 强制重新检查")

        self._report(f"[{idx+1}/{total}] [{ch.volume_name}] 插图...")

        page, html = self._load_page(page, browser_session, urljoin(BASE_URL, ch.url), "illustration")
        text_content = page.query_selector("#TextContent")
        if not text_content:
            self._report("  no TextContent")
            return False, False

        img_urls = extract_image_urls(text_content.inner_html() or html)
        if not img_urls:
            self._report("  no images found")
            return False, False

        self._download_images_parallel(img_urls, img_dir, browser_session)
        self._report(f"  OK ({len(img_urls)} images)")
        return True, False

    def _download_text_chapter(self, vol_dir, ch: Chapter, idx, total, page, browser_session) -> tuple:
        filename = f"{ch.index:03d}_{sanitize(ch.title)}.txt"
        filepath = os.path.join(vol_dir, filename)
        force = (ch.volume_name, ch.index) in self._force_chapters

        if os.path.exists(filepath) and not force:
            if not self._has_missing_images(filepath, vol_dir):
                self._report(f"[{idx+1}/{total}] [{ch.volume_name}] {ch.title[:25]}... SKIP (exists)")
                return False, True
            self._report(f"[{idx+1}/{total}] [{ch.volume_name}] {ch.title[:25]}... [RETRY] 图片缺失，重新下载")

        if force:
            self._report(f"[{idx+1}/{total}] [{ch.volume_name}] {ch.title[:25]}... [RETRY] 强制重新下载")

        base = re.sub(r"\.html$", "", ch.url)
        all_text = ""
        page_no = 0
        img_dir = os.path.join(vol_dir, "插图")
        context = browser_session.page.context if browser_session else None
        ch_prefix = f"{ch.index:03d}_{sanitize(ch.title)}"

        while True:
            page_no += 1
            page_url = urljoin(
                BASE_URL,
                ch.url if page_no == 1 else f"{base}_{page_no}.html",
            )

            if page_no == 1:
                self._report(f"[{idx+1}/{total}] [{ch.volume_name}] {ch.title[:25]}...")
            else:
                self._report(f"  pg{page_no}")

            page, html = self._load_page(page, browser_session, page_url, "chapter")
            page_text = self._wait_for_text_content_ready(page)
            ordered_content = self._extract_ordered_content(page)
            if ordered_content:
                page_text = ordered_content["text"]
            text_elem = page.query_selector("#TextContent")
            if not text_elem:
                if page_no == 1:
                    self._report("  no TextContent")
                break

            inner_html = text_elem.inner_html()
            page_imgs = extract_image_urls(inner_html)
            has_text = bool(page_text) and "没有可阅读" not in page_text and len(page_text) >= 10
            is_image_chapter = page_imgs and (not has_text or len(page_text) < 50 or len(page_imgs) > 5)

            if page_no == 1 and is_image_chapter:
                os.makedirs(img_dir, exist_ok=True)
                self._download_images_parallel(page_imgs, img_dir, browser_session,
                                                prefix=ch_prefix)
                # Write a .txt file so the chapter is included in EPUB and
                # passes verification. Each image gets an [IMG:filename] marker.
                img_refs = "\n\n".join(f"[IMG:{img_fname(url)}]" for url in page_imgs)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"{ch.title}\n{'='*50}\n\n{img_refs}\n")
                self._report(f"  OK ({len(page_imgs)} images, image-only chapter)")
                return True, False

            if not has_text:
                if page_no == 1:
                    self._report("  empty_text")
                break

            # Extract text with inline image markers at correct positions.
            # Marker: [IMG:url] — replaced with [IMG:filename] after download.
            # Uses img_fname(url) so same URL always maps to same file,
            # eliminating duplicates across chapters and pages.
            inline_imgs = ordered_content if ordered_content and ordered_content["urls"] else None
            if inline_imgs:
                os.makedirs(img_dir, exist_ok=True)
                text_with_markers = inline_imgs["text"]
                for img_url in inline_imgs["urls"]:
                    local_name = img_fname(img_url)
                    img_path = os.path.join(img_dir, local_name)
                    if not os.path.exists(img_path):
                        try:
                            download_image(img_url, img_path, context)
                        except Exception:
                            pass
                    text_with_markers = text_with_markers.replace(
                        f"[IMG:{img_url}]", f"[IMG:{local_name}]"
                    )
                all_text += text_with_markers + "\n\n"
            else:
                all_text += page_text + "\n\n"

            next_href = self._next_same_chapter_href(page, base, page_no)
            if not next_href:
                break
            time.sleep(random.uniform(0.3, 0.6))

        if all_text:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"{ch.title}\n{'='*50}\n\n{all_text}")
            img_count = all_text.count("[IMG:")
            extra = f", {img_count} images" if img_count > 0 else ""
            self._report(f"  OK ({len(all_text)} chars, {page_no} pages{extra})")
            return True, False

        if page_no == 1:
            self._report("  SKIP")
        return False, False

    @staticmethod
    def _looks_like_loading_failure(text: str) -> bool:
        failure_markers = (
            "內容加載失敗",
            "内容加载失败",
            "沒有可閱讀",
            "没有可阅读",
            "请刷新或更换浏览器",
            "請刷新或更換瀏覽器",
        )
        return any(marker in text for marker in failure_markers)

    def _wait_for_text_content_ready(
        self,
        page,
        timeout_ms: int = 6000,
        min_wait_ms: int = 2500,
        stable_ms: int = 700,
        poll_ms: int = 100,
    ) -> str:
        """Wait for site-side chapter text reordering scripts to settle."""
        try:
            page.wait_for_selector("#TextContent", timeout=timeout_ms)
        except Exception:
            return ""

        elapsed = 0
        stable_elapsed = 0
        previous = None
        last_text = ""

        while elapsed <= timeout_ms:
            try:
                text_elem = page.query_selector("#TextContent")
                current = ((text_elem.inner_text() if text_elem else "") or "").strip()
            except Exception:
                current = ""

            if current == previous:
                stable_elapsed += poll_ms
            else:
                previous = current
                stable_elapsed = 0
            if current:
                last_text = current

            if (
                current
                and not self._looks_like_loading_failure(current)
                and elapsed >= min_wait_ms
                and stable_elapsed >= stable_ms
            ):
                return current

            if elapsed >= timeout_ms:
                break

            wait = min(poll_ms, timeout_ms - elapsed)
            try:
                page.wait_for_timeout(wait)
            except Exception:
                time.sleep(wait / 1000)
            elapsed += wait

        return last_text

    @staticmethod
    def _build_ordered_content(items: list[dict], require_image: bool = False) -> dict | None:
        parts = []
        urls = []
        last_was_break = False
        last_block = None
        ordered_items = sorted(
            items or [],
            key=lambda item: (
                item.get("y", item.get("index", 0)),
                item.get("x", 0),
                item.get("index", 0),
            ),
        )

        for item in ordered_items:
            item_type = item.get("type")
            if item_type == "text":
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                block = item.get("blockIndex")
                if (
                    parts
                    and block is not None
                    and block == last_block
                    and not last_was_break
                ):
                    parts[-1] += text
                else:
                    parts.append(text)
                last_block = block
                last_was_break = False
            elif item_type == "image":
                url = (item.get("url") or "").strip()
                if not url or "readpai.com" not in url or "sloading" in url:
                    continue
                parts.append(f"[IMG:{url}]")
                urls.append(url)
                last_block = None
                last_was_break = False
            elif item_type == "break" and parts and not last_was_break:
                parts.append("")
                last_block = None
                last_was_break = True

        while parts and parts[-1] == "":
            parts.pop()

        if require_image and not urls:
            return None
        if not parts:
            return None

        return {"text": "\n\n".join(parts), "urls": urls}

    @staticmethod
    def _build_text_with_inline_images(items: list[dict]) -> dict | None:
        return Downloader._build_ordered_content(items, require_image=True)

    def _extract_ordered_content(self, page) -> dict | None:
        """Extract #TextContent in visual order, preserving inline images."""
        try:
            items = page.evaluate("""() => {
                const content = document.querySelector('#TextContent');
                if (!content) return null;
                const items = [];
                let serial = 0;
                function visible(el) {
                    if (!el || el.nodeType !== 1) return true;
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                }
                function nearestBlock(node) {
                    let el = node.parentElement;
                    while (el && el !== content) {
                        if (['P', 'DIV', 'LI', 'H1', 'H2', 'H3'].includes(el.tagName)) {
                            return el;
                        }
                        el = el.parentElement;
                    }
                    return node.parentElement || content;
                }
                function fullUrl(src) {
                    if (!src) return '';
                    if (src.startsWith('http')) return src;
                    if (src.startsWith('//')) return 'https:' + src;
                    if (src.startsWith('/')) return window.location.origin + src;
                    return new URL(src, window.location.href).href;
                }
                function addTextNode(node) {
                    const value = node.nodeValue || '';
                    const block = nearestBlock(node);
                    const blockIndex = Array.prototype.indexOf.call(content.childNodes, block);
                    let current = null;
                    for (let i = 0; i < value.length; i++) {
                        const ch = value[i];
                        if (!ch.trim()) continue;
                        const range = document.createRange();
                        range.setStart(node, i);
                        range.setEnd(node, i + 1);
                        const rects = Array.from(range.getClientRects()).filter(
                            rect => rect.width || rect.height
                        );
                        range.detach();
                        if (!rects.length) continue;
                        const rect = rects[0];
                        const y = Math.round(rect.top + window.scrollY);
                        const x = Math.round(rect.left + window.scrollX);
                        const key = `${blockIndex}:${y}`;
                        if (!current || current.key !== key || x < current.lastX - 2) {
                            current = {
                                type: 'text',
                                text: '',
                                y,
                                x,
                                index: serial++,
                                blockIndex,
                                key,
                                lastX: x
                            };
                            items.push(current);
                        }
                        current.text += ch;
                        current.lastX = Math.round(rect.right + window.scrollX);
                    }
                }
                function addImage(img) {
                    if (!visible(img)) return;
                    const src = img.getAttribute('data-src') || img.currentSrc || img.src || '';
                    const full = fullUrl(src);
                    if (full && full.includes('readpai.com') && !full.includes('sloading')) {
                        const rect = img.getBoundingClientRect();
                        items.push({
                            type: 'image',
                            url: full,
                            y: Math.round(rect.top + window.scrollY),
                            x: Math.round(rect.left + window.scrollX),
                            index: serial++,
                            blockIndex: -1
                        });
                    }
                }
                function walk(node) {
                    if (node.nodeType === 3) {
                        addTextNode(node);
                    } else if (node.nodeType === 1 && visible(node)) {
                        if (node.tagName === 'BR') {
                            const rect = node.getBoundingClientRect();
                            items.push({
                                type: 'break',
                                y: Math.round(rect.top + window.scrollY),
                                x: Math.round(rect.left + window.scrollX),
                                index: serial++,
                                blockIndex: -1
                            });
                        } else if (node.tagName === 'IMG') {
                            addImage(node);
                        } else if (!['SCRIPT', 'STYLE'].includes(node.tagName)) {
                            for (const child of node.childNodes) walk(child);
                        }
                    }
                }
                for (const child of content.childNodes) walk(child);
                return items;
            }""")
            return self._build_ordered_content(items)
        except Exception:
            return None

    def _extract_inline_images(self, page) -> dict | None:
        """Walk #TextContent child nodes to get text with inline image markers.

        Returns {"text": "..., [IMG:http://...], ...", "urls": ["http://..."]} or None.
        Markers use the full URL so they can be replaced with deterministic filenames."""
        try:
            result = self._extract_ordered_content(page)
            if result and result["urls"]:
                return result
            return None
        except Exception:
            return None

    def _next_same_chapter_href(self, page, base: str, page_no: int) -> str | None:
        expected = f"{base}_{page_no + 1}.html"
        try:
            links = page.query_selector_all(".mlfy_page a")
            for link in links:
                href = link.get_attribute("href") or ""
                if href == expected or href.endswith(expected):
                    return href
        except Exception:
            pass
        return None

    @staticmethod
    def _has_missing_images(filepath: str, vol_dir: str) -> bool:
        """Check if a downloaded text file references any images that don't exist."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return False
        img_dir = os.path.join(vol_dir, "插图")
        for m in re.finditer(r"\[IMG:([^\]]+)\]", content):
            if not os.path.exists(os.path.join(img_dir, m.group(1))):
                return True
        return False

    def _check_volume(self, vol_name, all_chapters):
        vol_dir = os.path.join(self.output_dir, vol_name)
        if not os.path.exists(vol_dir):
            return
        expected = sum(1 for v, c in all_chapters if v == vol_name and not c.is_illustration)
        actual = len([f for f in os.listdir(vol_dir) if f.endswith(".txt")])
        illus_dir = os.path.join(vol_dir, "插图")
        illus_actual = len(os.listdir(illus_dir)) if os.path.exists(illus_dir) else 0
        illus_expected = sum(1 for v, c in all_chapters if v == vol_name and c.is_illustration)
        status = "OK" if actual == expected else f"MISSING {expected - actual}"
        self._report(
            f"  [VOLUME CHECK] {vol_name}: {actual}/{expected} text, "
            f"{illus_actual}/{illus_expected} illus [{status}]"
        )

    # ── Retry preparation ──────────────────────────────────────────────────

    def prepare_retry(self, verification):
        """Clean up problematic files and mark chapters for force re-download.

        Called before a retry round so that the normal download loop re-downloads
        chapters that were flagged as empty, truncated, or having image issues,
        instead of skipping them because files already exist on disk.
        """
        self._force_chapters.clear()

        for issue in verification.issues:
            vol_dir = os.path.join(self.output_dir, issue.volume_name)
            img_dir = os.path.join(vol_dir, "插图")
            is_illus = issue.chapter_title == "插图" or issue.chapter_index == 0
            ch_idx = 0 if is_illus else issue.chapter_index

            self._force_chapters.add((issue.volume_name, ch_idx))

            if issue.issue in ("empty", "truncated"):
                filename = f"{issue.chapter_index:03d}_{sanitize(issue.chapter_title)}.txt"
                filepath = os.path.join(vol_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    self._report(f"  [RETRY] 删除问题文件: {filename}")

            elif issue.issue == "image_missing":
                # Re-download the text chapter so inline images are re-fetched
                if not is_illus:
                    filename = f"{issue.chapter_index:03d}_{sanitize(issue.chapter_title)}.txt"
                    filepath = os.path.join(vol_dir, filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        self._report(f"  [RETRY] 删除章节(图片缺失): {filename}")

            elif issue.issue == "image_corrupt":
                m = re.search(r"corrupt or invalid image: (.+)$", issue.detail)
                if m:
                    img_path = os.path.join(img_dir, m.group(1))
                    if os.path.exists(img_path):
                        os.remove(img_path)
                        self._report(f"  [RETRY] 删除损坏图片: {m.group(1)}")

            elif issue.issue == "empty" and is_illus:
                # Illustration directory exists but is empty
                pass  # force flag on _download_illustration will handle it

    # ── Post-download verification ──────────────────────────────────────────

    MIN_CONTENT_CHARS = 100     # below this is flagged as truncated
    MIN_EMPTY_CHARS = 20        # below this is flagged as empty/error

    def verify_all(
        self,
        volumes: list[Volume],
        selected_volume_names: set,
    ) -> VerificationResult:
        """Verify every downloaded chapter for completeness and report issues."""
        result = VerificationResult()

        for vol in volumes:
            if vol.name not in selected_volume_names:
                continue
            vol_dir = os.path.join(self.output_dir, vol.name)

            for ch in vol.chapters:
                result.total_expected += 1

                if ch.is_illustration:
                    self._verify_illustration_chapter(vol_dir, ch, result)
                else:
                    self._verify_text_chapter(vol_dir, ch, result)

        result.total_actual = result.total_expected - result.missing
        result.complete = result.total_actual - result.empty - result.truncated - result.image_issues
        return result

    def _verify_text_chapter(self, vol_dir, ch: Chapter, result: VerificationResult):
        filename = f"{ch.index:03d}_{sanitize(ch.title)}.txt"
        filepath = os.path.join(vol_dir, filename)

        if not os.path.exists(filepath):
            result.missing += 1
            result.issues.append(ChapterIssue(
                volume_name=ch.volume_name,
                chapter_index=ch.index,
                chapter_title=ch.title,
                chapter_url=ch.url,
                issue="missing",
                detail=f"file not found: {filename}",
            ))
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            result.missing += 1
            result.issues.append(ChapterIssue(
                volume_name=ch.volume_name,
                chapter_index=ch.index,
                chapter_title=ch.title,
                chapter_url=ch.url,
                issue="missing",
                detail=f"read error: {e}",
            ))
            return

        # Strip header (title + ===... line)
        body = content
        header_end = content.find("=" * 50)
        if header_end != -1:
            body = content[header_end + 50:].strip()

        body_len = len(body)
        is_image_only = body_len > 0 and re.fullmatch(r"(\[IMG:[^\]]+\]\s*)+", body, re.DOTALL)

        if body_len < self.MIN_EMPTY_CHARS and not is_image_only:
            result.empty += 1
            result.issues.append(ChapterIssue(
                volume_name=ch.volume_name,
                chapter_index=ch.index,
                chapter_title=ch.title,
                chapter_url=ch.url,
                issue="empty",
                detail=f"content too short ({body_len} chars after header)",
            ))
        elif body_len < self.MIN_CONTENT_CHARS and not is_image_only:
            result.truncated += 1
            result.issues.append(ChapterIssue(
                volume_name=ch.volume_name,
                chapter_index=ch.index,
                chapter_title=ch.title,
                chapter_url=ch.url,
                issue="truncated",
                detail=f"content may be truncated ({body_len} chars)",
            ))

        # Check for inline image references — verify those images exist
        img_dir = os.path.join(vol_dir, "插图")
        for m in re.finditer(r"\[IMG:([^\]]+)\]", content):
            img_name = m.group(1)
            img_path = os.path.join(img_dir, img_name)
            if not os.path.exists(img_path):
                result.image_issues += 1
                result.issues.append(ChapterIssue(
                    volume_name=ch.volume_name,
                    chapter_index=ch.index,
                    chapter_title=ch.title,
                    chapter_url=ch.url,
                    issue="image_missing",
                    detail=f"referenced image not found: {img_name}",
                ))

    def _verify_illustration_chapter(self, vol_dir, ch: Chapter, result: VerificationResult):
        img_dir = os.path.join(vol_dir, "插图")
        if not os.path.isdir(img_dir):
            result.missing += 1
            result.issues.append(ChapterIssue(
                volume_name=ch.volume_name,
                chapter_index=0,
                chapter_title=ch.title,
                chapter_url=ch.url,
                issue="missing",
                detail="illustration directory not found",
            ))
            return

        images = [f for f in os.listdir(img_dir) if not f.startswith(".")]
        if not images:
            result.empty += 1
            result.issues.append(ChapterIssue(
                volume_name=ch.volume_name,
                chapter_index=0,
                chapter_title=ch.title,
                chapter_url=ch.url,
                issue="empty",
                detail="illustration directory is empty",
            ))
            return

        for fname in images:
            fpath = os.path.join(img_dir, fname)
            if not self._is_valid_image(fpath):
                result.image_issues += 1
                result.issues.append(ChapterIssue(
                    volume_name=ch.volume_name,
                    chapter_index=0,
                    chapter_title=ch.title,
                    chapter_url=ch.url,
                    issue="image_corrupt",
                    detail=f"corrupt or invalid image: {fname}",
                ))

    @staticmethod
    def _is_valid_image(filepath: str) -> bool:
        """Check if a file is a valid image by inspecting magic bytes."""
        if os.path.getsize(filepath) == 0:
            return False
        try:
            with open(filepath, "rb") as f:
                header = f.read(12)
            if len(header) < 4:
                return False
            # JPEG: FF D8 FF
            if header[:3] == b"\xff\xd8\xff":
                return True
            # PNG: 89 50 4E 47
            if header[:4] == b"\x89PNG":
                return True
            # GIF: GIF87a / GIF89a
            if header[:6] in (b"GIF87a", b"GIF89a"):
                return True
            # WebP: RIFF....WEBP
            if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
                return True
            # BMP: BM
            if header[:2] == b"BM":
                return True
            return False
        except Exception:
            return False
