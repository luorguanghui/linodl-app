import queue
import sys
import threading
import types

import pytest


def test_catalog_worker_skips_browser_when_direct_fetch_succeeds(monkeypatch):
    """A healthy HTTP catalog response must not pay browser startup cost."""
    import linodl.gui.workers as workers_module

    messages = queue.Queue()
    direct_calls = []

    def direct_fetch(url):
        direct_calls.append(url)
        return "<html>catalog</html>"

    class BrowserMustNotStart:
        def __init__(self, *args, **kwargs):
            raise AssertionError("browser must not start for a direct catalog response")

    monkeypatch.setattr(workers_module, "fetch_catalog_direct", direct_fetch)
    monkeypatch.setattr(workers_module, "BrowserSession", BrowserMustNotStart)
    monkeypatch.setattr(
        workers_module,
        "parse_catalog",
        lambda html: (["volume"], "novel"),
    )
    worker = workers_module.CatalogWorker(
        "https://www.linovelib.com/novel/1/catalog",
        types.SimpleNamespace(),
        messages,
    )

    worker.run()

    result = next(data for event, data, _ in list(messages.queue) if event == "result")
    assert direct_calls == ["https://www.linovelib.com/novel/1/catalog"]
    assert result == (["volume"], "novel")


def test_catalog_worker_uses_browser_fallback_after_direct_fetch_failure(monkeypatch):
    """Cloudflare and network failures retain the configured browser path."""
    import linodl.gui.workers as workers_module

    messages = queue.Queue()
    sessions = []

    class BrowserSessionDouble:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            self.closed = False
            sessions.append(self)

        def start(self):
            self.started = True

        def close(self):
            self.closed = True

    def direct_fetch(_url):
        raise workers_module.CatalogDirectFetchFailed("challenge")

    monkeypatch.setattr(workers_module, "fetch_catalog_direct", direct_fetch)
    monkeypatch.setattr(workers_module, "BrowserSession", BrowserSessionDouble)
    monkeypatch.setattr(
        workers_module,
        "fetch_catalog_via_browser",
        lambda url, session: "<html>catalog</html>",
    )
    monkeypatch.setattr(
        workers_module,
        "parse_catalog",
        lambda html: (["volume"], "novel"),
    )
    worker = workers_module.CatalogWorker(
        "https://www.linovelib.com/novel/1/catalog",
        types.SimpleNamespace(
            headless=True,
            anti_bot_mode="cloak",
            proxy="",
            geoip=False,
            profile_dir="profile",
        ),
        messages,
    )

    worker.run()

    assert len(sessions) == 1
    assert sessions[0].started is True
    assert sessions[0].closed is True


def test_task_snapshot_survives_failure():
    from linodl.gui.tasks import (
        TaskInputSnapshot,
        TaskStatus,
        TaskStore,
    )

    store = TaskStore()
    inputs = TaskInputSnapshot(
        kind="download",
        query="",
        url="https://www.linovelib.com/novel/1/catalog",
        selected_volumes=("第一卷",),
        output_dir="novel_output",
    )

    task = store.create("下载 第一卷", inputs)
    store.transition(task.id, TaskStatus.RUNNING, "正在下载")
    failed = store.transition(
        task.id,
        TaskStatus.FAILED,
        "网络错误",
        error_detail="TimeoutError",
    )

    assert failed.input_snapshot == inputs
    assert failed.error_detail == "TimeoutError"


def test_terminal_task_cannot_return_to_running():
    from linodl.gui.tasks import TaskStatus, TaskStore

    store = TaskStore()
    task = store.create("测试任务")
    store.transition(task.id, TaskStatus.COMPLETED, "完成")

    with pytest.raises(ValueError, match="终态"):
        store.transition(task.id, TaskStatus.RUNNING, "重新运行")


def test_task_store_snapshot_is_detached_from_future_changes():
    from linodl.gui.tasks import TaskStatus, TaskStore

    store = TaskStore()
    task = store.create("测试任务")
    before = store.snapshot()
    store.transition(task.id, TaskStatus.RUNNING, "运行中", progress=0.5)

    assert before[0].status is TaskStatus.QUEUED
    assert before[0].progress == 0.0


def test_task_store_versioned_snapshot_is_detached_from_future_changes():
    from linodl.gui.tasks import TaskStatus, TaskStore

    store = TaskStore()
    task = store.create("test task")
    _, before = store.snapshot_versioned()
    store.transition(task.id, TaskStatus.RUNNING, "running", progress=0.5)

    assert before[0].status is TaskStatus.QUEUED
    assert before[0].progress == 0.0


def test_download_progress_message_updates_the_task_progress_ratio():
    """Desktop task snapshots must reflect the downloader's [current/total] updates."""
    from linodl.gui.tasks import TaskStatus, TaskStore
    from linodl.gui.workers import BackgroundWorker

    store = TaskStore()
    worker = BackgroundWorker(queue.Queue(), task_store_instance=store)
    store.transition(worker.task.id, TaskStatus.RUNNING, "downloading")

    worker.report_progress("[3/12] [Volume 1] Chapter 3...")

    task = store.get(worker.task.id)
    assert task.detail == "[3/12] [Volume 1] Chapter 3..."
    assert task.progress == 0.25


