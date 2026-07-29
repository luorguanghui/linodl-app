from __future__ import annotations

import threading
from dataclasses import dataclass

from linodl.desktop.controller import (
    CatalogReloadRequired,
    DesktopController,
    TaskInputNotFound,
    UnsupportedTaskInput,
)
from linodl.gui.tasks import TaskInputSnapshot, TaskStore


class FinishedWorker:
    def __init__(self, message_queue, owner):
        self._queue = message_queue
        self._owner = owner
        self.task = type("Task", (), {"id": "task-1"})()

    def start(self):
        self._queue.put(("result", [{"title": "作品 A"}], self._owner))
        self._queue.put(("done", None, self._owner))


class EventWorker:
    def __init__(self, message_queue, owner, events=(), task_id="task-event"):
        self._queue = message_queue
        self._owner = owner
        self._events = events
        self.task = type("Task", (), {"id": task_id})()

    def start(self):
        for event_type, data in self._events:
            self._queue.put((event_type, data, self._owner))


def test_controller_keeps_result_after_worker_finishes():
    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={"search": lambda payload, q, owner: FinishedWorker(q, owner)},
    )

    operation_id = controller.start("search", query="作品 A")
    controller.drain_events()
    payload = controller.operations(-1)

    assert payload["operations"][operation_id]["status"] == "completed"
    assert payload["operations"][operation_id]["result"][0]["title"] == "作品 A"


def test_controller_versions_operation_changes_and_omits_unchanged_snapshot():
    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={
            "search": lambda payload, q, owner: EventWorker(
                q, owner, events=(("progress", "正在查找"),)
            )
        },
    )

    operation_id = controller.start("search", query="作品 A")
    started = controller.operations(-1)
    controller.drain_events()
    progressed = controller.operations(started["operation_version"])
    unchanged = controller.operations(progressed["operation_version"])

    assert progressed["operation_version"] > started["operation_version"]
    assert progressed["operations"][operation_id]["detail"] == "正在查找"
    assert unchanged == {
        "operation_version": progressed["operation_version"],
        "operations": None,
    }


def test_controller_redacts_worker_errors_and_done_does_not_overwrite_failure():
    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={
            "search": lambda payload, q, owner: EventWorker(
                q,
                owner,
                events=(
                    (
                        "error",
                        "proxy socks5://reader:secret@127.0.0.1 failed token=abcd",
                    ),
                    ("done", None),
                ),
            )
        },
    )

    operation_id = controller.start("search", query="作品 A")
    controller.drain_events()
    operation = controller.operations(-1)["operations"][operation_id]

    assert operation["status"] == "failed"
    assert "reader" not in operation["error"]
    assert "secret" not in operation["error"]
    assert "abcd" not in operation["error"]
    assert "socks5://***:***@127.0.0.1" in operation["error"]


def test_concurrent_drainers_preserve_error_before_done_queue_order(monkeypatch):
    captured = {}

    def factory(payload, message_queue, owner):
        captured["queue"] = message_queue
        captured["owner"] = owner
        return EventWorker(message_queue, owner)

    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={"search": factory},
    )
    operation_id = controller.start("search", query="作品 A")
    message_queue = captured["queue"]
    message_queue.put(("error", "network failed", captured["owner"]))
    message_queue.put(("done", None, captured["owner"]))

    real_get_nowait = message_queue.get_nowait
    error_dequeued = threading.Event()
    release_error = threading.Event()
    second_attempted_processing = threading.Event()
    second_dequeued_done = threading.Event()
    second_finished = threading.Event()
    second_observed_status = []

    class ObservableLock:
        def __init__(self, lock):
            self._lock = lock

        def __enter__(self):
            if threading.current_thread().name == "done-drainer":
                second_attempted_processing.set()
            self._lock.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self._lock.release()

    def controlled_get_nowait():
        event = real_get_nowait()
        if (
            threading.current_thread().name == "error-drainer"
            and event[0] == "error"
        ):
            error_dequeued.set()
            assert release_error.wait(2)
        if (
            threading.current_thread().name == "done-drainer"
            and event[0] == "done"
        ):
            second_dequeued_done.set()
        return event

    monkeypatch.setattr(message_queue, "get_nowait", controlled_get_nowait)
    monkeypatch.setattr(controller, "_lock", ObservableLock(controller._lock))

    first = threading.Thread(target=controller.drain_events, name="error-drainer")

    def drain_and_observe():
        controller.drain_events()
        operation = controller.operations(-1)["operations"][operation_id]
        second_observed_status.append(operation["status"])
        second_finished.set()

    second = threading.Thread(target=drain_and_observe, name="done-drainer")
    first.start()
    assert error_dequeued.wait(1)
    second.start()
    assert second_attempted_processing.wait(1)
    if second_dequeued_done.is_set():
        assert second_finished.wait(1)
    release_error.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_observed_status == ["failed"]


