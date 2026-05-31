import customtkinter as ctk


class ProgressArea(ctk.CTkFrame):
    def __init__(self, parent, on_cancel=None, **kwargs):
        super().__init__(parent, **kwargs)

        self._on_cancel = on_cancel

        self._status_label = ctk.CTkLabel(self, text="Ready", anchor="w")
        self._status_label.pack(fill="x", padx=8, pady=(8, 2))

        self._progress_bar = ctk.CTkProgressBar(self, mode="determinate")
        self._progress_bar.set(0)
        self._progress_bar.pack(fill="x", padx=8, pady=2)

        self._stats_label = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=11))
        self._stats_label.pack(fill="x", padx=8, pady=2)

        self._cancel_btn = ctk.CTkButton(
            self, text="Cancel", fg_color="#e74c3c", hover_color="#c0392b",
            command=self._on_cancel_click, width=100
        )
        self._cancel_btn.pack(pady=(2, 8))

    def _on_cancel_click(self):
        self._cancel_btn.configure(text="Cancelling...", state="disabled")
        if self._on_cancel:
            self._on_cancel()

    def set_total(self, total: int):
        self._progress_bar.configure(determinate_speed=1 / max(total, 1))

    def update(self, current: int, message: str = "", stats: str = ""):
        self._progress_bar.set(current / max(self._progress_bar.cget("determinate_speed") ** (-1), 1) if self._progress_bar.cget("mode") == "determinate" else 0)
        ratio = current / max(getattr(self, '_total', 100), 1)
        if self._progress_bar.cget("mode") == "determinate":
            self._progress_bar.set(ratio)
        if message:
            self._status_label.configure(text=message)
        if stats:
            self._stats_label.configure(text=stats)

    def set_result(self, success: int, skipped: int, failed: int):
        self._stats_label.configure(
            text=f"Success: {success}  |  Skipped: {skipped}  |  Failed: {failed}"
        )

    def show_indeterminate(self):
        self._progress_bar.configure(mode="indeterminate")
        self._progress_bar.start()

    def stop_indeterminate(self):
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        self._progress_bar.set(0)

    def set_complete(self, message: str = "Complete"):
        self._progress_bar.set(1)
        self._status_label.configure(text=message)
        self._cancel_btn.configure(text="Cancel", state="disabled")
