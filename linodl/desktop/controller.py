"""Thread-safe orchestration of existing GUI workers for the desktop bridge."""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping

from ..config.manager import ConfigManager
from ..core.catalog import normalize_catalog_url
from ..core.downloader import Downloader
from ..core.sanitization import redact_sensitive_text
from ..gui.tasks import TaskStore, task_store as shared_task_store
from ..gui.workers import (
    CatalogWorker,
    DownloadWorker,
    ExportWorker,
    RetryWorker,
    SearchWorker,
    VerifyWorker,
    WarmupWorker,
    cancel_task,
    focus_task_verification,
)
from ..models.novel import NovelInfo, VerificationResult
from .serialization import to_primitive


WorkerFactory = Callable[[dict, queue.Queue, object], object]


class CatalogOperationNotFound(ValueError):
    """Raised when a download references a catalog result not held by Python."""


class CatalogReloadRequired(ValueError):
    """Raised when a restarted download no longer has cached catalog data."""


class TaskInputNotFound(ValueError):
    """Raised when a task cannot be recovered from a persisted input snapshot."""


class UnsupportedTaskInput(ValueError):
    """Raised when a persisted task kind is not supported by desktop recovery."""


class RetrySourceNotFound(ValueError):
    """Raised when an operation has no completed verification to retry."""


class NoRetryableIssues(ValueError):
    """Raised when verification found no issue with a recoverable source URL."""


@dataclass(frozen=True)
class OperationOwner:
    operation_id: str


@dataclass
class OperationRecord:
    id: str
    kind: str
    task_id: str
    status: str
    detail: str = ""
    result: object = None
    error: str = ""


@dataclass(frozen=True)
class RetrySource:
    volumes: object
    selected_volumes: object
    novel_info: NovelInfo
    output_dir: str
    verification: VerificationResult


