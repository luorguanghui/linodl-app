import os
import re
import customtkinter as ctk
from tkinter import filedialog

from ..workers import VerifyWorker
from ..widgets.issue_tree import IssueTree
from ...models.novel import Chapter, Volume


class VerifyPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._subdirs = []
        self._dir_check_vars = []

        ctk.CTkLabel(self, text="Verify Downloads", font=ctk.CTkFont(size=18, weight="bold")).pack(
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

        # Action buttons
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(
            action_frame, text="Select All", width=90, command=lambda: self._toggle_all(True)
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            action_frame, text="Deselect All", width=90, command=lambda: self._toggle_all(False)
        ).pack(side="left")

        self._verify_btn = ctk.CTkButton(
            action_frame, text="Verify", command=self._start_verify,
            fg_color="#27ae60", hover_color="#219a52", width=100
        )
        self._verify_btn.pack(side="right")

        # Status
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=16, pady=4)

        # Results
        self._issue_tree = IssueTree(self)
        self._issue_tree.pack(fill="both", expand=True, padx=16, pady=(4, 16))

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
            illus_dir = os.path.join(output_dir, d, "插图")
            img_count = len(os.listdir(illus_dir)) if os.path.isdir(illus_dir) else 0

            var = ctk.BooleanVar(value=False)
            label = f"{d}  ({txt_count} chapters, {img_count} images)"
            cb = ctk.CTkCheckBox(self._dir_list_frame, text=label, variable=var)
            cb.pack(fill="x", padx=8, pady=2)
            self._dir_check_vars.append((d, var, cb))

    def _toggle_all(self, selected):
        for name, var, cb in self._dir_check_vars:
            var.set(selected)

    def _start_verify(self):
        selected = [name for name, var, cb in self._dir_check_vars if var.get()]
        if not selected:
            self._status_label.configure(text="Select at least one directory.", text_color="red")
            return

        self._status_label.configure(text="Verifying...", text_color="gray")
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

        self._worker = VerifyWorker(volumes, set(selected), output_dir, self._queue)
        self._worker.start()

    def on_verify_result(self, verification):
        self._verify_btn.configure(state="normal")
        self._issue_tree.set_issues(verification.issues)

        if verification.is_clean:
            self._status_label.configure(
                text=f"All {verification.total_expected} items verified successfully.",
                text_color="green"
            )
        else:
            self._status_label.configure(
                text=f"Issues found: {verification.issue_count}",
                text_color="red"
            )

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
