from __future__ import annotations

import threading
import types

import pytest

from linodl.config.manager import ConfigManager
from linodl.desktop.bridge import DesktopBridge
from linodl.desktop.controller import (
    CatalogReloadRequired,
    DesktopController,
    TaskInputNotFound,
    UnsupportedTaskInput,
)
from linodl.gui.tasks import TaskInputSnapshot, TaskStatus, TaskStore
from linodl.gui.verification import VerificationResult
from linodl.gui.workers import BackgroundWorker


class FakeController:
    def __init__(self):
        self.last = None
        self.cancelled_task = None
        self.restarted_task = None
        self.focused_task = None
        self.drained = 0

    def start(self, kind, **payload):
        self.last = (kind, payload)
        return "op-1"

    def drain_events(self):
        self.drained += 1

    def poll(self, task_version, operation_version):
        return {
            "task_version": task_version + 1,
            "tasks": [],
            "operation_version": operation_version + 1,
            "operations": {},
        }

    def cancel(self, task_id):
        self.cancelled_task = task_id
        return True

    def restart(self, task_id):
        self.restarted_task = task_id
        return "op-restarted"

    def focus_verification(self, task_id):
        self.focused_task = task_id
        return True


class FakeProfileService:
    def __init__(self):
        self.checked = 0
        self.manual_target = None

    def snapshot(self):
        return {"status": "unknown", "detail": ""}

    def check_profile(self):
        self.checked += 1
        return True

    def start_manual_verification(self, target_url):
        self.manual_target = target_url
        return True


def make_bridge(tmp_path, controller=None):
    return DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=controller or FakeController(),
    )


def test_bootstrap_never_reports_unknown_profile_as_healthy(tmp_path):
    bridge = make_bridge(tmp_path)

    payload = bridge.bootstrap()

    assert payload["profile"]["status"] in {
        "unknown",
        "checking",
        "healthy",
        "needs_verification",
        "busy",
        "error",
    }
    assert payload["profile"]["status"] != "healthy"


def test_bridge_starts_injected_profile_operations_without_real_browser(tmp_path):
    profile_service = FakeProfileService()
    bridge = DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=FakeController(),
        profile_service=profile_service,
    )

    assert bridge.check_profile() == {"ok": True}
    assert bridge.start_manual_verification(
        " https://www.linovelib.com/novel/1 "
    ) == {
        "ok": True
    }
    assert profile_service.checked == 1
    assert profile_service.manual_target == "https://www.linovelib.com/novel/1"


@pytest.mark.parametrize(
    "target_url",
    [
        " ",
        "ftp://www.linovelib.com/novel/1",
        "https://example.com/novel/1",
        "javascript:alert(1)",
    ],
)
def test_bridge_rejects_unsafe_manual_verification_target(tmp_path, target_url):
    bridge = make_bridge(tmp_path)

    response = bridge.start_manual_verification(target_url)

    assert response["error"]["code"] == "INVALID_VERIFICATION_TARGET"


def test_bridge_focuses_original_waiting_worker_and_resumes_same_task(
    monkeypatch,
    tmp_path,
):
    from linodl.gui import workers as workers_module

    verification_entered = threading.Event()
    captured = {}

    class FocusDrivenVerificationService:
        def verify(
            self,
            target_url,
            config,
            cancel_event,
            progress,
            *,
            focus_event,
        ):
            captured["focus_event"] = focus_event
            verification_entered.set()
            assert focus_event.wait(1)
            return VerificationResult(
                passed=True,
                message="验证已通过，正在恢复原任务。",
            )

    monkeypatch.setattr(
        workers_module,
        "verification_service",
        FocusDrivenVerificationService(),
    )

    task_store = TaskStore()
    holder = {}
    resumed_statuses = []

    class VerificationWorker(BackgroundWorker):
        def __init__(self, message_queue, owner):
            super().__init__(
                message_queue,
                owner,
                task_title="读取目录",
                input_snapshot=TaskInputSnapshot(
                    kind="catalog",
                    url="https://www.linovelib.com/novel/1",
                ),
                task_store_instance=task_store,
            )
            self.config = types.SimpleNamespace()

        def run(self):
            try:
                assert self.verify_challenge(
                    "https://www.linovelib.com/novel/1",
                )
                resumed_statuses.append(self.task.status)
                self.report_result([])
            finally:
                self.report_done()

    def worker_factory(payload, message_queue, owner):
        worker = VerificationWorker(message_queue, owner)
        holder["worker"] = worker
        return worker

    class ProfileServiceThatMustNotStartManualVerification(FakeProfileService):
        def __init__(self):
            super().__init__()
            self.manual_calls = 0

        def start_manual_verification(self, target_url):
            self.manual_calls += 1
            raise AssertionError("waiting tasks must reuse their original worker")

    profile_service = ProfileServiceThatMustNotStartManualVerification()
    controller = DesktopController(
        task_store=task_store,
        worker_factories={"catalog": worker_factory},
    )
    bridge = DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=controller,
        profile_service=profile_service,
    )

    operation_id = controller.start(
        "catalog",
        url="https://www.linovelib.com/novel/1",
    )
    assert verification_entered.wait(1)
    task_id = controller.operations(-1)["operations"][operation_id]["task_id"]
    assert task_store.get(task_id).status is TaskStatus.WAITING_FOR_VERIFICATION

    assert bridge.focus_task_verification(task_id) == {"ok": True}

    holder["worker"].join(1)
    assert not holder["worker"].is_alive()
    assert captured["focus_event"] is holder["worker"]._verification_focus_event
    assert resumed_statuses == [TaskStatus.RUNNING]
    assert task_store.get(task_id).status is TaskStatus.COMPLETED
    assert profile_service.manual_calls == 0


