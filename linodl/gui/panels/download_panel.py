import customtkinter as ctk

from ..workers import CatalogWorker, DownloadWorker, RetryWorker, ExportWorker
from ..widgets.progress_area import ProgressArea
from ..widgets.issue_tree import IssueTree
from .. import style


class DownloadPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, show_search, set_active_panel=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._show_search = show_search
        self._set_active_panel = set_active_panel or (lambda panel: None)
        self._volumes = []
        self._novel_info = None
        self._selected_names = set()
        self._downloader = None
        self._verification = None
        self._worker = None
        self._volume_checkboxes = []

        # Header
        self._header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._header_frame.pack(fill="x", padx=style.PAD_X, pady=(16, 8))

        self._title_label = ctk.CTkLabel(
            self._header_frame, text="下载", font=style.title_font()
        )
        self._title_label.pack(anchor="w")

        self._author_label = ctk.CTkLabel(self._header_frame, text="", text_color="gray")
        self._author_label.pack(anchor="w")

        # Volume list
        self._volume_frame = ctk.CTkScrollableFrame(self)
        self._volume_frame.pack(fill="both", expand=True, padx=style.PAD_X, pady=4)
        self._empty_volume_label = None
        self._show_empty_catalog()

        # Action bar
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        ctk.CTkButton(
            action_frame, text="全选", width=90,
            command=self._select_all
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            action_frame, text="取消全选", width=90,
            command=self._deselect_all
        ).pack(side="left")

        self._download_btn = ctk.CTkButton(
            action_frame, text="开始下载", fg_color=style.COLOR_SUCCESS, hover_color="#2b8a3e",
            command=self._start_download, height=36, state="disabled"
        )
        self._download_btn.pack(side="right")

        # Progress area (hidden initially)
        self._progress_area = ProgressArea(self, on_cancel=self._cancel_download)

        # Result area (hidden initially)
        self._result_frame = ctk.CTkFrame(self, fg_color="transparent")

        self._result_summary = ctk.CTkLabel(
            self._result_frame, text="", font=ctk.CTkFont(weight="bold"), anchor="w"
        )
        self._result_summary.pack(fill="x", padx=8, pady=4)

        self._issue_tree = IssueTree(self._result_frame)

        self._retry_btn = ctk.CTkButton(
            self._result_frame, text="重试失败章节", fg_color=style.COLOR_WARNING,
            hover_color="#d68910", command=self._start_retry
        )
        self._export_btn = ctk.CTkButton(
            self._result_frame, text="导出 EPUB", fg_color=style.COLOR_PRIMARY,
            hover_color=style.COLOR_PRIMARY_HOVER, command=self._start_export
        )

        # Back button
        ctk.CTkButton(
            self, text="← 返回搜索", command=self._show_search, fg_color="transparent",
            text_color="gray", height=28
        ).pack(padx=style.PAD_X, pady=(4, 8))

    def load_catalog(self, url_or_novel_info, novel_info=None):
        if novel_info is not None:
            self._volumes, self._novel_info = url_or_novel_info, novel_info
            self._show_catalog()
            return

        url = url_or_novel_info
        if not url:
            self._clear_all()
            self._show_empty_catalog()
            return

        self._clear_all()
        self._title_label.configure(text="正在获取目录...")
        self._author_label.configure(text=url)
        self._set_active_panel(self)
        self._worker = CatalogWorker(url, self._config, self._queue)
        self._worker.start()

    def on_catalog_result(self, data):
        volumes, novel_info = data
        self._volumes = volumes
        self._novel_info = novel_info
        self._show_catalog()

    def _show_catalog(self):
        self._title_label.configure(text=self._novel_info.title or "小说", text_color=("gray10", "gray90"))
        self._author_label.configure(
            text=f"作者: {self._novel_info.author or '-'}   |   共 {len(self._volumes)} 卷",
            text_color=style.COLOR_MUTED,
        )
        self._populate_volumes()
        self._download_btn.configure(state="normal" if self._volumes else "disabled")

    def _populate_volumes(self):
        self._clear_volume_widgets()
        if not self._volumes:
            self._show_empty_catalog("未读取到分卷目录。请确认目录 URL 是否正确。")
            return
        for vol in self._volumes:
            var = ctk.BooleanVar(value=False)
            label = f"{vol.name}  ({vol.text_count} 章"
            if vol.illus_count:
                label += ", 含插图"
            label += ")"

            cb = ctk.CTkCheckBox(self._volume_frame, text=label, variable=var)
            cb.pack(fill="x", padx=8, pady=2)
            self._volume_checkboxes.append((vol.name, var, cb))

    def _select_all(self):
        for name, var, cb in self._volume_checkboxes:
            var.set(True)

    def _deselect_all(self):
        for name, var, cb in self._volume_checkboxes:
            var.set(False)

    def _start_download(self):
        selected = set()
        for name, var, cb in self._volume_checkboxes:
            if var.get():
                selected.add(name)

        if not selected:
            self._author_label.configure(text="请至少选择一个分卷。", text_color=style.COLOR_WARNING)
            return

        self._selected_names = selected
        self._author_label.configure(
            text=f"作者: {self._novel_info.author or '-'}   |   已选择 {len(selected)} 卷",
            text_color=style.COLOR_MUTED,
        )
        self._hide_result()
        self._progress_area.pack(fill="x", padx=style.PAD_X, pady=8)
        total = sum(
            1 for v in self._volumes if v.name in selected
            for c in v.chapters
        )
        self._progress_area.set_total(total)
        self._progress_area.update(0, "正在准备下载...")
        self._download_btn.configure(state="disabled")

        self._set_active_panel(self)
        self._worker = DownloadWorker(
            self._volumes, selected, self._novel_info, self._config, self._queue
        )
        self._worker.start()

    def on_download_result(self, data):
        result, verification, downloader = data
        self._verification = verification
        self._downloader = downloader
        self._progress_area.pack_forget()

        summary = f"下载完成 — {result.novel_title}\n"
        summary += f"成功: {result.success}  |  跳过: {result.skipped}  |  失败: {result.failed}"
        if result.failed > 0:
            summary += f"\n输出目录: {result.output_dir}"
        self._result_summary.configure(
            text=summary,
            text_color=style.COLOR_SUCCESS if result.failed == 0 else style.COLOR_WARNING
        )

        self._issue_tree.set_issues(verification.issues if verification else [])
        self._issue_tree.pack(fill="both", expand=True, padx=8, pady=4)

        if verification and not verification.is_clean:
            self._retry_btn.pack(padx=8, pady=4)

        self._export_btn.pack(padx=8, pady=4)
        self._result_frame.pack(fill="both", expand=True, padx=style.PAD_X, pady=8)
        self._download_btn.configure(state="normal")

    def on_progress(self, msg):
        self._progress_area.update(0, msg)

    def on_error(self, msg):
        self._progress_area.pack_forget()
        self._title_label.configure(text=f"错误: {msg}", text_color=style.COLOR_DANGER)
        self._download_btn.configure(state="normal" if self._volumes else "disabled")

    def _start_retry(self):
        if not self._downloader or not self._verification:
            return
        self._downloader.prepare_retry(self._verification)
        self._hide_result()
        self._progress_area.pack(fill="x", padx=style.PAD_X, pady=8)
        self._progress_area.update(0, "正在重试失败章节...")
        self._download_btn.configure(state="disabled")

        self._set_active_panel(self)
        self._worker = RetryWorker(
            self._downloader, self._volumes, self._selected_names,
            self._novel_info, self._config, self._queue
        )
        self._worker.start()

    def _start_export(self):
        self._export_btn.configure(text="正在导出...", state="disabled")
        self._set_active_panel(self)
        worker = ExportWorker(
            self._novel_info, self._volumes, self._config.output_dir, True, self._queue
        )
        self._export_worker = worker
        worker.start()

    def on_export_result(self, paths):
        self._export_btn.configure(text="EPUB 已导出!", state="normal", fg_color="green")
        paths_list = paths if isinstance(paths, list) else [paths]
        text = self._result_summary.cget("text") + "\n\nEPUB 保存至:"
        for p in paths_list:
            text += f"\n  {p}"
        self._result_summary.configure(text=text)

    def _cancel_download(self):
        if self._worker:
            self._worker.cancel()
        self._progress_area.pack_forget()
        self._download_btn.configure(state="normal")

    def _hide_result(self):
        self._result_frame.pack_forget()
        self._issue_tree.pack_forget()
        self._retry_btn.pack_forget()
        self._export_btn.pack_forget()
        self._issue_tree.clear()

    def _clear_all(self):
        self._clear_volume_widgets()
        self._hide_result()
        self._progress_area.pack_forget()
        self._volumes = []
        self._novel_info = None
        self._selected_names = set()
        self._downloader = None
        self._verification = None
        self._download_btn.configure(state="disabled")

    def _clear_volume_widgets(self):
        for name, var, cb in self._volume_checkboxes:
            cb.destroy()
        self._volume_checkboxes.clear()
        if self._empty_volume_label is not None:
            self._empty_volume_label.destroy()
            self._empty_volume_label = None

    def _show_empty_catalog(self, text="请先从搜索页选择小说，或粘贴 linovelib 目录 URL。"):
        self._clear_volume_widgets()
        self._empty_volume_label = ctk.CTkLabel(
            self._volume_frame, text=text, text_color=style.COLOR_MUTED,
            font=style.meta_font(), anchor="center"
        )
        self._empty_volume_label.pack(fill="both", expand=True, padx=16, pady=40)
