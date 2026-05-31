import customtkinter as ctk

from ..workers import CatalogWorker, DownloadWorker, RetryWorker, ExportWorker
from ..widgets.progress_area import ProgressArea
from ..widgets.issue_tree import IssueTree


class DownloadPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, show_search, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._show_search = show_search
        self._volumes = []
        self._novel_info = None
        self._selected_names = set()
        self._downloader = None
        self._verification = None
        self._worker = None
        self._volume_checkboxes = []

        # Header
        self._header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._header_frame.pack(fill="x", padx=16, pady=(16, 8))

        self._title_label = ctk.CTkLabel(
            self._header_frame, text="Download", font=ctk.CTkFont(size=18, weight="bold")
        )
        self._title_label.pack(anchor="w")

        self._author_label = ctk.CTkLabel(self._header_frame, text="", text_color="gray")
        self._author_label.pack(anchor="w")

        # Volume list
        self._volume_frame = ctk.CTkScrollableFrame(self)
        self._volume_frame.pack(fill="both", expand=True, padx=16, pady=4)

        # Action bar
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(
            action_frame, text="Select All", width=90,
            command=self._select_all
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            action_frame, text="Deselect All", width=90,
            command=self._deselect_all
        ).pack(side="left")

        self._download_btn = ctk.CTkButton(
            action_frame, text="Start Download", fg_color="#27ae60", hover_color="#219a52",
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
            self._result_frame, text="Retry Failed Chapters", fg_color="#f39c12",
            hover_color="#d68910", command=self._start_retry
        )
        self._export_btn = ctk.CTkButton(
            self._result_frame, text="Export EPUB", fg_color="#3498db",
            hover_color="#2980b9", command=self._start_export
        )

        # Back button
        ctk.CTkButton(
            self, text="Back to Search", command=self._show_search, fg_color="transparent",
            text_color="gray", height=28
        ).pack(padx=16, pady=(4, 8))

    def load_catalog(self, url_or_novel_info, novel_info=None):
        if novel_info is not None:
            self._volumes, self._novel_info = url_or_novel_info, novel_info
            self._show_catalog()
            return

        url = url_or_novel_info
        self._clear_all()
        self._title_label.configure(text="Fetching catalog...")
        self._author_label.configure(text=url)
        self._worker = CatalogWorker(url, self._config, self._queue)
        self._worker.start()

    def on_catalog_result(self, data):
        volumes, novel_info = data
        self._volumes = volumes
        self._novel_info = novel_info
        self._show_catalog()

    def _show_catalog(self):
        self._title_label.configure(text=self._novel_info.title or "Novel")
        self._author_label.configure(
            text=f"Author: {self._novel_info.author or '-'}   |   {len(self._volumes)} volume(s)"
        )
        self._populate_volumes()
        self._download_btn.configure(state="normal")

    def _populate_volumes(self):
        self._clear_volume_widgets()
        for vol in self._volumes:
            var = ctk.BooleanVar(value=False)
            label = f"{vol.name}  ({vol.text_count} chapters"
            if vol.illus_count:
                label += f", {vol.illus_count} illustrations"
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
            return

        self._selected_names = selected
        self._hide_result()
        self._progress_area.pack(fill="x", padx=16, pady=8)
        total = sum(
            1 for v in self._volumes if v.name in selected
            for c in v.chapters
        )
        self._progress_area.set_total(total)
        self._progress_area.update(0, "Starting download...")
        self._download_btn.configure(state="disabled")

        self._worker = DownloadWorker(
            self._volumes, selected, self._novel_info, self._config, self._queue
        )
        self._worker.start()

    def on_download_result(self, data):
        result, verification, downloader = data
        self._verification = verification
        self._downloader = downloader
        self._progress_area.pack_forget()

        summary = f"Download Complete — {result.novel_title}\n"
        summary += f"Success: {result.success}  |  Skipped: {result.skipped}  |  Failed: {result.failed}"
        if result.failed > 0:
            summary += f"\nOutput: {result.output_dir}"
        self._result_summary.configure(
            text=summary,
            text_color="green" if result.failed == 0 else "#f39c12"
        )

        self._issue_tree.set_issues(verification.issues if verification else [])
        self._issue_tree.pack(fill="both", expand=True, padx=8, pady=4)

        if verification and not verification.is_clean:
            self._retry_btn.pack(padx=8, pady=4)

        self._export_btn.pack(padx=8, pady=4)
        self._result_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self._download_btn.configure(state="normal")

    def on_progress(self, msg):
        self._progress_area.update(0, msg)

    def on_error(self, msg):
        self._progress_area.pack_forget()
        self._title_label.configure(text=f"Error: {msg}", text_color="red")
        self._download_btn.configure(state="normal")

    def _start_retry(self):
        if not self._downloader or not self._verification:
            return
        self._downloader.prepare_retry(self._verification)
        self._hide_result()
        self._progress_area.pack(fill="x", padx=16, pady=8)
        self._progress_area.update(0, "Retrying failed chapters...")
        self._download_btn.configure(state="disabled")

        self._worker = RetryWorker(
            self._downloader, self._volumes, self._selected_names,
            self._novel_info, self._config, self._queue
        )
        self._worker.start()

    def _start_export(self):
        self._export_btn.configure(text="Exporting...", state="disabled")
        worker = ExportWorker(
            self._novel_info, self._volumes, self._config.output_dir, True, self._queue
        )
        self._export_worker = worker
        worker.start()

    def on_export_result(self, paths):
        self._export_btn.configure(text="EPUB Exported!", state="normal", fg_color="green")
        paths_list = paths if isinstance(paths, list) else [paths]
        text = self._result_summary.cget("text") + "\n\nEPUB saved:"
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
