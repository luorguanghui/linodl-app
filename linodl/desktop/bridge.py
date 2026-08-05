"""Stable pywebview command boundary for the React desktop UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

from ..config.manager import ConfigManager
from ..gui.tasks import TERMINAL_STATUSES
from .archive import load_archive, scan_archives
from .controller import (
    CatalogOperationNotFound,
    CatalogReloadRequired,
    DesktopController,
    NoRetryableIssues,
    RetrySourceNotFound,
    TaskInputNotFound,
    UnsupportedTaskInput,
)
from .profile import DesktopProfileService
from .serialization import to_primitive


_PYWEBVIEW_FOLDER_DIALOG = 10


class DesktopBridge:
    def __init__(
        self,
        config: ConfigManager,
        debug: bool = False,
        *,
        controller: DesktopController | None = None,
        profile_service: DesktopProfileService | None = None,
    ):
        self._config = config
        self.debug = debug
        self._controller = controller or DesktopController(config=config)
        self._profile_service = profile_service or DesktopProfileService(config)
        self._window = None
        self._force_close_requested = False

    def attach_window(self, window) -> None:
        self._window = window

    def has_active_tasks(self) -> bool:
        task_store = getattr(self._controller, "_task_store", None)
        if task_store is None:
            return False
        return any(
            task.status not in TERMINAL_STATUSES
            for task in task_store.snapshot()
        )

    def force_close(self) -> dict:
        self._force_close_requested = True
        if self._window is not None:
            self._window.destroy()
        return {"ok": True}

    def consume_force_close(self) -> bool:
        if not self._force_close_requested:
            return False
        self._force_close_requested = False
        return True

    def bootstrap(self) -> dict:
        try:
            self._drain_events()
            snapshot = self._controller.poll(-1, -1)
            proxy = self._config.proxy
            return {
                **snapshot,
                "profile": self._profile_service.snapshot(),
                "config": to_primitive(
                    {
                        "output_dir": self._config.output_dir,
                        "headless": self._config.headless,
                        "anti_bot_mode": self._config.anti_bot_mode,
                        "profile_dir": self._config.profile_dir,
                        "proxy": self._redact_proxy(proxy),
                        "has_proxy": bool(proxy),
                        "proxy_has_credentials": self._proxy_has_credentials(
                            proxy
                        ),
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
            return {
                **self._controller.poll(int(task_version), int(operation_version)),
                "profile": self._profile_service.snapshot(),
            }
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

    def list_archives(self) -> dict:
        try:
            archives = scan_archives(Path(self._config.output_dir).resolve())
            return {"ok": True, "archives": to_primitive(archives)}
        except Exception:
            return self._error(
                "ARCHIVE_LIST_FAILED",
                "无法读取归档目录。",
                "请检查输出目录后重试。",
            )

    def start_verify(self, archive_id: str) -> dict:
        archive = self._archive_for_id(archive_id)
        if archive is None:
            return self._error(
                "ARCHIVE_NOT_FOUND",
                "所选归档不存在。",
                "请刷新归档列表后重试。",
            )
        try:
            novel_info, volumes, base_dir = load_archive(
                archive["path"],
                self._config.output_dir,
            )
        except Exception:
            return self._error(
                "ARCHIVE_READ_FAILED",
                "无法读取归档内容。",
                "请检查归档文件后重试。",
            )
        if not volumes:
            return self._error(
                "ARCHIVE_EMPTY",
                "所选归档没有可校验的卷册。",
                "请选择包含章节的归档。",
            )
        return self._start(
            "verify",
            volumes=volumes,
            selected_volumes=[volume.name for volume in volumes],
            output_dir=str(base_dir),
            novel_info=novel_info,
        )

    def start_retry(self, operation_id: str) -> dict:
        normalized = str(operation_id or "").strip()
        if not normalized:
            return self._error(
                "INVALID_OPERATION",
                "校验结果无效。",
                "请重新运行校验后再试。",
            )
        try:
            retry_operation_id = self._controller.retry(normalized)
        except RetrySourceNotFound:
            return self._error(
                "RETRY_NOT_AVAILABLE",
                "该校验结果无法重试。",
                "请重新运行校验，或重新读取作品目录后下载。",
            )
        except NoRetryableIssues:
            return self._error(
                "NO_RETRYABLE_ISSUES",
                "没有可自动重试的问题。",
                "缺少下载地址的旧归档需要重新读取目录或手动处理。",
            )
        except Exception:
            return self._error(
                "RETRY_START_FAILED",
                "无法启动重试任务。",
                "请稍后再试。",
            )
        return {"ok": True, "operation_id": retry_operation_id}

    def start_export(self, archive_id: str, per_volume: bool = True) -> dict:
        archive = self._archive_for_id(archive_id)
        if archive is None:
            return self._error(
                "ARCHIVE_NOT_FOUND",
                "所选归档不存在。",
                "请刷新归档列表后重试。",
            )
        try:
            novel_info, volumes, base_dir = load_archive(
                archive["path"],
                self._config.output_dir,
            )
        except Exception:
            return self._error(
                "ARCHIVE_READ_FAILED",
                "无法读取归档内容。",
                "请检查归档文件后重试。",
            )
        if not volumes:
            return self._error(
                "ARCHIVE_EMPTY",
                "所选归档没有可导出的卷册。",
                "请选择包含章节的归档。",
            )
        return self._start(
            "export",
            novel_info=novel_info,
            volumes=volumes,
            base_dir=str(base_dir),
            per_volume=bool(per_volume),
        )

    def get_settings(self) -> dict:
        try:
            proxy = self._config.proxy
            settings = {
                "username": self._config.username,
                "has_password": bool(self._config.password),
                "output_dir": self._config.output_dir,
                "headless": self._config.headless,
                "anti_bot_mode": self._config.anti_bot_mode,
                "profile_dir": self._config.profile_dir,
                "proxy": self._redact_proxy(proxy),
                "has_proxy": bool(proxy),
                "proxy_has_credentials": self._proxy_has_credentials(proxy),
                "geoip": self._config.geoip,
                "theme": self._config.theme,
            }
            return {"ok": True, "settings": to_primitive(settings)}
        except Exception:
            return self._error(
                "SETTINGS_READ_FAILED",
                "无法读取设置。",
                "请稍后重试。",
            )

    def save_settings(self, settings: Mapping[str, object]) -> dict:
        if not isinstance(settings, Mapping):
            return self._invalid_settings()
        try:
            clear_password = settings.get("clear_password", False)
            clear_proxy = settings.get("clear_proxy", False)
            if type(clear_password) is not bool or type(clear_proxy) is not bool:
                return self._invalid_settings()
            password_input = str(settings.get("password", "") or "")
            if clear_password:
                password = ""
            elif password_input:
                password = password_input
            else:
                password = self._config.password
            proxy_input = str(settings.get("proxy", "") or "").strip()
            if self._is_masked_proxy(proxy_input):
                return self._invalid_settings()
            if clear_proxy:
                proxy = ""
            elif proxy_input:
                proxy = proxy_input
            else:
                proxy = self._config.proxy
            self._config.update_settings(
                username=str(
                    settings.get("username", self._config.username) or ""
                ),
                password=password,
                output_dir=str(
                    settings.get("output_dir", self._config.output_dir) or ""
                ),
                headless=self._setting_bool(
                    settings.get("headless"),
                    self._config.headless,
                ),
                anti_bot_mode=str(
                    settings.get(
                        "anti_bot_mode",
                        self._config.anti_bot_mode,
                    )
                    or ""
                ),
                profile_dir=str(
                    settings.get("profile_dir", self._config.profile_dir) or ""
                ),
                proxy=proxy,
                geoip=self._setting_bool(
                    settings.get("geoip"),
                    self._config.geoip,
                ),
                theme=str(settings.get("theme", self._config.theme) or ""),
            )
            return {"ok": True}
        except Exception:
            return self._error(
                "SETTINGS_SAVE_FAILED",
                "无法保存设置。",
                "请检查设置后重试。",
            )

    def choose_directory(self) -> dict:
        if self._window is None:
            return self._error(
                "DIRECTORY_PICKER_UNAVAILABLE",
                "目录选择器暂不可用。",
                "请重新启动桌面应用。",
            )
        try:
            selected = self._window.create_file_dialog(
                _PYWEBVIEW_FOLDER_DIALOG
            )
            if isinstance(selected, (tuple, list)):
                path = str(selected[0]) if selected else ""
            else:
                path = str(selected or "")
            return {"ok": True, "path": path}
        except Exception:
            return self._error(
                "DIRECTORY_PICKER_FAILED",
                "无法打开目录选择器。",
                "请稍后重试。",
            )

    def open_directory(self, path: str) -> dict:
        normalized = str(path or "").strip()
        if not normalized:
            return self._error(
                "INVALID_DIRECTORY",
                "目录地址无效。",
                "请刷新页面后重试。",
            )
        try:
            output_dir = Path(self._config.output_dir).resolve()
            target = Path(normalized).resolve()
            if target != output_dir and output_dir not in target.parents:
                return self._error(
                    "DIRECTORY_OUTSIDE_OUTPUT",
                    "只能打开输出目录内的文件夹。",
                    "请从归档列表中选择目录。",
                )
            if not target.is_dir():
                return self._error(
                    "DIRECTORY_NOT_FOUND",
                    "目录不存在。",
                    "请刷新归档列表后重试。",
                )
            os.startfile(str(target))
            return {"ok": True}
        except Exception:
            return self._error(
                "OPEN_DIRECTORY_FAILED",
                "无法打开目录。",
                "请稍后重试。",
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

    def check_profile(self) -> dict:
        try:
            started = self._profile_service.check_profile()
        except Exception:
            return self._error(
                "PROFILE_CHECK_FAILED",
                "无法检查浏览档案。",
                "请稍后重试。",
            )
        if not started:
            return self._error(
                "PROFILE_BUSY",
                "浏览档案操作正在进行。",
                "请等待当前操作完成后重试。",
            )
        return {"ok": True}

    def start_manual_verification(self, target_url: str) -> dict:
        normalized = str(target_url or "").strip()
        if not self._is_valid_verification_target(normalized):
            return self._error(
                "INVALID_VERIFICATION_TARGET",
                "验证页面地址无效。",
                "请输入需要人工验证的页面地址。",
            )
        try:
            started = self._profile_service.start_manual_verification(normalized)
        except Exception:
            return self._error(
                "MANUAL_VERIFICATION_FAILED",
                "无法打开人工验证。",
                "请稍后重试。",
            )
        if not started:
            return self._error(
                "PROFILE_BUSY",
                "浏览档案操作正在进行。",
                "请等待当前操作完成后重试。",
            )
        return {"ok": True}

    def focus_task_verification(self, task_id: str) -> dict:
        normalized = str(task_id or "").strip()
        if not normalized:
            return self._error(
                "INVALID_TASK",
                "任务标识无效。",
                "请刷新任务列表后重试。",
            )
        try:
            focused = self._controller.focus_verification(normalized)
        except Exception:
            return self._error(
                "VERIFICATION_FOCUS_FAILED",
                "无法聚焦验证窗口。",
                "请从任务栏切换到已打开的浏览器窗口。",
            )
        if not focused:
            return self._error(
                "VERIFICATION_TASK_NOT_ACTIVE",
                "该任务当前没有等待中的验证窗口。",
                "请刷新任务列表后重试。",
            )
        return {"ok": True}

    def restart_task(self, task_id: str) -> dict:
        normalized = str(task_id or "").strip()
        if not normalized:
            return self._error(
                "INVALID_TASK",
                "任务标识无效。",
                "请刷新任务列表后重试。",
            )
        try:
            operation_id = self._controller.restart(normalized)
        except CatalogReloadRequired:
            return self._error(
                "CATALOG_RELOAD_REQUIRED",
                "目录缓存已失效，无法直接恢复下载。",
                "请重新读取目录并选择分卷。",
            )
        except TaskInputNotFound:
            return self._error(
                "TASK_INPUT_NOT_FOUND",
                "该任务没有完整的恢复输入。",
                "请重新输入作品名或目录地址。",
            )
        except UnsupportedTaskInput:
            return self._error(
                "UNSUPPORTED_TASK_INPUT",
                "该任务类型暂不支持恢复。",
                "请从对应页面重新开始。",
            )
        except Exception:
            return self._error(
                "RESTART_FAILED",
                "无法重新开始任务。",
                "请稍后重试。",
            )
        return {"ok": True, "operation_id": operation_id}

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

    def _archive_for_id(self, archive_id: str) -> dict | None:
        normalized = str(archive_id or "").strip()
        if not normalized:
            return None
        try:
            archives = scan_archives(Path(self._config.output_dir).resolve())
        except Exception:
            return None
        return next(
            (
                archive
                for archive in archives
                if archive["id"] == normalized
            ),
            None,
        )

    @staticmethod
    def _setting_bool(value: object, fallback: bool) -> bool:
        return value if isinstance(value, bool) else fallback

    @staticmethod
    def _proxy_has_credentials(proxy: str) -> bool:
        return "@" in proxy

    @staticmethod
    def _is_masked_proxy(proxy: str) -> bool:
        return proxy == "***" or ("://***" in proxy and "@" in proxy)

    @staticmethod
    def _redact_proxy(proxy: str) -> str:
        return "***" if "@" in proxy else proxy

    @classmethod
    def _invalid_settings(cls) -> dict:
        return cls._error(
            "INVALID_SETTINGS",
            "设置内容无效。",
            "请刷新设置页后重试。",
        )

    @staticmethod
    def _is_valid_verification_target(target_url: str) -> bool:
        try:
            parsed = urlsplit(target_url)
            hostname = (parsed.hostname or "").rstrip(".").lower()
        except ValueError:
            return False
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and (
                hostname == "linovelib.com"
                or hostname.endswith(".linovelib.com")
            )
        )

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
