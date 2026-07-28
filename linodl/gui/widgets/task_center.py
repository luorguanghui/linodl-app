"""Task-center widgets for the reading workbench."""

from __future__ import annotations

from collections.abc import Sequence

import customtkinter as ctk

from .. import style
from ..tasks import TaskRecord, TaskStatus


_STATUS_PRIORITY = {
    TaskStatus.RUNNING: 0,
    TaskStatus.WAITING_FOR_PROFILE: 1,
    TaskStatus.WAITING_FOR_VERIFICATION: 2,
    TaskStatus.CANCELLING: 3,
    TaskStatus.QUEUED: 4,
    TaskStatus.FAILED: 5,
    TaskStatus.COMPLETED: 6,
    TaskStatus.CANCELLED: 7,
}

_STATUS_LABELS = {
    TaskStatus.QUEUED: "排队中",
    TaskStatus.WAITING_FOR_PROFILE: "等待档案",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.WAITING_FOR_VERIFICATION: "等待验证",
    TaskStatus.CANCELLING: "正在取消",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.FAILED: "失败",
    TaskStatus.COMPLETED: "已完成",
}

_STATUS_COLORS = {
    TaskStatus.WAITING_FOR_PROFILE: style.COLOR_WARNING,
    TaskStatus.WAITING_FOR_VERIFICATION: style.COLOR_WARNING,
    TaskStatus.CANCELLING: style.COLOR_WARNING,
    TaskStatus.FAILED: style.COLOR_DANGER,
    TaskStatus.COMPLETED: style.COLOR_SUCCESS,
    TaskStatus.CANCELLED: style.COLOR_MUTED,
}


def sort_task_records(records: Sequence[TaskRecord]) -> list[TaskRecord]:
    """Return active tasks first while keeping creation order within a state."""
    return sorted(
        records,
        key=lambda record: _STATUS_PRIORITY.get(record.status, 99),
    )


def task_actions(record: TaskRecord) -> tuple[str, ...]:
    if record.status in {
        TaskStatus.QUEUED,
        TaskStatus.WAITING_FOR_PROFILE,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_FOR_VERIFICATION,
    }:
        return ("cancel",)
    if record.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
        return ("restore",)
    return ()


class TaskCenter(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_cancel=None,
        on_restore=None,
        **kwargs,
    ):
        super().__init__(
            parent,
            corner_radius=style.CARD_RADIUS,
            fg_color=style.COLOR_CARD,
            border_width=1,
            border_color=style.COLOR_BORDER,
            **kwargs,
        )
        self._on_cancel = on_cancel or (lambda _task_id: None)
        self._on_restore = on_restore or (lambda _record: None)
        self._signature = None
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        ctk.CTkLabel(
            header,
            text="任务中心",
            font=style.section_font(),
        ).pack(side="left")
        self._count_label = ctk.CTkLabel(
            header,
            text="0 项",
            font=style.meta_font(),
            text_color=style.COLOR_MUTED,
        )
        self._count_label.pack(side="right")

        self._list = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=260,
        )
        self._list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._empty = None
        self.render([])

    def render(self, records: Sequence[TaskRecord]):
        signature = tuple(
            (
                record.id,
                record.status,
                record.detail,
                record.progress,
                record.error_detail,
            )
            for record in records
        )
        if signature == self._signature:
            return
        self._signature = signature
        for child in self._list.winfo_children():
            child.destroy()

        ordered = sort_task_records(records)[:8]
        self._count_label.configure(text=f"{len(records)} 项")
        if not ordered:
            self._empty = ctk.CTkLabel(
                self._list,
                text="任务将在这里持续显示\n切换页面也不会丢失进度",
                justify="left",
                text_color=style.COLOR_MUTED,
                font=style.meta_font(),
            )
            self._empty.pack(fill="x", padx=8, pady=18)
            return

        for record in ordered:
            self._render_record(record)

    def _render_record(self, record: TaskRecord):
        row = ctk.CTkFrame(
            self._list,
            corner_radius=10,
            fg_color=style.COLOR_CARD_ELEVATED,
        )
        row.pack(fill="x", padx=2, pady=4)

        title = ctk.CTkLabel(
            row,
            text=record.title,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=(8, 1))
        row.grid_columnconfigure(0, weight=1)

        status = ctk.CTkLabel(
            row,
            text=_STATUS_LABELS.get(record.status, record.status.value),
            text_color=_STATUS_COLORS.get(record.status, style.COLOR_PRIMARY),
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        status.grid(row=0, column=1, padx=(2, 10), pady=(8, 1))

        detail = record.detail or "等待开始"
        ctk.CTkLabel(
            row,
            text=detail,
            anchor="w",
            justify="left",
            wraplength=250,
            text_color=style.COLOR_MUTED,
            font=style.meta_font(),
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=10,
            pady=(1, 8),
        )

        actions = task_actions(record)
        if "cancel" in actions:
            ctk.CTkButton(
                row,
                text="取消",
                width=62,
                height=26,
                fg_color="transparent",
                border_width=1,
                border_color=style.COLOR_BORDER_STRONG,
                text_color=style.COLOR_WARNING,
                command=lambda task_id=record.id: self._on_cancel(task_id),
            ).grid(row=2, column=1, sticky="e", padx=10, pady=(0, 8))
        elif "restore" in actions:
            ctk.CTkButton(
                row,
                text="恢复输入",
                width=80,
                height=26,
                fg_color=style.COLOR_PRIMARY,
                hover_color=style.COLOR_PRIMARY_HOVER,
                command=lambda item=record: self._on_restore(item),
            ).grid(row=2, column=1, sticky="e", padx=10, pady=(0, 8))

        if record.error_detail:
            detail_label = ctk.CTkLabel(
                row,
                text=record.error_detail,
                anchor="w",
                justify="left",
                wraplength=240,
                text_color=style.COLOR_DANGER,
                font=style.meta_font(),
            )

            def toggle_detail():
                if detail_label.winfo_manager():
                    detail_label.grid_remove()
                else:
                    detail_label.grid(
                        row=3,
                        column=0,
                        columnspan=2,
                        sticky="ew",
                        padx=10,
                        pady=(0, 8),
                    )

            ctk.CTkButton(
                row,
                text="技术详情",
                width=72,
                height=26,
                fg_color="transparent",
                text_color=style.COLOR_MUTED,
                command=toggle_detail,
            ).grid(row=2, column=0, sticky="w", padx=10, pady=(0, 8))
