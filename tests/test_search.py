from linodl.core.search import SearchEngine
from linodl.models.novel import NovelInfo


def test_search_tries_direct_form_before_rank_and_listing(monkeypatch):
    engine = SearchEngine()
    calls = []

    monkeypatch.setattr(
        engine,
        "_try_browser_form",
        lambda keyword: calls.append("form") or '<a href="/novel/1.html">Direct Hit</a>',
    )
    monkeypatch.setattr(
        engine,
        "_try_browser_direct",
        lambda keyword: calls.append("rank") or [NovelInfo(novel_id="2", title="Rank Hit")],
    )
    monkeypatch.setattr(
        engine,
        "_try_public_listing_pages",
        lambda keyword: calls.append("listing") or [NovelInfo(novel_id="3", title="Listing Hit")],
    )

    results = engine.search("Direct")

    assert calls == ["form"]
    assert [(r.title, r.novel_id) for r in results] == [("Direct Hit", "1")]


def test_filter_results_by_keyword_returns_only_title_matches():
    engine = SearchEngine()
    results = [
        NovelInfo(novel_id="1", title="义妹生活"),
        NovelInfo(novel_id="2", title="欢迎来到实力至上主义的教室"),
    ]

    assert engine._filter_results_by_keyword(results, "义妹") == [results[0]]


def test_filter_results_by_keyword_does_not_return_unmatched_rank_list():
    engine = SearchEngine()
    results = [
        NovelInfo(novel_id="3080", title="我当备胎女友也没关系。"),
        NovelInfo(novel_id="5031", title="转移到异世界后，与美少女皇女结婚的我成为皇帝"),
    ]

    assert engine._filter_results_by_keyword(results, "不存在的搜索词xyz123") == []


def test_parse_public_listing_results_supports_non_rank_titles():
    html = """
    <div class="rank_d_b_name" title="无止尽的冬天，毁坏的梦之国">
      <a href="/novel/5105.html" target="_blank">无止尽的冬天，毁坏的梦之国</a>
    </div>
    <div class="rank_d_b_cate" title="八目迷">
      <a href="https://www.linovelib.com/authorarticle/八目迷.html">八目迷</a>
    </div>
    """
    engine = SearchEngine()

    results = engine._parse_results(html)
    matched = engine._filter_results_by_keyword(results, "无止尽的冬天")

    assert [(r.title, r.novel_id, r.author) for r in matched] == [
        ("无止尽的冬天，毁坏的梦之国", "5105", "八目迷")
    ]


def test_parse_results_updates_blank_cover_link_with_later_title_link():
    html = """
    <a href="/novel/5105.html"><img alt="无止尽的冬天，毁坏的梦之国"></a>
    <div class="rank_d_b_name" title="无止尽的冬天，毁坏的梦之国">
      <a href="/novel/5105.html" target="_blank">无止尽的冬天，毁坏的梦之国</a>
    </div>
    """
    engine = SearchEngine()

    results = engine._parse_results(html)

    assert [(r.title, r.novel_id) for r in results] == [
        ("无止尽的冬天，毁坏的梦之国", "5105")
    ]


class _SearchChallengeSession:
    def __init__(self):
        self.wait_target_urls = []
        self.page = self
        self.url = ""

    def start(self):
        pass

    def ensure_cloak(self, reason):
        return True

    def wait_for_challenge_clear(self, reason, target_url=None, timeout_ms=None):
        self.wait_target_urls.append(target_url)
        return True


def test_browser_form_replays_search_after_challenge_with_home_target(monkeypatch):
    session = _SearchChallengeSession()
    engine = SearchEngine(browser_session=session)
    calls = []
    htmls = iter([
        "<html><title>Just a moment...</title><div>verify you are human</div></html>",
        '<a href="/novel/1.html">Direct Hit</a>' + (" " * 1000),
    ])

    monkeypatch.setattr(engine, "_open_search_home", lambda sess: calls.append("open") or True)
    monkeypatch.setattr(
        engine,
        "_submit_search_form",
        lambda sess, keyword: calls.append(f"submit:{keyword}") or True,
    )
    monkeypatch.setattr(engine, "_content_after_navigation", lambda sess: next(htmls))

    assert engine._try_browser_form("Direct").startswith('<a href="/novel/1.html">Direct Hit</a>')
    assert calls == ["open", "submit:Direct"]
    assert session.wait_target_urls == [""]


def test_parse_results_does_not_overwrite_title_with_ui_label():
    """Regression: search results should not show '书籍详情' as the novel title.

    The site renders multiple <a href="/novel/{id}.html"> per result card.
    A later '书籍详情' button link was overwriting the correctly-parsed title.
    """
    html = """
    <a href="/novel/123.html"><img src="cover.jpg"></a>
    <h3><a href="/novel/123.html">真正的书名</a></h3>
    <a href="/novel/123.html">书籍详情</a>
    """
    engine = SearchEngine()
    results = engine._parse_results(html)

    assert len(results) == 1
    assert results[0].title == "真正的书名"
    assert results[0].novel_id == "123"


def test_parse_results_filters_all_generic_ui_labels():
    """No generic UI label should survive as a title."""
    for label in ["书籍详情", "查看详情", "立即阅读", "开始阅读"]:
        html = f'<a href="/novel/999.html">{label}</a>'
        engine = SearchEngine()
        results = engine._parse_results(html)
        assert results[0].title == "", f"'{label}' should not be a title"
