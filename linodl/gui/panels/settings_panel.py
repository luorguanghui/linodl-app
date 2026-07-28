import os
import customtkinter as ctk
from tkinter import filedialog

from .. import style


class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, config, message_queue, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue

        ctk.CTkLabel(self, text="设置", font=style.display_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(18, 2)
        )
        ctk.CTkLabel(
            self,
            text="配置下载、浏览档案与网络环境。",
            text_color=style.COLOR_MUTED,
            font=style.body_font(),
        ).pack(anchor="w", padx=style.PAD_X, pady=(0, 12))

        self._add_browser_profile_card()

        ctk.CTkLabel(self, text="账号", font=style.section_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(16, 8))

        self._username_var = ctk.StringVar(value=config.username or "")
        self._add_field("用户名 / 邮箱", self._username_var)

        self._password_var = ctk.StringVar(value=config.password or "")
        self._add_field("密码", self._password_var, show="*")

        ctk.CTkLabel(self, text="下载", font=style.section_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(16, 4))

        self._output_dir_var = ctk.StringVar(value=config.output_dir)
        self._add_field("输出目录", self._output_dir_var, browse=True)

        self._headless_var = ctk.BooleanVar(value=config.headless)
        self._add_switch("无头模式", self._headless_var)

        self._anti_bot_var = ctk.StringVar(value=config.anti_bot_mode)
        self._add_options("反爬模式", self._anti_bot_var, ["auto", "playwright", "cloak"])

        self._profile_dir_var = ctk.StringVar(value=config.profile_dir)
        self._add_field("浏览器档案目录", self._profile_dir_var, browse=True)

        ctk.CTkLabel(self, text="网络", font=style.section_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(16, 4))

        self._proxy_var = ctk.StringVar(value=config.proxy or "")
        self._proxy_entry = self._add_field("代理 URL（可选）", self._proxy_var)

        self._geoip_var = ctk.BooleanVar(value=config.geoip)
        self._geoip_switch = self._add_switch(
            "GeoIP",
            self._geoip_var,
            help_text="根据代理出口匹配语言与时区；必须先配置代理。",
        )
        self._proxy_var.trace_add("write", lambda *_args: self._sync_geoip_state())
        self._sync_geoip_state()

        ctk.CTkLabel(self, text="界面", font=style.section_font()).pack(
            anchor="w", padx=style.PAD_X, pady=(16, 4))

        self._theme_var = ctk.StringVar(value=config.theme)
        self._add_options("主题", self._theme_var, ["auto", "light", "dark"])

        self._status_label = ctk.CTkLabel(self, text="", text_color=style.COLOR_SUCCESS)
        self._status_label.pack(anchor="w", padx=style.PAD_X, pady=(12, 4))

        save_btn = ctk.CTkButton(
            self, text="保存设置", command=self._save, fg_color=style.COLOR_SUCCESS,
            hover_color="#2b8a3e", height=36
        )
        save_btn.pack(padx=style.PAD_X, pady=(4, 8))

        if config.has_credentials():
            logout_btn = ctk.CTkButton(
                self, text="退出账号（清除凭据）", command=self._logout,
                fg_color=style.COLOR_DANGER, hover_color="#c0392b", height=32
            )
            logout_btn.pack(padx=style.PAD_X, pady=(4, 12))

    def _add_field(self, label_text, variable, show=None, browse=False):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=style.PAD_X, pady=2)
        ctk.CTkLabel(frame, text=label_text, width=140, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(frame, textvariable=variable, show=show or "")
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        if browse:
            path = variable
            ctk.CTkButton(
                frame, text="浏览", width=70, command=lambda p=path: self._browse_dir(p)
            ).pack(side="left", padx=(4, 0))
        return entry

    def _add_switch(self, label_text, variable, help_text=""):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=style.PAD_X, pady=2)
        label_group = ctk.CTkFrame(frame, fg_color="transparent", width=140)
        label_group.pack(side="left")
        ctk.CTkLabel(label_group, text=label_text, anchor="w").pack(anchor="w")
        if help_text:
            ctk.CTkLabel(
                label_group,
                text=help_text,
                anchor="w",
                wraplength=310,
                text_color=style.COLOR_MUTED,
                font=style.meta_font(),
            ).pack(anchor="w")
        switch = ctk.CTkSwitch(frame, variable=variable, text="")
        switch.pack(side="left", padx=(8, 0))
        return switch

    def _add_options(self, label_text, variable, values):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=style.PAD_X, pady=2)
        ctk.CTkLabel(frame, text=label_text, width=140, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(frame, variable=variable, values=values).pack(side="left", padx=(8, 0))

    def _browse_dir(self, variable):
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _save(self):
        self._config.update_settings(
            username=self._username_var.get(),
            password=self._password_var.get(),
            output_dir=self._output_dir_var.get(),
            headless=self._headless_var.get(),
            anti_bot_mode=self._anti_bot_var.get(),
            profile_dir=self._profile_dir_var.get(),
            proxy=self._proxy_var.get(),
            geoip=self._geoip_var.get(),
            theme=self._theme_var.get(),
        )
        style.apply_appearance(self._config.theme)
        self._status_label.configure(text="设置已保存到 ~/.linovelib.ini", text_color=style.COLOR_SUCCESS)

    def _sync_geoip_state(self):
        has_proxy = bool(self._proxy_var.get().strip())
        self._geoip_switch.configure(state="normal" if has_proxy else "disabled")
        if not has_proxy:
            self._geoip_var.set(False)

    def _add_browser_profile_card(self):
        try:
            from ...core import browser as _browser  # noqa: F401
            from cloakbrowser import __version__, binary_info

            info = binary_info()
            binary_state = "浏览器内核已安装" if info.get("installed") else "浏览器内核待安装"
            version_text = f"CloakBrowser {__version__} · Chromium {info.get('version', '-')}"
            state_color = style.COLOR_SUCCESS if info.get("installed") else style.COLOR_WARNING
        except Exception:
            binary_state = "暂时无法读取浏览档案状态"
            version_text = "CloakBrowser 状态未知"
            state_color = style.COLOR_WARNING

        card = ctk.CTkFrame(
            self,
            corner_radius=style.CARD_RADIUS,
            fg_color=style.COLOR_CARD,
            border_width=1,
            border_color=style.COLOR_BORDER,
        )
        card.pack(fill="x", padx=style.PAD_X, pady=(0, 8))
        ctk.CTkLabel(
            card,
            text="浏览档案",
            font=style.section_font(),
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            card,
            text=f"● {binary_state}",
            text_color=state_color,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=14)
        ctk.CTkLabel(
            card,
            text=version_text,
            text_color=style.COLOR_MUTED,
            font=style.meta_font(),
        ).pack(anchor="w", padx=14, pady=(2, 12))

    def _logout(self):
        self._config.set_credentials("", "")
        self._username_var.set("")
        self._password_var.set("")
        self._status_label.configure(text="凭据已清除。", text_color=style.COLOR_DANGER)