class DesktopController:
    """Own workers, consume their events, and expose versioned UI snapshots."""

    def __init__(
        self,
        config: ConfigManager | None = None,
        *,
        task_store: TaskStore | None = None,
        worker_factories: Mapping[str, WorkerFactory] | None = None,
        cancel_callback: Callable[[str], bool] = cancel_task,
        focus_verification_callback: Callable[
            [str], bool
        ] = focus_task_verification,
    ):
        self._config = config
        self._task_store = task_store if task_store is not None else shared_task_store
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.RLock()
        self._operations: dict[str, OperationRecord] = {}
        self._workers: dict[str, object] = {}
        self._operation_payloads: dict[str, dict] = {}
        self._retry_sources: dict[str, RetrySource] = {}
        self._catalog_results: dict[str, tuple[object, object]] = {}
        self._catalog_source_urls: dict[str, str] = {}
        self._operation_version = 0
        self._cancel_callback = cancel_callback
        self._focus_verification_callback = focus_verification_callback

        factories = self._default_worker_factories() if config is not None else {}
        if worker_factories:
            factories.update(worker_factories)
        self._worker_factories = factories

    def _default_worker_factories(self) -> dict[str, WorkerFactory]:
        config = self._config
        assert config is not None
        return {
            "search": lambda payload, q, owner: SearchWorker(
                payload["query"], config, q, owner
            ),
            "catalog": lambda payload, q, owner: CatalogWorker(
                payload["url"], config, q, owner
            ),
            "download": lambda payload, q, owner: DownloadWorker(
                payload["volumes"],
                payload["selected_volumes"],
                payload["novel_info"],
                config,
                q,
                owner,
                output_dir=payload.get("output_dir"),
            ),
            "retry": lambda payload, q, owner: RetryWorker(
                Downloader(
                    output_dir=payload["output_dir"],
                    delay_range=config.delay_range,
                ),
                payload["volumes"],
                payload["selected_volumes"],
                payload["novel_info"],
                config,
                q,
                owner,
                verification=payload["verification"],
            ),
            "verify": lambda payload, q, owner: VerifyWorker(
                payload["volumes"],
                payload["selected_volumes"],
                payload.get("output_dir", config.output_dir),
                q,
                owner,
            ),
            "export": lambda payload, q, owner: ExportWorker(
                payload["novel_info"],
                payload["volumes"],
                payload.get("base_dir", config.output_dir),
                bool(payload.get("per_volume", False)),
                q,
                owner,
            ),
            "warmup": lambda payload, q, owner: WarmupWorker(config, q, owner),
        }

    def start(self, kind: str, **payload) -> str:
        operation_id = uuid.uuid4().hex
        owner = OperationOwner(operation_id)
        prepared_payload = self._prepare_payload(kind, payload)
        try:
            factory = self._worker_factories[kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported desktop operation: {kind}") from exc
        worker = factory(prepared_payload, self._queue, owner)
        with self._lock:
            self._operations[operation_id] = OperationRecord(
                id=operation_id,
                kind=kind,
                task_id=worker.task.id,
                status="running",
            )
            self._workers[operation_id] = worker
            self._operation_payloads[operation_id] = prepared_payload
            if kind == "catalog":
                self._catalog_source_urls[operation_id] = normalize_catalog_url(
                    str(payload.get("url", "")).strip()
                )
            self._operation_version += 1
        try:
            worker.start()
        except Exception as exc:
            with self._lock:
                operation = self._operations[operation_id]
                operation.status = "failed"
                operation.error = redact_sensitive_text(exc)
                self._operation_version += 1
            raise
        return operation_id

    def _prepare_payload(self, kind: str, payload: dict) -> dict:
        prepared = dict(payload)
        if kind != "download":
            return prepared
        catalog_operation_id = str(prepared.pop("catalog_operation_id", ""))
        with self._lock:
            catalog_result = self._catalog_results.get(catalog_operation_id)
        if catalog_result is None:
            raise CatalogOperationNotFound(catalog_operation_id)
        volumes, novel_info = catalog_result
        prepared["volumes"] = volumes
        prepared["novel_info"] = novel_info
        return prepared

    def drain_events(self) -> None:
        with self._lock:
            while True:
                try:
                    event_type, data, owner = self._queue.get_nowait()
                except queue.Empty:
                    return
                if not isinstance(owner, OperationOwner):
                    continue
                operation = self._operations.get(owner.operation_id)
                if operation is None:
                    continue
                if event_type == "progress":
                    if operation.status not in {"failed", "cancelled"}:
                        operation.status = "running"
                        operation.detail = redact_sensitive_text(data)
                elif event_type == "result":
                    try:
                        self._cache_retry_source(operation, data)
                        operation.result = self._serialize_result(operation.kind, data)
                    except TypeError:
                        operation.status = "failed"
                        operation.error = "无法处理任务结果。"
                    else:
                        if operation.kind == "catalog":
                            self._cache_catalog_result(operation.id, data)
                elif event_type == "error":
                    operation.status = "failed"
                    operation.error = redact_sensitive_text(data)
                elif event_type == "done":
                    if operation.status not in {"failed", "cancelled"}:
                        operation.status = "completed"
                else:
                    continue
                self._operation_version += 1

    def _cache_catalog_result(self, operation_id: str, result: object) -> None:
        if isinstance(result, tuple) and len(result) == 2:
            self._catalog_results[operation_id] = result

    def _cache_retry_source(self, operation: OperationRecord, result: object) -> None:
        if operation.kind not in {"download", "verify"}:
            return
        verification = result[1] if operation.kind == "download" and isinstance(result, tuple) and len(result) >= 2 else result
        if not isinstance(verification, VerificationResult):
            return
        payload = self._operation_payloads.get(operation.id)
        if payload is None:
            return
        novel_info = payload.get("novel_info")
        if not isinstance(novel_info, NovelInfo):
            novel_info = NovelInfo()
        output_dir = str(payload.get("output_dir") or "")
        if not output_dir:
            return
        self._retry_sources[operation.id] = RetrySource(
            volumes=payload.get("volumes", []),
            selected_volumes=payload.get("selected_volumes", []),
            novel_info=novel_info,
            output_dir=output_dir,
            verification=verification,
        )

    @staticmethod
    def _serialize_result(kind: str, result: object) -> object:
        if kind in {"download", "retry"} and isinstance(result, tuple) and len(result) == 3:
            result = result[:2]
        return to_primitive(result)

    def operations(self, after_version: int = -1) -> dict:
        with self._lock:
            version = self._operation_version
            if after_version == version:
                operations = None
            else:
                operations = to_primitive(self._operations)
        return {
            "operation_version": version,
            "operations": operations,
        }

    def poll(self, task_version: int, operation_version: int) -> dict:
        self.drain_events()
        current_task_version, tasks = self._task_store.snapshot_versioned(task_version)
        operation_snapshot = self.operations(operation_version)
        return {
            "task_version": current_task_version,
            "tasks": to_primitive(tasks),
            **operation_snapshot,
        }

    def cancel(self, task_id: str) -> bool:
        cancelled = self._cancel_callback(task_id)
        if not cancelled:
            return False
        with self._lock:
            for operation in self._operations.values():
                if (
                    operation.task_id == task_id
                    and operation.status not in {"completed", "failed", "cancelled"}
                ):
                    operation.status = "cancelled"
                    operation.detail = "已取消"
                    self._operation_version += 1
                    break
        return True

    def focus_verification(self, task_id: str) -> bool:
        return self._focus_verification_callback(task_id)

    def retry(self, operation_id: str) -> str:
        with self._lock:
            source = self._retry_sources.get(operation_id)
        if source is None:
            raise RetrySourceNotFound(operation_id)
        issues = [
            issue
            for issue in source.verification.issues
            if isinstance(issue.chapter_url, str) and issue.chapter_url.strip()
        ]
        if not issues:
            raise NoRetryableIssues(operation_id)
        return self.start(
            "retry",
            volumes=source.volumes,
            selected_volumes=source.selected_volumes,
            novel_info=source.novel_info,
            output_dir=source.output_dir,
            verification=VerificationResult(issues=issues),
        )

    def restart(self, task_id: str) -> str:
        try:
            record = self._task_store.get(task_id)
        except KeyError as exc:
            raise TaskInputNotFound(task_id) from exc
        snapshot = record.input_snapshot
        if snapshot is None:
            raise TaskInputNotFound(task_id)

        if snapshot.kind == "search" and snapshot.query.strip():
            return self.start("search", query=snapshot.query.strip())
        if snapshot.kind == "catalog" and snapshot.url.strip():
            return self.start("catalog", url=snapshot.url.strip())
        if snapshot.kind == "warmup":
            return self.start("warmup")
        if snapshot.kind == "download":
            return self._restart_download(snapshot)
        if snapshot.kind in {"search", "catalog"}:
            raise TaskInputNotFound(task_id)
        raise UnsupportedTaskInput(snapshot.kind or "<empty>")

    def _restart_download(self, snapshot) -> str:
        url = normalize_catalog_url(snapshot.url.strip())
        selected_volumes = list(snapshot.selected_volumes)
        if not url or not selected_volumes:
            raise TaskInputNotFound("download")
        with self._lock:
            catalog_operation_id = next(
                (
                    operation_id
                    for operation_id, source_url in reversed(
                        list(self._catalog_source_urls.items())
                    )
                    if source_url == url and operation_id in self._catalog_results
                ),
                None,
            )
        if catalog_operation_id is None:
            raise CatalogReloadRequired(url)
        payload = {
            "catalog_operation_id": catalog_operation_id,
            "selected_volumes": selected_volumes,
        }
        if snapshot.output_dir:
            payload["output_dir"] = snapshot.output_dir
        return self.start("download", **payload)
