import os
import re
import customtkinter as ctk
from tkinter import filedialog

from ..workers import ExportWorker
from ...models.novel import Chapter, NovelInfo, Volume


class ExportPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._subdirs = []
        self._dir_check_vars = []

        ctk.CTkLabel(self, text="Export EPUB", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))

        # Directory picker
        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=16, pady=4)

        self._dir_var = ctk.StringVar(value=config.output_dir)
        self._dir_entry = ctk.CTkEntry(dir_frame, textvariable=self._dir_var)
        self._dir_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            dir_frame, text="Browse", width=80, command=self._browse_dir
        ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            dir_frame, text="Scan", width=60, command=self._scan_dir
        ).pack(side="left", padx=(4, 0))

        # Subdirectory list
        self._dir_list_frame = ctk.CTkScrollableFrame(self)
        self._dir_list_frame.pack(fill="both", expand=True, padx=16, pady=4)

        # Options
        option_frame = ctk.CTkFrame(self, fg_color="transparent")
        option_frame.pack(fill="x", padx=16, pady=4)

        self._per_volume_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(option_frame, text="Export per volume (uncheck for single EPUB)", variable=self._per_volume_var).pack(side="left")

        # Action buttons
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(
            action_frame, text="Select All", width=90, command=lambda: self._toggle_all(True)
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            action_frame, text="Deselect All", width=90, command=lambda: self._toggle_all(False)
        ).pack(side="left")

        self._export_btn = ctk.CTkButton(
            action_frame, text="Export EPUB", command=self._start_export,
            fg_color="#3498db", hover_color="#2980b9", width=100
        )
        self._export_btn.pack(side="right")

        # Status
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=16, pady=4)

        # Results
        self._result_text = ctk.CTkTextbox(self, height=120, state="disabled")
        self._result_text.pack(fill="x", padx=16, pady=(4, 16))

    def _browse_dir(self):
        path = filedialog.askdirectory()
        if path:
            self._dir_var.set(path)
            self._scan_dir()

    def _scan_dir(self):
        output_dir = self._dir_var.get()
        if not os.path.isdir(output_dir):
            self._status_label.configure(text="Directory does not exist.", text_color="red")
            return

        self._subdirs = [
            d for d in os.listdir(output_dir)
            if os.path.isdir(os.path.join(output_dir, d))
        ]
        self._populate_dir_list()
        self._status_label.configure(
            text=f"Found {len(self._subdirs)} subdirector{'y' if len(self._subdirs)==1 else 'ies'}.",
            text_color="green"
        )

    def _populate_dir_list(self):
        for var, cb in self._dir_check_vars:
            cb.destroy()
        self._dir_check_vars.clear()

        output_dir = self._dir_var.get()
        for d in self._subdirs:
            txt_count = len([
                f for f in os.listdir(os.path.join(output_dir, d))
                if f.endswith(".txt")
            ])
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(
                self._dir_list_frame, text=f"{d}  ({txt_count} chapters)", variable=var
            )
            cb.pack(fill="x", padx=8, pady=2)
            self._dir_check_vars.append((d, var, cb))

    def _toggle_all(self, selected):
        for name, var, cb in self._dir_check_vars:
            var.set(selected)

    def _start_export(self):
        selected = [name for name, var, cb in self._dir_check_vars if var.get()]
        if not selected:
            self._status_label.configure(text="Select at least one directory.", text_color="red")
            return

        self._status_label.configure(text="Exporting...", text_color="gray")
        self._export_btn.configure(state="disabled")

        output_dir = self._dir_var.get()
        novel_info, volumes = self._build_from_directories(output_dir, selected)

        self._worker = ExportWorker(
            novel_info, volumes, output_dir, self._per_volume_var.get(), self._queue
        )
        self._worker.start()

    def on_export_result(self, paths):
        self._export_btn.configure(text="Export EPUB", state="normal", fg_color="#27ae60")
        self._status_label.configure(text="Export complete!", text_color="green")

        paths_list = paths if isinstance(paths, list) else [paths]
        self._result_text.configure(state="normal")
        self._result_text.delete("1.0", "end")
        for p in paths_list:
            self._result_text.insert("end", f"{p}\n")
        self._result_text.configure(state="disabled")

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
