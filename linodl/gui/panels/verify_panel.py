import os
import re
import customtkinter as ctk
from tkinter import filedialog

from ..workers import VerifyWorker
from ..directory_scan import scan_download_directories
from ..widgets.issue_tree import IssueTree
from .. import style
from ...models.novel import Chapter, Volume


class VerifyPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, set_active_panel=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._set_active_panel = set_active_panel or (lambda panel: None)
        self._subdirs = []
        self._dir_check_vars = []

        ctk.CTkLabel(self, text="校验下载", font=style.title_font()).pack(
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

        # Action buttons
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        ctk.CTkButton(
            action_frame, text="全选", width=90, command=lambda: self._toggle_all(True)
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            action_frame, text="取消全选", width=90, command=lambda: self._toggle_all(False)
        ).pack(side="left")

        self._verify_btn = ctk.CTkButton(
            action_frame, text="开始校验", command=self._start_verify,
            fg_color=style.COLOR_SUCCESS, hover_color="#2b8a3e", width=100
        )
        self._verify_btn.pack(side="right")

        # Status
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=style.PAD_X, pady=4)

        # Results
        self._issue_tree = IssueTree(self)
        self._issue_tree.pack(fill="both", expand=True, padx=style.PAD_X, pady=(4, 16))

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
            infos = scan_download_directories(output_dir, include_images=True)
        except NotADirectoryError:
            self._status_label.configure(text="目录不存在。", text_color=style.COLOR_DANGER)
            return

        self._subdirs = [info.name for info in infos]
        self._populate_dir_list()
        if not self._subdirs:
            text = "未找到可校验的子目录。请确认下载输出目录是否正确。"
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
        infos = {info.name: info for info in scan_download_directories(output_dir, include_images=True)}
        if not self._subdirs:
            label = ctk.CTkLabel(
                self._dir_list_frame, text="扫描后会在这里显示可校验的分卷目录。",
                text_color=style.COLOR_MUTED, font=style.meta_font()
            )
            label.pack(fill="both", expand=True, padx=16, pady=40)
            self._dir_check_vars.append((None, None, label))
            return
        for d in self._subdirs:
            txt_count = infos[d].text_count
            img_count = infos[d].image_count

            var = ctk.BooleanVar(value=False)
            label = f"{d}  ({txt_count} 章, {img_count} 图)"
            cb = ctk.CTkCheckBox(self._dir_list_frame, text=label, variable=var)
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

    def _start_verify(self):
        selected = [name for name, var, cb in self._dir_check_vars if var is not None and var.get()]
        if not selected:
            self._status_label.configure(text="请至少选择一个目录。", text_color=style.COLOR_DANGER)
            return

        self._status_label.configure(text="正在校验...", text_color="gray")
        self._verify_btn.configure(state="disabled")

        output_dir = self._dir_var.get()
        volumes = []
        for directory in selected:
            vol = self._build_volume_from_directory(output_dir, directory)
            illus_dir = os.path.join(output_dir, directory, "插图")
            if os.path.isdir(illus_dir) and os.listdir(illus_dir):
                vol.chapters.append(Chapter(
                    index=0, url="", title="插图",
                    is_illustration=True, volume_name=directory,
                ))
            volumes.append(vol)

        self._set_active_panel(self)
        self._worker = VerifyWorker(volumes, set(selected), output_dir, self._queue)
        self._worker.start()

    def on_verify_result(self, verification):
        self._verify_btn.configure(state="normal")
        self._issue_tree.set_issues(verification.issues)

        if verification.is_clean:
            self._status_label.configure(
                text=f"全部 {verification.total_expected} 项校验通过。",
                text_color=style.COLOR_SUCCESS
            )
        else:
            self._status_label.configure(
                text=f"发现问题: {verification.issue_count} 项",
                text_color=style.COLOR_DANGER
            )

    def on_error(self, msg):
        self._verify_btn.configure(state="normal")
        self._status_label.configure(text=f"校验失败: {msg}", text_color=style.COLOR_DANGER)

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
