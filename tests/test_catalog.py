from linodl.core.catalog import parse_catalog


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