@dataclass
class CatalogVolume:
    name: str


@dataclass
class CatalogNovel:
    title: str


def test_download_factory_receives_original_catalog_objects():
    volumes = [CatalogVolume(name="第一卷")]
    novel = CatalogNovel(title="作品 A")
    captured = {}

    def catalog_factory(payload, message_queue, owner):
        return EventWorker(
            message_queue,
            owner,
            events=(("result", (volumes, novel)), ("done", None)),
            task_id="task-catalog",
        )

    def download_factory(payload, message_queue, owner):
        captured.update(payload)
        return EventWorker(message_queue, owner, task_id="task-download")

    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={
            "catalog": catalog_factory,
            "download": download_factory,
        },
    )
    catalog_operation_id = controller.start("catalog", url="https://example.test/catalog")
    controller.drain_events()

    controller.start(
        "download",
        catalog_operation_id=catalog_operation_id,
        selected_volumes=["第一卷"],
    )

    assert captured["volumes"] is volumes
    assert captured["novel_info"] is novel
    assert captured["selected_volumes"] == ["第一卷"]
    assert "catalog_operation_id" not in captured


def test_download_result_does_not_serialize_runtime_downloader_object():
    volumes = [CatalogVolume(name="第一卷")]
    novel = CatalogNovel(title="作品 A")

    def catalog_factory(payload, message_queue, owner):
        return EventWorker(
            message_queue,
            owner,
            events=(("result", (volumes, novel)), ("done", None)),
            task_id="task-catalog",
        )

    def download_factory(payload, message_queue, owner):
        return EventWorker(
            message_queue,
            owner,
            events=(
                ("result", ({"success": 1}, {"is_clean": True}, object())),
                ("done", None),
            ),
            task_id="task-download",
        )

    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={
            "catalog": catalog_factory,
            "download": download_factory,
        },
    )
    catalog_operation_id = controller.start("catalog", url="https://example.test/catalog")
    controller.drain_events()
    download_operation_id = controller.start(
        "download",
        catalog_operation_id=catalog_operation_id,
        selected_volumes=["第一卷"],
    )

    controller.drain_events()
    operation = controller.operations(-1)["operations"][download_operation_id]

    assert operation["status"] == "completed"
    assert operation["result"] == [{"success": 1}, {"is_clean": True}]


def test_unserializable_worker_result_becomes_safe_failed_operation():
    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={
            "search": lambda payload, q, owner: EventWorker(
                q, owner, events=(("result", object()), ("done", None))
            )
        },
    )
    operation_id = controller.start("search", query="作品 A")

    controller.drain_events()
    operation = controller.operations(-1)["operations"][operation_id]

    assert operation["status"] == "failed"
    assert operation["error"] == "无法处理任务结果。"


def test_poll_combines_versioned_task_and_operation_snapshots():
    task_store = TaskStore()
    task_store.create("read catalog")
    controller = DesktopController(
        task_store=task_store,
        worker_factories={
            "search": lambda payload, q, owner: EventWorker(
                q, owner, events=(("done", None),)
            )
        },
    )
    operation_id = controller.start("search", query="作品 A")

    payload = controller.poll(-1, -1)

    assert payload["task_version"] > 0
    assert payload["tasks"][0]["title"] == "read catalog"
    assert payload["operation_version"] > 0
    assert payload["operations"][operation_id]["status"] == "completed"


