import threading
from pathlib import Path

from linodl.gui.directory_scan import scan_download_directories
from linodl.gui.app import MainWindow
from linodl.gui.widgets.progress_area import parse_progress_message
from linodl.gui.workers import BackgroundWorker


def test_parse_progress_message_extracts_current_and_total():
    assert parse_progress_message("[3/20] [第一卷] 标题...") == (3, 20)
    assert parse_progress_message("[10/10] [第二卷] 插图... OK") == (10, 10)


def test_parse_progress_message_ignores_non_progress_text():
    assert parse_progress_message("正在启动浏览器...") is None
    assert parse_progress_message("ERROR: failed") is None


def test_scan_download_directories_returns_empty_for_empty_output(tmp_path: Path):
    assert scan_download_directories(str(tmp_path), include_images=True) == []


def test_scan_download_directories_counts_text_and_images(tmp_path: Path):
    volume = tmp_path / "第一卷"
    volume.mkdir()
    (volume / "001_开端.txt").write_text("正文", encoding="utf-8")
    (volume / "readme.md").write_text("ignore", encoding="utf-8")
    illus_dir = volume / "插图"
    illus_dir.mkdir()
    (illus_dir / "cover.jpg").write_bytes(b"fake")
    (illus_dir / "cover.webp").write_bytes(b"fake")

    [info] = scan_download_directories(str(tmp_path), include_images=True)

    assert info.name == "第一卷"
    assert info.text_count == 1
    assert info.image_count == 2


def test_main_window_dispatches_string_result_to_active_panel_on_result():
    class FakePanel:
        def __init__(self):
            self.result = None

        def on_result(self, value):
            self.result = value

    window = MainWindow.__new__(MainWindow)
    panel = FakePanel()

    window._dispatch_result("Cloudflare 验证成功完成。", panel)

    assert panel.result == "Cloudflare 验证成功完成。"


def test_background_worker_tags_messages_with_owner():
    import queue
    from linodl.gui.workers import BackgroundWorker

    q = queue.Queue()

    class FakePanel:
        pass

    owner = FakePanel()
    worker = BackgroundWorker(q, owner=owner)
    worker.report_progress("test progress")
    worker.report_result("test result")
    worker.report_error("test error")
    worker.report_done()

    msg1 = q.get_nowait()
    assert msg1 == ("progress", "test progress", owner)

    msg2 = q.get_nowait()
    assert msg2 == ("result", "test result", owner)

    msg3 = q.get_nowait()
    assert msg3 == ("error", "test error", owner)

    msg4 = q.get_nowait()
    assert msg4 == ("done", None, owner)


def test_dispatch_routes_to_owner_panel():
    class FakePanel:
        def __init__(self):
            self.progress_msgs = []
            self.result = None
            self.error = None
            self.done = False

        def on_progress(self, msg):
            self.progress_msgs.append(msg)

        def on_search_complete(self, data):
            self.result = data

        def on_error(self, msg):
            self.error = msg

        def on_done(self):
            self.done = True

    window = MainWindow.__new__(MainWindow)
    window._status_label = type('S', (), {'configure': lambda self, **kw: None})()

    panel_a = FakePanel()
    panel_b = FakePanel()

    window._dispatch("progress", "downloading...", panel_a)
    assert panel_a.progress_msgs == ["downloading..."]
    assert panel_b.progress_msgs == []

    window._dispatch("error", "failed", panel_b)
    assert panel_b.error == "failed"
    assert panel_a.error is None

    window._dispatch("done", None, panel_a)
    assert panel_a.done is True
    assert panel_b.done is False


def test_is_busy_returns_false_when_no_worker():
    """A panel with no worker should report not busy."""
    from linodl.gui.panels.search_panel import SearchPanel

    # Create a minimal SearchPanel without a real parent
    panel = SearchPanel.__new__(SearchPanel)
    panel._worker = None

    assert panel.is_busy() is False


def test_is_busy_returns_true_while_worker_alive():
    """is_busy() should return True while the worker thread is alive."""
    import queue

    class SlowWorker(BackgroundWorker):
        def run(self):
            self.report_progress("working...")
            threading.Event().wait(2.0)  # simulate long work
            self.report_done()

    class FakePanelWithBusy:
        def __init__(self):
            self._worker = None

        def is_busy(self):
            return self._worker is not None and self._worker.is_alive()

    q = queue.Queue()

    panel = FakePanelWithBusy()
    panel._worker = SlowWorker(q, owner=panel)
    panel._worker.start()

    try:
        assert panel.is_busy() is True
    finally:
        panel._worker.cancel()
        panel._worker.join(timeout=1)


def test_is_busy_returns_false_after_worker_completes():
    """is_busy() should return False after the worker finishes."""
    import queue

    class QuickWorker(BackgroundWorker):
        def run(self):
            self.report_progress("done")
            self.report_done()

    class FakePanelWithBusy:
        def __init__(self):
            self._worker = None

        def is_busy(self):
            return self._worker is not None and self._worker.is_alive()

    q = queue.Queue()

    panel = FakePanelWithBusy()
    panel._worker = QuickWorker(q, owner=panel)
    panel._worker.start()
    panel._worker.join(timeout=1)

    assert panel.is_busy() is False


def test_show_panel_no_longer_has_busy_check():
    """The old _is_panel_busy method should be removed."""
    import inspect
    # Verify the method does not exist on MainWindow
    assert '_is_panel_busy' not in [name for name, _ in inspect.getmembers(MainWindow, predicate=inspect.isfunction)]


def test_classify_workbench_input_distinguishes_query_and_catalog_url():
    from linodl.gui.panels.workbench_panel import classify_workbench_input

    assert classify_workbench_input("") == "empty"
    assert classify_workbench_input("刀剑神域") == "query"
    assert (
        classify_workbench_input(
            "https://www.linovelib.com/novel/1/catalog"
        )
        == "url"
    )
    assert classify_workbench_input("https://example.com/novel/1") == "invalid_url"


def test_task_center_sorts_active_tasks_before_finished_tasks():
    from linodl.gui.tasks import TaskStatus, TaskStore
    from linodl.gui.widgets.task_center import sort_task_records

    store = TaskStore()
    completed = store.create("已完成")
    running = store.create("下载中")
    waiting = store.create("等待验证")
    store.transition(completed.id, TaskStatus.COMPLETED, "完成")
    store.transition(running.id, TaskStatus.RUNNING, "正在下载")
    store.transition(
        waiting.id,
        TaskStatus.WAITING_FOR_VERIFICATION,
        "等待用户验证",
    )

    records = sort_task_records(store.snapshot())

    assert [record.status for record in records] == [
        TaskStatus.RUNNING,
        TaskStatus.WAITING_FOR_VERIFICATION,
        TaskStatus.COMPLETED,
    ]
