import customtkinter as ctk

from ..workers import WarmupWorker
from .. import style


class WarmupPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, set_active_panel=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._set_active_panel = set_active_panel or (lambda panel: None)
        self._worker = None

        ctk.CTkLabel(self, text="Cloudflare 预热", font=style.title_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(16, 8))

        # Instructions
        instr_frame = ctk.CTkFrame(self)
        instr_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        instructions = [
            "1. 点击「开始预热」打开 CloakBrowser 窗口",
            "2. 在浏览器中完成「验证您是真人」的挑战",
            "3. 验证通过后，浏览器档案将自动保存",
            "4. 后续下载可复用此档案（减少验证频率）",
            f"5. 档案保存位置: {config.profile_dir}\\cloak",
        ]
        for line in instructions:
            ctk.CTkLabel(instr_frame, text=line, anchor="w", font=ctk.CTkFont(size=12)).pack(
                fill="x", pady=2, padx=8)

        # Start button
        self._start_btn = ctk.CTkButton(
            self, text="开始预热", command=self._start_warmup,
            fg_color="#3498db", hover_color="#2980b9", height=36
        )
        self._start_btn.pack(padx=style.PAD_X, pady=(16, 8))

        # Progress bar
        self._progress_bar = ctk.CTkProgressBar(self, mode="indeterminate")

        # Status label
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=style.PAD_X, pady=8)

    def _start_warmup(self):
        self._start_btn.configure(state="disabled", text="正在预热...")
        self._progress_bar.pack(fill="x", padx=style.PAD_X, pady=4)
        self._progress_bar.start()
        self._status_label.configure(text="正在启动 CloakBrowser...", text_color="gray")

        self._set_active_panel(self)
        self._worker = WarmupWorker(self._config, self._queue)
        self._worker.start()

    def on_progress(self, msg):
        self._status_label.configure(text=msg, text_color="gray")

    def on_result(self, msg):
        self._progress_bar.stop()
        self._progress_bar.pack_forget()
        self._start_btn.configure(text="开始预热", state="normal")
        self._status_label.configure(text=msg, text_color=style.COLOR_SUCCESS)

    def on_error(self, msg):
        self._progress_bar.stop()
        self._progress_bar.pack_forget()
        self._start_btn.configure(text="开始预热", state="normal")
        self._status_label.configure(text=f"错误: {msg}", text_color=style.COLOR_DANGER)

    def on_done(self):
        self._start_btn.configure(text="开始预热", state="normal")