def test_bridge_restarts_task_from_controller_snapshot(tmp_path):
    controller = FakeController()
    bridge = make_bridge(tmp_path, controller)

    response = bridge.restart_task(" task-1 ")

    assert response == {"ok": True, "operation_id": "op-restarted"}
    assert controller.restarted_task == "task-1"


def test_bridge_returns_actionable_restart_errors(tmp_path):
    class FailingRestartController(FakeController):
        error = TaskInputNotFound("task-1")

        def restart(self, task_id):
            raise self.error

    controller = FailingRestartController()
    bridge = make_bridge(tmp_path, controller)

    missing = bridge.restart_task("task-1")
    controller.error = UnsupportedTaskInput("export")
    unsupported = bridge.restart_task("task-1")
    controller.error = CatalogReloadRequired("https://example.test/catalog")
    reload_required = bridge.restart_task("task-1")

    assert missing["error"]["code"] == "TASK_INPUT_NOT_FOUND"
    assert unsupported["error"]["code"] == "UNSUPPORTED_TASK_INPUT"
    assert reload_required["error"]["code"] == "CATALOG_RELOAD_REQUIRED"


def test_bridge_rejects_blank_search(tmp_path):
    bridge = make_bridge(tmp_path)

    response = bridge.start_search("   ")

    assert response == {
        "ok": False,
        "error": {
            "code": "INVALID_QUERY",
            "message": "请输入作品名。",
            "action": "输入作品名后重新查找。",
        },
    }


def test_bridge_starts_valid_search(tmp_path):
    controller = FakeController()
    bridge = make_bridge(tmp_path, controller)

    response = bridge.start_search("  刀剑神域  ")

    assert response == {"ok": True, "operation_id": "op-1"}
    assert controller.last == ("search", {"query": "刀剑神域"})


def test_bridge_validates_catalog_and_download_inputs(tmp_path):
    bridge = make_bridge(tmp_path)

    invalid_url = bridge.load_catalog(" ")
    invalid_catalog = bridge.start_download("", ["第一卷"])
    invalid_selection = bridge.start_download("catalog-op", [])
    malformed_selection = bridge.start_download("catalog-op", 42)

    assert invalid_url["error"]["code"] == "INVALID_URL"
    assert invalid_catalog["error"]["code"] == "INVALID_CATALOG"
    assert invalid_selection["error"]["code"] == "INVALID_SELECTION"
    assert malformed_selection["error"]["code"] == "INVALID_SELECTION"


def test_bridge_starts_catalog_and_download_operations(tmp_path):
    controller = FakeController()
    bridge = make_bridge(tmp_path, controller)

    assert bridge.load_catalog(" https://example.test/catalog ") == {
        "ok": True,
        "operation_id": "op-1",
    }
    assert controller.last == (
        "catalog",
        {"url": "https://example.test/catalog"},
    )

    assert bridge.start_download("catalog-op", [" 第一卷 ", "", "第二卷"]) == {
        "ok": True,
        "operation_id": "op-1",
    }
    assert controller.last == (
        "download",
        {
            "catalog_operation_id": "catalog-op",
            "selected_volumes": ["第一卷", "第二卷"],
        },
    )


def test_bridge_poll_drains_events_before_requesting_snapshot(tmp_path):
    controller = FakeController()
    bridge = make_bridge(tmp_path, controller)

    response = bridge.poll(3, 7)

    assert controller.drained == 1
    assert response == {
        "task_version": 4,
        "tasks": [],
        "operation_version": 8,
        "operations": {},
        "profile": {"status": "unknown", "detail": ""},
    }


def test_bridge_bootstrap_excludes_credentials_and_redacts_proxy(tmp_path):
    controller = FakeController()
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.set_credentials("reader", "secret")
    config.proxy = "socks5://proxy-user:proxy-pass@127.0.0.1:1080"
    bridge = DesktopBridge(config, controller=controller)

    response = bridge.bootstrap()

    assert response["config"]["proxy"] == "socks5://***:***@127.0.0.1:1080"
    assert "username" not in response["config"]
    assert "password" not in response["config"]
    assert response["tasks"] == []


def test_bridge_cancels_task_without_exposing_controller_details(tmp_path):
    controller = FakeController()
    bridge = make_bridge(tmp_path, controller)

    response = bridge.cancel("task-1")

    assert response == {"ok": True}
    assert controller.cancelled_task == "task-1"


def test_bridge_turns_python_exceptions_into_stable_redacted_errors(tmp_path):
    class FailingController(FakeController):
        def start(self, kind, **payload):
            raise RuntimeError("token=secret-value")

    bridge = make_bridge(tmp_path, FailingController())

    response = bridge.start_search("作品 A")

    assert response["ok"] is False
    assert response["error"] == {
        "code": "START_FAILED",
        "message": "无法启动任务。",
        "action": "请稍后重试。",
    }
    assert "secret-value" not in str(response)
