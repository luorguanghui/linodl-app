from __future__ import annotations

from dataclasses import dataclass

from linodl.desktop.controller import DesktopController
from linodl.gui.tasks import TaskStore


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
