import queue
import sys
import threading
import types

import pytest


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
