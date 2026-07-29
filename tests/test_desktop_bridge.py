from __future__ import annotations

import os
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


def test_bridge_settings_never_return_password_and_empty_password_keeps_secret(
    tmp_path,
):
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.set_credentials("reader", "secret")
    bridge = DesktopBridge(config, controller=FakeController())

    before = bridge.get_settings()
    saved = bridge.save_settings(
        {
            **before["settings"],
            "username": "reader-renamed",
            "password": "",
            "clear_password": False,
            "proxy": "",
            "geoip": True,
        }
    )
    after = bridge.get_settings()

    assert before["settings"]["has_password"] is True
    assert "password" not in before["settings"]
    assert saved == {"ok": True}
    assert config.username == "reader-renamed"
    assert config.password == "secret"
    assert config.geoip is False
    assert after["settings"]["has_password"] is True
    assert "password" not in after["settings"]


def test_bridge_settings_clear_password_only_when_explicitly_requested(tmp_path):
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.set_credentials("reader", "secret")
    bridge = DesktopBridge(config, controller=FakeController())
    settings = bridge.get_settings()["settings"]

    response = bridge.save_settings(
        {
            **settings,
            "password": "ignored",
            "clear_password": True,
        }
    )

    assert response == {"ok": True}
    assert config.password == ""
    assert bridge.get_settings()["settings"]["has_password"] is False


def test_bridge_choose_directory_uses_attached_pywebview_window(tmp_path):
    class FakeWindow:
        def __init__(self):
            self.calls = []

        def create_file_dialog(self, dialog_type):
            self.calls.append(dialog_type)
            return (str(tmp_path / "chosen"),)

    bridge = make_bridge(tmp_path)
    window = FakeWindow()
    bridge.attach_window(window)

    response = bridge.choose_directory()

    assert response == {"ok": True, "path": str(tmp_path / "chosen")}
    assert len(window.calls) == 1


def test_bridge_open_directory_allows_output_and_descendants_only(
    monkeypatch,
    tmp_path,
):
    output_dir = tmp_path / "output"
    child = output_dir / "作品 A"
    outside = tmp_path / "outside"
    child.mkdir(parents=True)
    outside.mkdir()
    opened = []
    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path))
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.output_dir = str(output_dir)
    bridge = DesktopBridge(config, controller=FakeController())

    assert bridge.open_directory(str(output_dir)) == {"ok": True}
    assert bridge.open_directory(str(child)) == {"ok": True}
    rejected = bridge.open_directory(str(outside))

    assert rejected["error"]["code"] == "DIRECTORY_OUTSIDE_OUTPUT"
    assert opened == [str(output_dir.resolve()), str(child.resolve())]


def test_bridge_open_directory_rejects_resolved_symlink_escape(
    monkeypatch,
    tmp_path,
):
    output_dir = tmp_path / "output"
    outside = tmp_path / "outside"
    output_dir.mkdir()
    outside.mkdir()
    link = output_dir / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    opened = []
    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path))
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.output_dir = str(output_dir)
    bridge = DesktopBridge(config, controller=FakeController())

    response = bridge.open_directory(str(link))

    assert response["error"]["code"] == "DIRECTORY_OUTSIDE_OUTPUT"
    assert opened == []


def test_bridge_lists_and_starts_only_configured_output_archives(tmp_path):
    output_dir = tmp_path / "output"
    volume = output_dir / "作品 A" / "第一卷"
    volume.mkdir(parents=True)
    (volume / "001_序章.txt").write_text("正文", encoding="utf-8")
    controller = FakeController()
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.output_dir = str(output_dir)
    bridge = DesktopBridge(config, controller=controller)

    listed = bridge.list_archives()
    verified = bridge.start_verify("作品 A")

    assert [archive["id"] for archive in listed["archives"]] == ["作品 A"]
    assert verified == {"ok": True, "operation_id": "op-1"}
    kind, payload = controller.last
    assert kind == "verify"
    assert payload["output_dir"] == str((output_dir / "作品 A").resolve())
    assert payload["selected_volumes"] == ["第一卷"]
    assert [volume.name for volume in payload["volumes"]] == ["第一卷"]

    exported = bridge.start_export("作品 A", True)

    assert exported == {"ok": True, "operation_id": "op-1"}
    kind, payload = controller.last
    assert kind == "export"
    assert payload["novel_info"].title == "作品 A"
    assert payload["base_dir"] == str((output_dir / "作品 A").resolve())
    assert payload["per_volume"] is True


def test_bridge_rejects_archive_ids_outside_configured_output(tmp_path):
    output_dir = tmp_path / "output"
    outside_volume = tmp_path / "outside" / "第一卷"
    output_dir.mkdir()
    outside_volume.mkdir(parents=True)
    (outside_volume / "001_序章.txt").write_text("正文", encoding="utf-8")
    controller = FakeController()
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.output_dir = str(output_dir)
    bridge = DesktopBridge(config, controller=controller)

    verified = bridge.start_verify("../outside")
    exported = bridge.start_export("../outside", True)

    assert verified["error"]["code"] == "ARCHIVE_NOT_FOUND"
    assert exported["error"]["code"] == "ARCHIVE_NOT_FOUND"
    assert controller.last is None


def test_bridge_utility_failures_stay_structured_and_redacted(tmp_path):
    config = ConfigManager(str(tmp_path / "settings.ini"))
    config.output_dir = str(tmp_path / "missing-token=secret-value")
    bridge = DesktopBridge(config, controller=FakeController())

    listed = bridge.list_archives()
    chosen = bridge.choose_directory()

    assert listed["error"]["code"] == "ARCHIVE_LIST_FAILED"
    assert chosen["error"]["code"] == "DIRECTORY_PICKER_UNAVAILABLE"
    assert "secret-value" not in str(listed)
    assert "secret-value" not in str(chosen)
