from __future__ import annotations

from linodl.config.manager import ConfigManager
from linodl.desktop.bridge import DesktopBridge


class FakeController:
    def __init__(self):
        self.last = None
        self.cancelled_task = None
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


def make_bridge(tmp_path, controller=None):
    return DesktopBridge(
        ConfigManager(str(tmp_path / "settings.ini")),
        controller=controller or FakeController(),
    )


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