def test_worker_cancel_only_finishes_after_thread_exits():
    from linodl.gui.tasks import TaskStatus
    from linodl.gui.workers import BackgroundWorker

    class CancelAwareWorker(BackgroundWorker):
        def run(self):
            self.report_done()

    worker = CancelAwareWorker(queue.Queue())
    worker.cancel()

    assert worker.task.status is TaskStatus.CANCELLING

    worker.start()
    worker.join(0.5)

    assert worker.task.status is TaskStatus.CANCELLED


def test_search_worker_preserves_query_in_task_snapshot():
    from linodl.gui.workers import SearchWorker

    config = types.SimpleNamespace()
    worker = SearchWorker("刀剑神域", config, queue.Queue())

    assert worker.task.input_snapshot.kind == "search"
    assert worker.task.input_snapshot.query == "刀剑神域"


def test_search_worker_cancels_while_waiting_for_profile(monkeypatch, tmp_path):
    from linodl.core.browser import BrowserSession
    from linodl.gui import workers as workers_module
    from linodl.gui.tasks import TaskStatus

    class FakeContext:
        pages = []

        def new_page(self):
            return types.SimpleNamespace(content=lambda: "")

        def close(self):
            pass

    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        types.SimpleNamespace(
            launch_persistent_context=lambda path, **kwargs: FakeContext()
        ),
    )
    monkeypatch.setattr(
        workers_module,
        "SearchEngine",
        lambda browser_session: types.SimpleNamespace(search=lambda keyword: []),
    )

    config = types.SimpleNamespace(
        headless=True,
        anti_bot_mode="cloak",
        proxy="",
        geoip=False,
        profile_dir=str(tmp_path),
    )
    holder = BrowserSession(profile_dir=str(tmp_path), anti_bot_mode="cloak")
    worker = workers_module.SearchWorker("测试", config, queue.Queue())

    holder.start()
    try:
        worker.start()
        threading.Event().wait(0.05)
        worker.cancel()
        worker.join(0.3)
        assert not worker.is_alive()
        assert worker.task.status is TaskStatus.CANCELLED
    finally:
        holder.close()
        worker.join(0.5)


def test_verification_service_uses_visible_cloak_and_rechecks_target():
    from linodl.gui.verification import VerificationService

    class FakeSession:
        def __init__(self):
            self.goto_urls = []
            self.contents = [
                "<html><div class='cf-turnstile'>verify you are human</div></html>",
                '<html><a href="/novel/1.html">正常内容</a></html>',
                '<html><a href="/novel/1.html">正常内容</a></html>',
            ]
            self.closed = False

        def start(self, prefer_cloak=False):
            self.prefer_cloak = prefer_cloak
            return self

        def goto(self, url, timeout=30000, wait_until="domcontentloaded"):
            self.goto_urls.append(url)

        def content(self):
            if len(self.contents) > 1:
                return self.contents.pop(0)
            return self.contents[0]

        def close(self):
            self.closed = True

    created = {}

    def session_factory(**kwargs):
        created["kwargs"] = kwargs
        created["session"] = FakeSession()
        return created["session"]

    config = types.SimpleNamespace(
        proxy="",
        geoip=False,
        profile_dir="profile",
    )
    result = VerificationService(
        session_factory=session_factory,
        poll_interval=0,
    ).verify(
        "https://www.linovelib.com/",
        config,
        threading.Event(),
        lambda message: None,
        timeout_ms=50,
    )

    assert created["kwargs"]["headless"] is False
    assert created["kwargs"]["anti_bot_mode"] == "cloak"
    assert created["session"].goto_urls == [
        "https://www.linovelib.com/",
        "https://www.linovelib.com/",
    ]
    assert created["session"].closed is True
    assert result.passed is True


def test_verification_service_focuses_existing_window_and_safely_reports_fallback():
    from linodl.gui.verification import VerificationService

    messages = []
    focus_event = threading.Event()
    focus_event.set()

    class FakeSession:
        def __init__(self):
            self.contents = [
                "<html><div class='cf-turnstile'>verify you are human</div></html>",
                '<html><a href="/novel/1.html">正常内容</a></html>',
                '<html><a href="/novel/1.html">正常内容</a></html>',
            ]

        def start(self, prefer_cloak=False):
            return self

        def goto(self, url, **kwargs):
            pass

        def content(self):
            if len(self.contents) > 1:
                return self.contents.pop(0)
            return self.contents[0]

        def close(self):
            pass

    config = types.SimpleNamespace(proxy="", geoip=False, profile_dir="profile")
    result = VerificationService(
        session_factory=lambda **kwargs: FakeSession(),
        poll_interval=0,
    ).verify(
        "https://www.linovelib.com/novel/1",
        config,
        threading.Event(),
        messages.append,
        focus_event=focus_event,
        timeout_ms=50,
    )

    assert result.passed is True
    assert focus_event.is_set() is False
    assert any("验证窗口已打开" in message for message in messages)