def test_cancel_marks_matching_operation_cancelled():
    cancelled = []
    controller = DesktopController(
        task_store=TaskStore(),
        worker_factories={
            "search": lambda payload, q, owner: EventWorker(
                q, owner, task_id="task-cancel"
            )
        },
        cancel_callback=lambda task_id: cancelled.append(task_id) or True,
    )
    operation_id = controller.start("search", query="作品 A")

    assert controller.cancel("task-cancel") is True
    controller.drain_events()
    operation = controller.operations(-1)["operations"][operation_id]

    assert cancelled == ["task-cancel"]
    assert operation["status"] == "cancelled"


def test_restart_dispatches_search_catalog_and_warmup_snapshots():
    task_store = TaskStore()
    search_task = task_store.create(
        "search",
        TaskInputSnapshot(kind="search", query="作品 A"),
    )
    catalog_task = task_store.create(
        "catalog",
        TaskInputSnapshot(kind="catalog", url="https://example.test/catalog"),
    )
    warmup_task = task_store.create("warmup", TaskInputSnapshot(kind="warmup"))
    captured = []

    def factory(kind):
        def create(payload, message_queue, owner):
            captured.append((kind, payload))
            return EventWorker(message_queue, owner, task_id=f"task-{kind}")

        return create

    controller = DesktopController(
        task_store=task_store,
        worker_factories={
            kind: factory(kind) for kind in ("search", "catalog", "warmup")
        },
    )

    controller.restart(search_task.id)
    controller.restart(catalog_task.id)
    controller.restart(warmup_task.id)

    assert captured == [
        ("search", {"query": "作品 A"}),
        ("catalog", {"url": "https://example.test/catalog"}),
        ("warmup", {}),
    ]


def test_restart_download_uses_only_snapshot_and_cached_catalog_data():
    task_store = TaskStore()
    download_task = task_store.create(
        "download",
        TaskInputSnapshot(
            kind="download",
            url="https://example.test/catalog",
            selected_volumes=("第二卷", "第一卷"),
            output_dir="snapshot-output",
        ),
    )
    captured = {}
    volumes = [CatalogVolume(name="第一卷")]
    novel = CatalogNovel(title="作品 A")

    def catalog_factory(payload, message_queue, owner):
        return EventWorker(
            message_queue,
            owner,
            events=(("result", (volumes, novel)), ("done", None)),
            task_id="task-catalog",
        )

    def download_factory(payload, message_queue, owner):
        captured.update(payload)
        return EventWorker(message_queue, owner, task_id="task-download")

    controller = DesktopController(
        task_store=task_store,
        worker_factories={
            "catalog": catalog_factory,
            "download": download_factory,
        },
    )
    controller.start("catalog", url="https://example.test/catalog")
    controller.drain_events()

    controller.restart(download_task.id)

    assert captured == {
        "selected_volumes": ["第二卷", "第一卷"],
        "output_dir": "snapshot-output",
        "volumes": volumes,
        "novel_info": novel,
    }


def test_restart_download_requires_cached_catalog_data():
    task_store = TaskStore()
    task = task_store.create(
        "download",
        TaskInputSnapshot(
            kind="download",
            url="https://example.test/catalog",
            selected_volumes=("第一卷",),
        ),
    )
    controller = DesktopController(
        task_store=task_store,
        worker_factories={"download": lambda payload, q, owner: None},
    )

    try:
        controller.restart(task.id)
    except CatalogReloadRequired as exc:
        assert str(exc) == "https://example.test/catalog"
    else:
        raise AssertionError("download restart must require cached catalog data")


def test_restart_rejects_missing_and_unsupported_snapshots():
    task_store = TaskStore()
    missing = task_store.create("missing")
    unsupported = task_store.create(
        "unsupported",
        TaskInputSnapshot(kind="export", output_dir="out"),
    )
    controller = DesktopController(task_store=task_store)

    try:
        controller.restart(missing.id)
    except TaskInputNotFound:
        pass
    else:
        raise AssertionError("missing snapshot must be rejected")

    try:
        controller.restart(unsupported.id)
    except UnsupportedTaskInput as exc:
        assert str(exc) == "export"
    else:
        raise AssertionError("unsupported snapshot must be rejected")
