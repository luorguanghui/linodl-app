"""Thread-safe task state used by the desktop workbench."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, replace
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    WAITING_FOR_PROFILE = "waiting_for_profile"
    RUNNING = "running"
    WAITING_FOR_VERIFICATION = "waiting_for_verification"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


TERMINAL_STATUSES = {
    TaskStatus.CANCELLED,
    TaskStatus.FAILED,
    TaskStatus.COMPLETED,
}


@dataclass(frozen=True)
class TaskInputSnapshot:
    kind: str = ""
    query: str = ""
    url: str = ""
    selected_volumes: tuple[str, ...] = ()
    output_dir: str = ""


@dataclass
class TaskRecord:
    id: str
    title: str
    status: TaskStatus = TaskStatus.QUEUED
    detail: str = ""
    progress: float = 0.0
    input_snapshot: TaskInputSnapshot | None = None
    error_detail: str = ""


class TaskStore:
    """Own task records and return detached snapshots to UI consumers."""

    def __init__(self):
        self._lock = threading.RLock()
        self._records: dict[str, TaskRecord] = {}
        self._version = 0

    def create(
        self,
        title: str,
        input_snapshot: TaskInputSnapshot | None = None,
    ) -> TaskRecord:
        record = TaskRecord(
            id=uuid.uuid4().hex,
            title=title,
            input_snapshot=input_snapshot,
        )
        with self._lock:
            self._records[record.id] = record
            self._version += 1
            return replace(record)

    def get(self, task_id: str) -> TaskRecord:
        with self._lock:
            return replace(self._records[task_id])

    def transition(
        self,
        task_id: str,
        status: TaskStatus,
        detail: str = "",
        *,
        progress: float | None = None,
        error_detail: str | None = None,
    ) -> TaskRecord:
        with self._lock:
            record = self._records[task_id]
            if record.status in TERMINAL_STATUSES and status is not record.status:
                raise ValueError(f"任务已处于终态: {record.status.value}")
            record.status = status
            record.detail = detail
            if progress is not None:
                record.progress = max(0.0, min(1.0, progress))
            if error_detail is not None:
                record.error_detail = error_detail
            self._version += 1
            return replace(record)

    def snapshot(self) -> list[TaskRecord]:
        with self._lock:
            return [replace(record) for record in self._records.values()]

    def snapshot_versioned(
        self,
        after_version: int = -1,
    ) -> tuple[int, list[TaskRecord] | None]:
        with self._lock:
            if after_version == self._version:
                return self._version, None
            return self._version, [replace(record) for record in self._records.values()]


task_store = TaskStore()
