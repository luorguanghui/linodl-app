import pytest

from linodl.core import downloader as downloader_module
from linodl.core.downloader import Downloader
from linodl.models.novel import NovelInfo


class _FakeTextElement:
    def __init__(self, page):
        self.page = page

    def inner_text(self):
        idx = min(self.page.reads, len(self.page.texts) - 1)
        self.page.reads += 1
        return self.page.texts[idx]


class _FakeStabilizingPage:
    def __init__(self, texts):
        self.texts = texts
        self.reads = 0
        self.waits = []

    def wait_for_selector(self, selector, timeout=0):
        assert selector == "#TextContent"

    def query_selector(self, selector):
        assert selector == "#TextContent"
        return _FakeTextElement(self)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


def test_download_stops_before_work_when_cancelled():
    class FakeBrowserSession:
        page = object()

        def start(self):
            pass

    downloader = Downloader(
        output_dir="unused",
        cancel_callback=lambda: True,
    )

    with pytest.raises(downloader_module.DownloadCancelled):
        downloader.download(
            [],
            set(),
            NovelInfo(title="测试作品"),
            browser_session=FakeBrowserSession(),
        )


def test_wait_for_text_content_ready_waits_for_stable_reordered_text():
    page = _FakeStabilizingPage([
        "乱序短文本",
        "乱序短文本",
        "修复后的稳定正文，包含全员生存且还站在理想位置的时机，是第一次出现。",
        "修复后的稳定正文，包含全员生存且还站在理想位置的时机，是第一次出现。",
    ])

    text = Downloader()._wait_for_text_content_ready(
        page,
        timeout_ms=1000,
        min_wait_ms=300,
        stable_ms=200,
        poll_ms=100,
    )

    assert "全员生存且还站在理想位置的时机，是第一次出现" in text
    assert page.reads >= 4


def test_wait_for_text_content_ready_does_not_accept_loading_failure_immediately():
    page = _FakeStabilizingPage([
        "內容加載失敗！請刷新或更換瀏覽器",
        "內容加載失敗！請刷新或更換瀏覽器",
        "真正正文已经由脚本重排完成",
        "真正正文已经由脚本重排完成",
    ])

    text = Downloader()._wait_for_text_content_ready(
        page,
        timeout_ms=1000,
        min_wait_ms=300,
        stable_ms=200,
        poll_ms=100,
    )

    assert text == "真正正文已经由脚本重排完成"


def test_extract_inline_images_preserves_paragraph_boundaries():
    items = [
        {"type": "text", "text": "正文A"},
        {"type": "image", "url": "https://img.readpai.com/book/1.jpg"},
        {"type": "text", "text": "正文B"},
    ]

    result = Downloader()._build_text_with_inline_images(items)

    assert result == {
        "text": "正文A\n\n[IMG:https://img.readpai.com/book/1.jpg]\n\n正文B",
        "urls": ["https://img.readpai.com/book/1.jpg"],
    }


def test_build_ordered_text_uses_visual_position_before_dom_order():
    items = [
        {"type": "text", "text": "第一段", "y": 100, "x": 10, "index": 0},
        {"type": "text", "text": "第三段", "y": 300, "x": 10, "index": 1},
        {"type": "text", "text": "第二段", "y": 200, "x": 10, "index": 2},
    ]

    result = Downloader()._build_ordered_content(items)

    assert result["text"] == "第一段\n\n第二段\n\n第三段"


def test_build_ordered_text_merges_fragments_from_same_paragraph():
    items = [
        {"type": "text", "text": "第一行", "y": 100, "x": 10, "index": 0, "blockIndex": 1},
        {"type": "text", "text": "第二行", "y": 130, "x": 10, "index": 1, "blockIndex": 1},
        {"type": "text", "text": "下一段", "y": 170, "x": 10, "index": 2, "blockIndex": 2},
    ]

    result = Downloader()._build_ordered_content(items)

    assert result["text"] == "第一行第二行\n\n下一段"
