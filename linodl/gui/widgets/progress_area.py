import re

import customtkinter as ctk

from .. import style


def parse_progress_message(message: str):
    match = re.search(r"\[(\d+)/(\d+)\]", message)
    if not match:
        return None
    current, total = int(match.group(1)), int(match.group(2))
    if total <= 0:
        return None
    return current, total


class ProgressArea(ctk.CTkFrame):
    def __init__(self, parent, on_cancel=None, **kwargs):
        super().__init__(parent, **kwargs)

        self._on_cancel = on_cancel
        self._total = 100

        self._status_label = ctk.CTkLabel(self, text="就绪", anchor="w")
        self._status_label.pack(fill="x", padx=8, pady=(8, 2))

        self._progress_bar = ctk.CTkProgressBar(self, mode="determinate")
        self._progress_bar.set(0)
        self._progress_bar.pack(fill="x", padx=8, pady=2)

        self._stats_label = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=11))
        self._stats_label.pack(fill="x", padx=8, pady=2)

        self._cancel_btn = ctk.CTkButton(
            self, text="取消", fg_color=style.COLOR_DANGER, hover_color="#c92a2a",
            command=self._on_cancel_click, width=100
        )
        self._cancel_btn.pack(anchor="e", pady=(4, 8))

    def _on_cancel_click(self):
        self._cancel_btn.configure(text="正在取消...", state="disabled")
        if self._on_cancel:
            self._on_cancel()

    def set_total(self, total: int):
        self._total = max(total, 1)
        self._progress_bar.configure(mode="determinate")
        self._progress_bar.set(0)
        self._cancel_btn.configure(text="取消", state="normal")

    def update(self, current: int, message: str = "", stats: str = ""):
        if self._progress_bar.cget("mode") == "determinate":
            parsed = parse_progress_message(message)
            if parsed:
                current, total = parsed
                self._total = total
            ratio = current / max(self._total, 1)
            self._progress_bar.set(max(0, min(ratio, 1)))
        if message:
            self._status_label.configure(text=message)
        if stats:
            self._stats_label.configure(text=stats)

    def set_result(self, success: int, skipped: int, failed: int):
        self._stats_label.configure(
            text=f"成功: {success}  |  跳过: {skipped}  |  失败: {failed}"
        )

    def show_indeterminate(self):
        self._progress_bar.configure(mode="indeterminate")
        self._progress_bar.start()

    def stop_indeterminate(self):
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        self._progress_bar.set(0)

    def set_complete(self, message: str = "完成"):
        self._progress_bar.set(1)
        self._status_label.configure(text=message)
        self._cancel_btn.configure(text="取消", state="disabled")
