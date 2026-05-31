#!/usr/bin/env python3
"""
linovelib.com novel downloader.
Usage: python download_novel.py [catalog_url]

If URL is not provided, reads catalog.html from current directory.
Set LINOVELIB_USER and LINOVELIB_PASS environment variables for login.
"""

import re
import os
import sys
import time
import random
import urllib.request
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.linovelib.com"
OUTPUT_DIR = "novel_output"

USERNAME = os.environ.get("LINOVELIB_USER", "")
PASSWORD = os.environ.get("LINOVELIB_PASS", "")

def safe_print(*args, **kwargs):
    """Print without crashing on encoding errors."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Fallback: encode to ascii, replacing problematic chars
        safe_args = []
        for a in args:
            if isinstance(a, str):
                safe_args.append(a.encode('ascii', errors='replace').decode('ascii'))
            else:
                safe_args.append(str(a).encode('ascii', errors='replace').decode('ascii'))
        try:
            print(*safe_args, **kwargs)
        except:
            pass  # give up


def sanitize(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def fetch_catalog(url):
    """Fetch catalog page HTML from given URL."""
    import cloudscraper
    scraper = cloudscraper.create_scraper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    resp = scraper.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch catalog: HTTP {resp.status_code}")
    return resp.text


def parse_catalog(html):
    """Parse catalog HTML into structured list.
    Returns list of (volume_name, chapter_index, url, title, is_illustration)."""
    result = []
    novel_id = None
    id_match = re.search(r'/novel/(\d+)/catalog', html)
    if not id_match:
        id_match = re.search(r'"articleid"\s*:\s*[\'"](\d+)[\'"]', html)
    if not id_match:
        mo = re.search(r'/novel/(\d+)\.html', html)
        if mo:
            novel_id = mo.group(1)
    else:
        novel_id = id_match.group(1)

    blocks = re.split(r'<div class="volume clearfix">', html)[1:]

    for block in blocks:
        vol_match = re.search(r'<h2[^>]*><a[^>]*>([^<]+)</a>', block)
        vol_name = sanitize(vol_match.group(1)) if vol_match else "Unknown"

        chapters = re.findall(
            r'<a href="(/novel/\d+/\d+\.html)">([^<]+)</a>', block
        )

        text_idx = 0
        for url, title in chapters:
            if 'javascript:' in url:
                continue
            is_illus = title.strip() in ('插图', '插圖', '插画')
            if is_illus:
                result.append((vol_name, 0, url, title, True))
            else:
                text_idx += 1
                result.append((vol_name, text_idx, url, title, False))

    return result, novel_id


def download_image(url, filepath):
    """Download a single image to filepath."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.linovelib.com/",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(filepath, 'wb') as f:
            f.write(resp.read())


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Get catalog
    catalog_url = sys.argv[1] if len(sys.argv) > 1 else None
    if catalog_url:
        safe_print(f"Fetching catalog from {catalog_url} ...")
        catalog_html = fetch_catalog(catalog_url)
        with open('catalog.html', 'w', encoding='utf-8') as f:
            f.write(catalog_html)
    else:
        if not os.path.exists('catalog.html'):
            safe_print("No catalog.html found and no URL provided.")
            safe_print("Usage: python download_novel.py <catalog_url>")
            sys.exit(1)
        with open('catalog.html', 'r', encoding='utf-8') as f:
            catalog_html = f.read()

    all_chapters, novel_id = parse_catalog(catalog_html)
    text_count = sum(1 for _, _, _, _, is_illus in all_chapters if not is_illus)
    illus_count = sum(1 for _, _, _, _, is_illus in all_chapters if is_illus)
    safe_print(f"Novel ID: {novel_id}")
    safe_print(f"Total: {len(all_chapters)} ({text_count} text + {illus_count} illustrations)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='zh-CN',
        )
        page = context.new_page()

        # Login only when credentials are provided through the environment.
        if USERNAME and PASSWORD:
            safe_print("Logging in...")
            page.goto(f'{BASE_URL}/login.php', timeout=30000, wait_until='networkidle')
            page.wait_for_timeout(1000)
            page.fill('input[name="username"]', USERNAME)
            page.fill('input[name="password"]', PASSWORD)
            page.select_option('select[name="usecookie"]', '315360000')
            page.click('input[type="submit"]')
            page.wait_for_timeout(3000)
            safe_print("Login done.")
        else:
            safe_print("No LINOVELIB_USER/LINOVELIB_PASS set; continuing without login.")

        success = 0
        failed = 0
        total = len(all_chapters)
        prev_vol = None

        for i, (vol_name, ch_idx, url, title, is_illus) in enumerate(all_chapters):
            # Volume transition: check previous volume completeness
            if prev_vol and vol_name != prev_vol:
                vol_dir = os.path.join(OUTPUT_DIR, prev_vol)
                if os.path.exists(vol_dir):
                    expected = sum(1 for v, _, _, _, ill in all_chapters if v == prev_vol and not ill)
                    actual = len([f for f in os.listdir(vol_dir) if f.endswith('.txt')])
                    illus_dir = os.path.join(vol_dir, "插图")
                    illus_actual = len(os.listdir(illus_dir)) if os.path.exists(illus_dir) else 0
                    illus_expected = sum(1 for v, _, _, _, ill in all_chapters if v == prev_vol and ill)
                    status = "OK" if actual == expected else f"MISSING {expected - actual}"
                    safe_print(f"  [VOLUME CHECK] {prev_vol}: {actual}/{expected} text, {illus_actual}/{illus_expected} illus [{status}]")
                # Longer pause between volumes
                time.sleep(random.uniform(3, 5))

            try:
                prev_vol = vol_name
                vol_dir = os.path.join(OUTPUT_DIR, vol_name)
                os.makedirs(vol_dir, exist_ok=True)

                if is_illus:
                    # --- Illustration chapter ---
                    img_dir = os.path.join(vol_dir, "插图")
                    os.makedirs(img_dir, exist_ok=True)
                    existing = os.listdir(img_dir) if os.path.exists(img_dir) else []
                    # Check if already downloaded
                    if len(existing) > 0:
                        safe_print(f"[{i+1}/{total}] [{vol_name}] 插图... SKIP ({len(existing)} images)")
                        success += 1
                        continue

                    safe_print(f"[{i+1}/{total}] [{vol_name}] 插图...", end=' ')
                    page.goto(BASE_URL + url, timeout=30000, wait_until='networkidle')
                    page.wait_for_timeout(1500)

                    text_content = page.query_selector('#TextContent')
                    if not text_content:
                        safe_print("no TextContent")
                        failed += 1
                        continue

                    inner = text_content.inner_html()
                    # Check both src and data-src (lazy loading)
                    img_urls = re.findall(r'(?:src|data-src)="(https?://[^"]+)"', inner)
                    img_urls = [u for u in img_urls if 'readpai.com' in u and 'sloading' not in u]

                    if not img_urls:
                        safe_print("no images found")
                        failed += 1
                        continue

                    downloaded = 0
                    for img_idx, img_url in enumerate(img_urls):
                        ext = os.path.splitext(img_url.split('?')[0])[1] or '.jpg'
                        img_path = os.path.join(img_dir, f"{img_idx+1:02d}{ext}")

                        if os.path.exists(img_path):
                            continue
                        try:
                            download_image(img_url, img_path)
                            downloaded += 1
                        except Exception as e:
                            safe_print(f"img_err({e})", end=' ')

                    safe_print(f"OK ({downloaded} images)")
                    success += 1

                else:
                    # --- Text chapter ---
                    filename = f"{ch_idx:03d}_{sanitize(title)}.txt"
                    filepath = os.path.join(vol_dir, filename)

                    if os.path.exists(filepath):
                        safe_print(f"[{i+1}/{total}] [{vol_name}] {title[:25]}... SKIP (exists)")
                        success += 1
                        continue

                    base = re.sub(r'\.html$', '', url)
                    all_text = ""
                    page_no = 0

                    while True:
                        page_no += 1
                        page_url = f"{BASE_URL}{url}" if page_no == 1 else f"{BASE_URL}{base}_{page_no}.html"

                        if page_no == 1:
                            safe_print(f"[{i+1}/{total}] [{vol_name}] {title[:25]}...", end=' ')
                        else:
                            safe_print(f"pg{page_no}", end=' ')

                        page.goto(page_url, timeout=30000, wait_until='networkidle')
                        page.wait_for_timeout(1200)

                        text_elem = page.query_selector('#TextContent')
                        if not text_elem:
                            if page_no == 1:
                                safe_print("no TextContent")
                            break

                        page_text = text_elem.inner_text()
                        # Check for images (lazy-loaded via data-src too)
                        inner_html = text_elem.inner_html()
                        page_imgs = re.findall(r'(?:src|data-src)="(https?://[^"]+)"', inner_html)
                        page_imgs = [u for u in page_imgs if 'readpai.com' in u and 'sloading' not in u]

                        has_text = page_text and '沒有可閱讀' not in page_text and len(page_text) >= 10
                        # Chapter is image-based if it has many images but little text
                        is_image_chapter = (page_imgs and (not has_text or len(page_text) < 50 or len(page_imgs) > 5))

                        if page_no == 1 and is_image_chapter and page_imgs:
                            # Image-based chapter — download images from first page only
                            img_dir = os.path.join(vol_dir, "插图")
                            os.makedirs(img_dir, exist_ok=True)
                            for ii, img_url in enumerate(page_imgs):
                                ext = os.path.splitext(img_url.split('?')[0])[1] or '.jpg'
                                img_path = os.path.join(img_dir, f"{ch_idx:03d}_{sanitize(title)}_{ii+1:03d}{ext}")
                                if not os.path.exists(img_path):
                                    try:
                                        download_image(img_url, img_path)
                                    except:
                                        pass
                            safe_print(f"OK ({len(page_imgs)} images)")
                            success += 1
                            all_text = "__IMAGE_CHAPTER__"  # prevent fallthrough to failed counter
                            break

                        if not has_text:
                            if page_no == 1:
                                safe_print("blocked/empty")
                            break

                        all_text += page_text + "\n\n"

                        next_link = page.query_selector('.mlfy_page a:has-text("下一页")')
                        if not next_link:
                            break
                        time.sleep(random.uniform(1.5, 2.5))

                    if all_text:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(f"{title}\n{'='*50}\n\n{all_text}")
                        safe_print(f"OK ({len(all_text)} chars, {page_no} pages)")
                        success += 1
                    else:
                        if page_no == 1:
                            safe_print("SKIP")
                        failed += 1

                time.sleep(random.uniform(2.0, 3.5))

            except Exception as e:
                safe_print(f"ERROR: {e}")
                failed += 1
                time.sleep(random.uniform(5, 8))

            prev_vol = vol_name

        # Final volume check
        if prev_vol:
            vol_dir = os.path.join(OUTPUT_DIR, prev_vol)
            if os.path.exists(vol_dir):
                expected = sum(1 for v, _, _, _, ill in all_chapters if v == prev_vol and not ill)
                actual = len([f for f in os.listdir(vol_dir) if f.endswith('.txt')])
                illus_dir = os.path.join(vol_dir, "插图")
                illus_actual = len(os.listdir(illus_dir)) if os.path.exists(illus_dir) else 0
                illus_expected = sum(1 for v, _, _, _, ill in all_chapters if v == prev_vol and ill)
                status = "OK" if actual == expected else f"MISSING {expected - actual}"
                safe_print(f"  [VOLUME CHECK] {prev_vol}: {actual}/{expected} text, {illus_actual}/{illus_expected} illus [{status}]")

        safe_print(f"\n=== Done ===")
        safe_print(f"Success: {success}, Failed: {failed}")
        safe_print(f"Output: {os.path.abspath(OUTPUT_DIR)}")
        browser.close()


if __name__ == '__main__':
    main()
