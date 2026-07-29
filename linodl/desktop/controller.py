"""Thread-safe orchestration of existing GUI workers for the desktop bridge."""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping

from ..config.manager import ConfigManager
from ..core.sanitization import redact_sensitive_text
from ..gui.tasks import TaskStore, task_store as shared_task_store
from ..gui.workers import (
    CatalogWorker,
    DownloadWorker,
    ExportWorker,
    SearchWorker,
    VerifyWorker,
    WarmupWorker,
    cancel_task,
)
from .serialization import to_primitive


WorkerFactory = Callable[[dict, queue.Queue, object], object]


class CatalogOperationNotFound(ValueError):
    """Raised when a download references a catalog result not held by Python."""


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


class DesktopController:
    """Own workers, consume their events, and expose versioned UI snapshots."""

    def __init__(
        self,
        config: ConfigManager | None = None,
        *,
        task_store: TaskStore | None = None,
        worker_factories: Mapping[str, WorkerFactory] | None = None,
        cancel_callback: Callable[[str], bool] = cancel_task,
    ):
        self._config = config
        self._task_store = task_store if task_store is not None else shared_task_store
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.RLock()
        self._operations: dict[str, OperationRecord] = {}
        self._workers: dict[str, object] = {}
        self._catalog_results: dict[str, tuple[object, object]] = {}
        self._operation_version = 0
        self._cancel_callback = cancel_callback

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

    @staticmethod
    def _serialize_result(kind: str, result: object) -> object:
        if kind == "download" and isinstance(result, tuple) and len(result) == 3:
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
