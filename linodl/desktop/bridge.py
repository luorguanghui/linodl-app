"""Stable pywebview command boundary for the React desktop UI."""

from __future__ import annotations

from typing import Callable

from ..config.manager import ConfigManager
from .controller import CatalogOperationNotFound, DesktopController
from .serialization import to_primitive


class DesktopBridge:
    def __init__(
        self,
        config: ConfigManager,
        debug: bool = False,
        *,
        controller: DesktopController | None = None,
    ):
        self._config = config
        self.debug = debug
        self._controller = controller or DesktopController(config=config)
        self._window = None

    def attach_window(self, window) -> None:
        self._window = window

    def bootstrap(self) -> dict:
        try:
            self._drain_events()
            snapshot = self._controller.poll(-1, -1)
            return {
                **snapshot,
                "config": to_primitive(
                    {
                        "output_dir": self._config.output_dir,
                        "headless": self._config.headless,
                        "anti_bot_mode": self._config.anti_bot_mode,
                        "profile_dir": self._config.profile_dir,
                        "proxy": self._config.proxy,
                        "geoip": self._config.geoip,
                        "theme": self._config.theme,
                    }
                ),
            }
        except Exception:
            return self._error(
                "BOOTSTRAP_FAILED",
                "无法读取应用状态。",
                "请重新启动应用。",
            )

    def poll(self, task_version: int, operation_version: int) -> dict:
        try:
            self._drain_events()
            return self._controller.poll(int(task_version), int(operation_version))
        except Exception:
            return self._error(
                "POLL_FAILED",
                "无法刷新任务状态。",
                "请稍后重试。",
            )

    def start_search(self, query: str) -> dict:
        normalized = str(query or "").strip()
        if not normalized:
            return self._error(
                "INVALID_QUERY",
                "请输入作品名。",
                "输入作品名后重新查找。",
            )
        return self._start("search", query=normalized)

    def load_catalog(self, url: str) -> dict:
        normalized = str(url or "").strip()
        if not normalized:
            return self._error(
                "INVALID_URL",
                "请输入目录地址。",
                "输入作品目录地址后重试。",
            )
        return self._start("catalog", url=normalized)

    def start_download(
        self,
        catalog_operation_id: str,
        selected_volumes: list[str],
    ) -> dict:
        catalog_id = str(catalog_operation_id or "").strip()
        if not catalog_id:
            return self._error(
                "INVALID_CATALOG",
                "目录结果无效。",
                "请重新读取目录。",
            )
        if not isinstance(selected_volumes, list):
            return self._error(
                "INVALID_SELECTION",
                "请选择要下载的分卷。",
                "至少选择一个分卷后重试。",
            )
        volumes = [
            normalized
            for value in (selected_volumes or [])
            if (normalized := str(value or "").strip())
        ]
        if not volumes:
            return self._error(
                "INVALID_SELECTION",
                "请选择要下载的分卷。",
                "至少选择一个分卷后重试。",
            )
        return self._start(
            "download",
            catalog_operation_id=catalog_id,
            selected_volumes=volumes,
        )

    def cancel(self, task_id: str) -> dict:
        normalized = str(task_id or "").strip()
        if not normalized:
            return self._error(
                "INVALID_TASK",
                "任务标识无效。",
                "请刷新任务列表后重试。",
            )
        try:
            if not self._controller.cancel(normalized):
                return self._error(
                    "TASK_NOT_ACTIVE",
                    "任务已结束或不存在。",
                    "请刷新任务列表。",
                )
        except Exception:
            return self._error(
                "CANCEL_FAILED",
                "无法取消任务。",
                "请稍后重试。",
            )
        return {"ok": True}

    def _start(self, kind: str, **payload) -> dict:
        try:
            operation_id = self._controller.start(kind, **payload)
        except CatalogOperationNotFound:
            return self._error(
                "CATALOG_NOT_FOUND",
                "目录结果已失效。",
                "请重新读取目录后下载。",
            )
        except Exception:
            return self._error(
                "START_FAILED",
                "无法启动任务。",
                "请稍后重试。",
            )
        return {"ok": True, "operation_id": operation_id}

    def _drain_events(self) -> None:
        drain: Callable[[], None] | None = getattr(
            self._controller, "drain_events", None
        )
        if drain is not None:
            drain()

    @staticmethod
    def _error(code: str, message: str, action: str) -> dict:
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "action": action,
            },
        }
