import customtkinter as ctk

from ..workers import WarmupWorker


class WarmupPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._worker = None

        ctk.CTkLabel(self, text="Cloudflare Warmup", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))

        # Instructions
        instr_frame = ctk.CTkFrame(self)
        instr_frame.pack(fill="x", padx=16, pady=4)

        instructions = [
            "1. Click 'Start Warmup' to open the CloakBrowser window",
            "2. In the browser, complete the 'Verify you are human' challenge",
            "3. After passing verification, the browser profile is saved automatically",
            "4. Subsequent downloads will reuse this profile (fewer verifications)",
            f"5. Profile saved to: {config.profile_dir}\\cloak",
        ]
        for line in instructions:
            ctk.CTkLabel(instr_frame, text=line, anchor="w", font=ctk.CTkFont(size=12)).pack(
                fill="x", pady=2, padx=8)

        # Start button
        self._start_btn = ctk.CTkButton(
            self, text="Start Warmup", command=self._start_warmup,
            fg_color="#3498db", hover_color="#2980b9", height=36
        )
        self._start_btn.pack(padx=16, pady=(16, 8))

        # Progress bar
        self._progress_bar = ctk.CTkProgressBar(self, mode="indeterminate")

        # Status label
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=16, pady=8)

    def _start_warmup(self):
        self._start_btn.configure(state="disabled", text="Warming up...")
        self._progress_bar.pack(fill="x", padx=16, pady=4)
        self._progress_bar.start()
        self._status_label.configure(text="Starting CloakBrowser...", text_color="gray")

        self._worker = WarmupWorker(self._config, self._queue)
        self._worker.start()

    def on_progress(self, msg):
        self._status_label.configure(text=msg, text_color="gray")

    def on_result(self, msg):
        self._progress_bar.stop()
        self._progress_bar.pack_forget()
        self._start_btn.configure(text="Start Warmup", state="normal")
        self._status_label.configure(text=msg, text_color="green")

    def on_error(self, msg):
        self._progress_bar.stop()
        self._progress_bar.pack_forget()
        self._start_btn.configure(text="Start Warmup", state="normal")
        self._status_label.configure(text=f"Error: {msg}", text_color="red")

    def on_done(self):
        self._start_btn.configure(text="Start Warmup", state="normal")
