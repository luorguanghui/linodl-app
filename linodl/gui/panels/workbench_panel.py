"""Unified reading workbench for search, catalog selection, and tasks."""

from __future__ import annotations

from urllib.parse import urlparse
import os

import customtkinter as ctk

from ...models.novel import NovelInfo
from .. import style
from ..directory_scan import scan_download_directories
from ..tasks import task_store
from ..widgets.task_center import TaskCenter
from ..widgets.workflow_steps import WorkflowSteps
from .download_panel import DownloadPanel
from .search_panel import SearchPanel


def classify_workbench_input(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "empty"
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        host = (parsed.hostname or "").lower()
        if host == "linovelib.com" or host.endswith(".linovelib.com"):
            return "url"
        return "invalid_url"
    return "query"


class WorkbenchPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._config = config
        self._queue = message_queue
        self._active_body = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_command_bar()
        self._build_workspace()
        self.show_search()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=style.PAD_X, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)

        title_group = ctk.CTkFrame(header, fg_color="transparent")
        title_group.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_group,
            text="阅读工作台",
            font=style.display_font(),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_group,
            text="从作品查找到内容校验，一个窗口持续完成。",
            text_color=style.COLOR_MUTED,
            font=style.body_font(),
        ).pack(anchor="w", pady=(2, 0))

        self._profile_badge = ctk.CTkLabel(
            header,
            text="● 浏览档案可用",
            height=30,
            corner_radius=15,
            fg_color=style.COLOR_SUCCESS_SOFT,
            text_color=style.COLOR_SUCCESS,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._profile_badge.grid(row=0, column=1, sticky="e")

        self._steps = WorkflowSteps(header)
        self._steps.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(18, 0),
        )

    def _build_command_bar(self):
        command = ctk.CTkFrame(
            self,
            corner_radius=style.CARD_RADIUS,
            fg_color=style.COLOR_CARD,
            border_width=1,
            border_color=style.COLOR_BORDER,
        )
        command.grid(row=1, column=0, sticky="ew", padx=style.PAD_X, pady=8)
        command.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            command,
            text="查找作品或粘贴目录 URL",
            font=style.section_font(),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6))

        self._entry = ctk.CTkEntry(
            command,
            height=42,
            placeholder_text="输入作品名，或 https://www.linovelib.com/novel/…/catalog",
            border_color=style.COLOR_BORDER_STRONG,
        )
        self._entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(0, 14))
        self._entry.bind("<Return>", lambda _event: self._submit())

        self._submit_button = ctk.CTkButton(
            command,
            text="开始",
            width=104,
            height=42,
            corner_radius=10,
            fg_color=style.COLOR_PRIMARY,
            hover_color=style.COLOR_PRIMARY_HOVER,
            command=self._submit,
        )
        self._submit_button.grid(row=1, column=1, padx=(0, 16), pady=(0, 14))

        self._input_status = ctk.CTkLabel(
            command,
            text="",
            anchor="w",
            font=style.meta_font(),
        )
        self._input_status.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        self._input_status.grid_remove()

    def _build_workspace(self):
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.grid(row=2, column=0, sticky="nsew", padx=style.PAD_X, pady=(4, 14))
        workspace.grid_columnconfigure(0, weight=3)
        workspace.grid_columnconfigure(1, weight=2, minsize=280)
        workspace.grid_rowconfigure(0, weight=1)

        self._body = ctk.CTkFrame(
            workspace,
            corner_radius=style.CARD_RADIUS,
            fg_color=style.COLOR_CARD,
            border_width=1,
            border_color=style.COLOR_BORDER,
        )
        self._body.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self._search_panel = SearchPanel(
            self._body,
            self._config,
            self._queue,
            on_novel_selected=self.open_novel,
            on_url_download=self.open_url,
            embedded=True,
        )
        self._download_panel = DownloadPanel(
            self._body,
            self._config,
            self._queue,
            show_search=self.show_search,
            embedded=True,
            on_step_changed=self._steps.set_active,
        )

        side = ctk.CTkFrame(workspace, fg_color="transparent")
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(1, weight=1)

        self._recent_card = ctk.CTkFrame(
            side,
            corner_radius=style.CARD_RADIUS,
            fg_color=style.COLOR_CARD,
            border_width=1,
            border_color=style.COLOR_BORDER,
        )
        self._recent_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._render_recent_archives()

        self._task_center = TaskCenter(side)
        self._task_center.grid(row=1, column=0, sticky="nsew")

    def _render_recent_archives(self):
        ctk.CTkLabel(
            self._recent_card,
            text="最近阅读档案",
            font=style.section_font(),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        try:
            output_dir = os.path.abspath(os.path.expanduser(self._config.output_dir))
            archives = scan_download_directories(output_dir)[:3]
        except (OSError, NotADirectoryError):
            archives = []

        if not archives:
            ctk.CTkLabel(
                self._recent_card,
                text="完成首次下载后，最近分卷会显示在这里。",
                wraplength=260,
                justify="left",
                text_color=style.COLOR_MUTED,
                font=style.meta_font(),
            ).pack(anchor="w", padx=14, pady=(2, 12))
            return

        for archive in archives:
            row = ctk.CTkFrame(
                self._recent_card,
                fg_color=style.COLOR_CARD_ELEVATED,
                corner_radius=8,
            )
            row.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(
                row,
                text=archive.name,
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", fill="x", expand=True, padx=9, pady=7)
            ctk.CTkLabel(
                row,
                text=f"{archive.text_count} 章",
                text_color=style.COLOR_MUTED,
                font=style.meta_font(),
            ).pack(side="right", padx=9)
        ctk.CTkFrame(
            self._recent_card,
            fg_color="transparent",
            height=7,
        ).pack()

    def _submit(self):
        value = self._entry.get().strip()
        kind = classify_workbench_input(value)
        if kind == "empty":
            self._show_input_error("请输入作品名称或目录 URL。")
            return
        if kind == "invalid_url":
            self._show_input_error("目前仅支持 linovelib.com 的作品或目录链接。")
            return

        self._input_status.grid_remove()
        if kind == "url":
            self.open_url(value)
        else:
            self.show_search()
            self._search_panel.start_search(value)

    def _show_input_error(self, message: str):
        self._input_status.configure(
            text=message,
            text_color=style.COLOR_DANGER,
        )
        self._input_status.grid()

    def _show_body(self, panel):
        if self._active_body is panel:
            return
        if self._active_body is not None:
            self._active_body.pack_forget()
        panel.pack(fill="both", expand=True)
        self._active_body = panel

    def show_search(self):
        self._steps.set_active("search")
        self._show_body(self._search_panel)

    def open_novel(self, novel: NovelInfo):
        if not novel.catalog_url:
            novel.catalog_url = (
                f"https://www.linovelib.com/novel/{novel.novel_id}/catalog"
            )
        self.open_url(novel.catalog_url)

    def open_url(self, url: str):
        self._steps.set_active("volumes")
        self._show_body(self._download_panel)
        self._download_panel.load_catalog(url)

    def refresh_tasks(self, records=None):
        self._task_center.render(records if records is not None else task_store.snapshot())

    def set_profile_health(self, text: str, level: str = "success"):
        colors = {
            "success": (style.COLOR_SUCCESS_SOFT, style.COLOR_SUCCESS),
            "warning": (style.COLOR_WARNING_SOFT, style.COLOR_WARNING),
            "danger": (style.COLOR_DANGER_SOFT, style.COLOR_DANGER),
        }
        background, foreground = colors.get(level, colors["success"])
        self._profile_badge.configure(
            text=f"● {text}",
            fg_color=background,
            text_color=foreground,
        )

    def is_busy(self):
        return self._search_panel.is_busy() or self._download_panel.is_busy()
