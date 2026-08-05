import threading

from linodl.core.catalog import parse_catalog


def test_parse_catalog_resolves_javascript_chapters_across_volumes_concurrently(
    monkeypatch,
):
    """Catalog parsing must not resolve protected chapter links one volume at a time."""
    import linodl.core.catalog as catalog_module

    barrier = threading.Barrier(2)

    def fetch_volume_page_urls(url):
        barrier.wait(timeout=1)
        if url.endswith("vol_1.html"):
            return {"隐藏章节一": "/novel/8/101.html"}
        return {"隐藏章节二": "/novel/8/201.html"}

    monkeypatch.setattr(
        catalog_module,
        "_fetch_volume_page_urls",
        fetch_volume_page_urls,
        raising=False,
    )

    html = """
    <a href="/novel/8/catalog">目录</a>
    <div class="volume clearfix">
      <h2><a href="/novel/8/vol_1.html">第一卷</a></h2>
      <ul><li><a href="javascript:cid(0)">隐藏章节一</a></li></ul>
    <div class="volume clearfix">
      <h2><a href="/novel/8/vol_2.html">第二卷</a></h2>
      <ul><li><a href="javascript:cid(0)">隐藏章节二</a></li></ul>
    """

    volumes, _ = parse_catalog(html)

    assert [[chapter.url for chapter in volume.chapters] for volume in volumes] == [
        ["/novel/8/101.html"],
        ["/novel/8/201.html"],
    ]


def test_parse_catalog_inferrs_a_masked_chapter_between_consecutive_urls(monkeypatch):
    """A numeric one-chapter gap needs no volume-page request to recover its URL."""
    import linodl.core.catalog as catalog_module

    def volume_page_must_not_load(_url):
        raise AssertionError("a consecutive chapter URL must be inferred locally")

    monkeypatch.setattr(
        catalog_module,
        "_fetch_volume_page_urls",
        volume_page_must_not_load,
    )
    html = """
    <a href="/novel/8/catalog">目录</a>
    <div class="volume clearfix">
      <h2><a href="/novel/8/vol_1.html">第一卷</a></h2>
      <ul>
        <li><a href="/novel/8/100.html">前章</a></li>
        <li><a href="javascript:cid(0)">隐藏章节</a></li>
        <li><a href="/novel/8/102.html">后章</a></li>
      </ul>
    """

    volumes, _ = parse_catalog(html)

    assert [chapter.url for chapter in volumes[0].chapters] == [
        "/novel/8/100.html",
        "/novel/8/101.html",
        "/novel/8/102.html",
    ]


def test_parse_catalog_extracts_novel_info_volumes_and_chapters():
    html = """
    <html>
      <body>
        <h1>测试小说</h1>
        <p>作者：<a>测试作者</a></p>
        <a href="/novel/123/catalog">目录</a>
        <div class="volume clearfix">
          <h2><a>第一卷</a></h2>
          <ul>
            <li><a href="/novel/123/100.html">插图</a></li>
            <li><a href="/novel/123/101.html">第一章</a></li>
            <li><a href="/novel/123/102.html">第二章</a></li>
          </ul>
        </div>
      </body>
    </html>
    """

    volumes, info = parse_catalog(html)

    assert info.novel_id == "123"
    assert info.title == "测试小说"
    assert info.author == "测试作者"
    assert info.catalog_url == "https://www.linovelib.com/novel/123/catalog"
    assert len(volumes) == 1
    assert volumes[0].name == "第一卷"
    assert volumes[0].text_count == 2
    assert volumes[0].illus_count == 1
    assert volumes[0].chapters[1].index == 1
    assert volumes[0].chapters[1].title == "第一章"
