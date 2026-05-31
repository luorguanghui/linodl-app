import os
import customtkinter as ctk
from tkinter import filedialog


class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue

        ctk.CTkLabel(self, text="Account", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=16, pady=(12, 4))

        self._username_var = ctk.StringVar(value=config.username or "")
        self._add_field("Username / Email", self._username_var)

        self._password_var = ctk.StringVar(value=config.password or "")
        self._add_field("Password", self._password_var, show="*")

        ctk.CTkLabel(self, text="Download", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 4))

        self._output_dir_var = ctk.StringVar(value=config.output_dir)
        self._add_field("Output Directory", self._output_dir_var, browse=True)

        self._headless_var = ctk.BooleanVar(value=config.headless)
        self._add_switch("Headless Mode", self._headless_var)

        self._anti_bot_var = ctk.StringVar(value=config.anti_bot_mode)
        self._add_options("Anti-Bot Mode", self._anti_bot_var, ["auto", "playwright", "cloak"])

        self._profile_dir_var = ctk.StringVar(value=config.profile_dir)
        self._add_field("Browser Profile Dir", self._profile_dir_var, browse=True)

        ctk.CTkLabel(self, text="Network", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 4))

        self._proxy_var = ctk.StringVar(value=config.proxy or "")
        self._add_field("Proxy URL (optional)", self._proxy_var)

        self._geoip_var = ctk.BooleanVar(value=config.geoip)
        self._add_switch("GeoIP", self._geoip_var)

        self._status_label = ctk.CTkLabel(self, text="", text_color="green")
        self._status_label.pack(anchor="w", padx=16, pady=(12, 4))

        save_btn = ctk.CTkButton(
            self, text="Save Settings", command=self._save, fg_color="#27ae60",
            hover_color="#219a52", height=36
        )
        save_btn.pack(padx=16, pady=(4, 8))

        if config.has_credentials():
            logout_btn = ctk.CTkButton(
                self, text="Logout (Clear Credentials)", command=self._logout,
                fg_color="#e74c3c", hover_color="#c0392b", height=32
            )
            logout_btn.pack(padx=16, pady=(4, 12))

    def _add_field(self, label_text, variable, show=None, browse=False):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(frame, text=label_text, width=140, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(frame, textvariable=variable, show=show or "")
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        if browse:
            path = variable
            ctk.CTkButton(
                frame, text="Browse", width=70, command=lambda p=path: self._browse_dir(p)
            ).pack(side="left", padx=(4, 0))

    def _add_switch(self, label_text, variable):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(frame, text=label_text, width=140, anchor="w").pack(side="left")
        ctk.CTkSwitch(frame, variable=variable, text="").pack(side="left", padx=(8, 0))

    def _add_options(self, label_text, variable, values):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(frame, text=label_text, width=140, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(frame, variable=variable, values=values).pack(side="left", padx=(8, 0))

    def _browse_dir(self, variable):
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _save(self):
        self._config.username = self._username_var.get()
        self._config.password = self._password_var.get()
        self._config.output_dir = self._output_dir_var.get()
        self._config.headless = self._headless_var.get()
        self._config.anti_bot_mode = self._anti_bot_var.get()
        self._config.profile_dir = self._profile_dir_var.get()
        self._config.proxy = self._proxy_var.get() or ""
        self._config.geoip = self._geoip_var.get()
        self._status_label.configure(text="Settings saved to ~/.linovelib.ini", text_color="green")

    def _logout(self):
        self._config.set_credentials("", "")
        self._username_var.set("")
        self._password_var.set("")
        self._status_label.configure(text="Credentials cleared.", text_color="#e74c3c")
