import os
import re
import customtkinter as ctk
from tkinter import filedialog

from ..workers import ExportWorker
from ..directory_scan import scan_download_directories
from .. import style
from ...models.novel import Chapter, NovelInfo, Volume


class ExportPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._subdirs = []
        self._dir_check_vars = []
        self._worker = None

        ctk.CTkLabel(self, text="导出 EPUB", font=style.title_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(16, 8))

        # Directory picker
        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        self._dir_var = ctk.StringVar(value=config.output_dir)
        self._dir_entry = ctk.CTkEntry(dir_frame, textvariable=self._dir_var)
        self._dir_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            dir_frame, text="浏览", width=80, command=self._browse_dir
        ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            dir_frame, text="扫描", width=60, command=self._scan_dir
        ).pack(side="left", padx=(4, 0))

        # Subdirectory list
        self._dir_list_frame = ctk.CTkScrollableFrame(self)
        self._dir_list_frame.pack(fill="both", expand=True, padx=style.PAD_X, pady=4)

        # Options
        option_frame = ctk.CTkFrame(self, fg_color="transparent")
        option_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        self._per_volume_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(option_frame, text="分卷导出（取消勾选则合并为单个 EPUB）", variable=self._per_volume_var).pack(side="left")

        # Action buttons
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        ctk.CTkButton(
            action_frame, text="全选", width=90, command=lambda: self._toggle_all(True)
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            action_frame, text="取消全选", width=90, command=lambda: self._toggle_all(False)
        ).pack(side="left")

        self._export_btn = ctk.CTkButton(
            action_frame, text="导出 EPUB", command=self._start_export,
            fg_color=style.COLOR_PRIMARY, hover_color=style.COLOR_PRIMARY_HOVER, width=100
        )
        self._export_btn.pack(side="right")

        # Status
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=style.PAD_X, pady=4)

        # Results
        self._result_text = ctk.CTkTextbox(self, height=120, state="disabled")
        self._result_text.pack(fill="x", padx=style.PAD_X, pady=(4, 16))

    def _browse_dir(self):
        path = filedialog.askdirectory()
        if path:
            self._dir_var.set(path)
            self._scan_dir()

    def _scan_dir(self):
        output_dir = self._dir_var.get()
        if not os.path.isdir(output_dir):
            self._clear_dir_list()
            self._status_label.configure(text="目录不存在。", text_color=style.COLOR_DANGER)
            return

        try:
            infos = scan_download_directories(output_dir)
        except NotADirectoryError:
            self._status_label.configure(text="目录不存在。", text_color=style.COLOR_DANGER)
            return

        self._subdirs = [info.name for info in infos]
        self._populate_dir_list()
        if not self._subdirs:
            text = "未找到可导出的子目录。请确认下载输出目录是否正确。"
            color = style.COLOR_WARNING
        elif len(self._subdirs) == 1:
            text = "找到 1 个子目录。"
            color = style.COLOR_SUCCESS
        else:
            text = f"找到 {len(self._subdirs)} 个子目录。"
            color = style.COLOR_SUCCESS
        self._status_label.configure(text=text, text_color=color)

    def _populate_dir_list(self):
        self._clear_dir_list()

        output_dir = self._dir_var.get()
        infos = {info.name: info for info in scan_download_directories(output_dir)}
        if not self._subdirs:
            label = ctk.CTkLabel(
                self._dir_list_frame, text="扫描后会在这里显示可导出的分卷目录。",
                text_color=style.COLOR_MUTED, font=style.meta_font()
            )
            label.pack(fill="both", expand=True, padx=16, pady=24)
            self._dir_check_vars.append((None, None, label))
            return
        for d in self._subdirs:
            txt_count = infos[d].text_count
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(
                self._dir_list_frame, text=f"{d}  ({txt_count} 章)", variable=var
            )
            cb.pack(fill="x", padx=8, pady=2)
            self._dir_check_vars.append((d, var, cb))

    def _clear_dir_list(self):
        for name, var, cb in self._dir_check_vars:
            cb.destroy()
        self._dir_check_vars.clear()

    def _toggle_all(self, selected):
        for name, var, cb in self._dir_check_vars:
            if var is not None:
                var.set(selected)

    def _start_export(self):
        selected = [name for name, var, cb in self._dir_check_vars if var is not None and var.get()]
        if not selected:
            self._status_label.configure(text="请至少选择一个目录。", text_color=style.COLOR_DANGER)
            return

        self._status_label.configure(text="正在导出...", text_color="gray")
        self._export_btn.configure(state="disabled", fg_color=style.COLOR_PRIMARY)

        output_dir = self._dir_var.get()
        novel_info, volumes = self._build_from_directories(output_dir, selected)

        self._worker = ExportWorker(
            novel_info, volumes, output_dir, self._per_volume_var.get(), self._queue, owner=self
        )
        self._worker.start()

    def on_progress(self, msg):
        self._status_label.configure(text=msg, text_color="gray")

    def on_export_result(self, paths):
        self._export_btn.configure(text="导出 EPUB", state="normal", fg_color=style.COLOR_SUCCESS)
        self._status_label.configure(text="导出完成!", text_color=style.COLOR_SUCCESS)

        paths_list = paths if isinstance(paths, list) else [paths]
        self._result_text.configure(state="normal")
        self._result_text.delete("1.0", "end")
        for p in paths_list:
            self._result_text.insert("end", f"{p}\n")
        self._result_text.configure(state="disabled")

    def on_error(self, msg):
        self._export_btn.configure(text="导出 EPUB", state="normal", fg_color=style.COLOR_PRIMARY)
        self._status_label.configure(text=f"导出失败: {msg}", text_color=style.COLOR_DANGER)

    def is_busy(self):
        worker = getattr(self, "_worker", None)
        return worker is not None and worker.is_alive()

    def _build_from_directories(self, output_dir, selected_dirs):
        title = selected_dirs[0] if len(selected_dirs) == 1 else self._derive_batch_title(selected_dirs)
        volumes = [self._build_volume_from_directory(output_dir, d) for d in selected_dirs]
        return NovelInfo(title=title), volumes

    def _build_volume_from_directory(self, output_dir, directory):
        vol_path = os.path.join(output_dir, directory)
        vol = Volume(name=directory)
        for fname in sorted(os.listdir(vol_path)):
            if not fname.endswith(".txt"):
                continue
            name_no_ext, _ = os.path.splitext(fname)
            match = re.match(r"^(\d+)_(.+)$", name_no_ext)
            if match:
                idx = int(match.group(1))
                title = match.group(2)
            else:
                idx = len(vol.chapters) + 1
                title = name_no_ext
            vol.chapters.append(Chapter(
                index=idx, url="", title=title,
                is_illustration=False, volume_name=directory,
            ))
        return vol

    @staticmethod
    def _derive_batch_title(selected_dirs):
        common = os.path.commonprefix(selected_dirs).strip(" -_.")
        return common or "batch"