def test_verification_service_brings_current_page_to_front_on_focus_request():
    from linodl.gui.verification import VerificationService

    focus_event = threading.Event()
    focus_event.set()
    brought_to_front = threading.Event()

    class FakePage:
        def bring_to_front(self):
            brought_to_front.set()

    class FakeSession:
        page = FakePage()

        def start(self, prefer_cloak=False):
            return self

        def goto(self, url, **kwargs):
            pass

        def content(self):
            return '<html><a href="/novel/1.html">正常内容</a></html>'

        def close(self):
            pass

    result = VerificationService(
        session_factory=lambda **kwargs: FakeSession(),
        poll_interval=0,
    ).verify(
        "https://www.linovelib.com/novel/1",
        types.SimpleNamespace(proxy="", geoip=False, profile_dir="profile"),
        threading.Event(),
        lambda message: None,
        focus_event=focus_event,
        timeout_ms=50,
    )

    assert result.passed is True
    assert brought_to_front.is_set()


def test_verification_service_returns_cancelled_before_opening_browser():
    from linodl.gui.verification import VerificationService

    cancel = threading.Event()
    cancel.set()
    opened = []
    config = types.SimpleNamespace(proxy="", geoip=False, profile_dir="profile")

    result = VerificationService(
        session_factory=lambda **kwargs: opened.append(kwargs)
    ).verify(
        "https://www.linovelib.com/",
        config,
        cancel,
        lambda message: None,
    )

    assert opened == []
    assert result.cancelled is True
    assert result.passed is False


def test_worker_returns_to_running_after_visible_verification(monkeypatch):
    from linodl.gui import workers as workers_module
    from linodl.gui.tasks import TaskStatus
    from linodl.gui.verification import VerificationResult

    class PassingService:
        def verify(
            self,
            target_url,
            config,
            cancel_event,
            progress,
            *,
            focus_event,
        ):
            assert target_url == "https://www.linovelib.com/"
            assert cancel_event.is_set() is False
            assert focus_event.is_set() is False
            return VerificationResult(
                passed=True,
                message="验证已通过，正在恢复原任务。",
            )

    monkeypatch.setattr(workers_module, "verification_service", PassingService(), raising=False)
    worker = workers_module.SearchWorker(
        "测试",
        types.SimpleNamespace(),
        queue.Queue(),
    )
    worker._task_store.transition(
        worker.task.id,
        TaskStatus.RUNNING,
        "正在搜索",
    )

    assert worker.verify_challenge("https://www.linovelib.com/", "search-home")
    assert worker.task.status is TaskStatus.RUNNING
    assert worker.task.detail == "验证已通过，正在恢复原任务。"


def test_sensitive_error_text_is_redacted():
    from linodl.core.sanitization import redact_sensitive_text

    message = (
        "proxy socks5://reader:secret@127.0.0.1:1080 failed; "
        "token=abcd1234 password=hunter2 cf_clearance=cookie-value"
    )

    redacted = redact_sensitive_text(message)

    assert "reader" not in redacted
    assert "secret" not in redacted
    assert "abcd1234" not in redacted
    assert "hunter2" not in redacted
    assert "cookie-value" not in redacted
    assert "socks5://***:***@127.0.0.1:1080" in redacted


def test_download_worker_snapshot_keeps_catalog_url():
    from linodl.gui.workers import DownloadWorker

    config = types.SimpleNamespace(output_dir="books")
    novel = types.SimpleNamespace(
        title="测试作品",
        catalog_url="https://www.linovelib.com/novel/1/catalog",
    )
    worker = DownloadWorker(
        [],
        {"第一卷"},
        novel,
        config,
        queue.Queue(),
    )

    assert worker.task.input_snapshot.url == novel.catalog_url


def test_download_worker_restart_keeps_snapshot_output_directory():
    from linodl.gui.workers import DownloadWorker

    config = types.SimpleNamespace(output_dir="current-settings")
    novel = types.SimpleNamespace(
        title="测试作品",
        catalog_url="https://www.linovelib.com/novel/1/catalog",
    )

    worker = DownloadWorker(
        [],
        {"第一卷"},
        novel,
        config,
        queue.Queue(),
        output_dir="snapshot-output",
    )

    assert worker.output_dir == "snapshot-output"
    assert worker.task.input_snapshot.output_dir == "snapshot-output"


def test_task_actions_offer_cancel_or_restore():
    from linodl.gui.tasks import TaskStatus, TaskStore
    from linodl.gui.widgets.task_center import task_actions

    store = TaskStore()
    running = store.create("运行中")
    failed = store.create("失败")
    store.transition(running.id, TaskStatus.RUNNING, "下载中")
    store.transition(failed.id, TaskStatus.FAILED, "网络错误")

    assert task_actions(store.get(running.id)) == ("cancel",)
    assert task_actions(store.get(failed.id)) == ("restore",)
