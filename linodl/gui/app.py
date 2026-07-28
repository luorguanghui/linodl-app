import queue
import customtkinter as ctk

from ..config.manager import ConfigManager
from ..models.novel import NovelInfo

from .panels.workbench_panel import WorkbenchPanel
from .panels.settings_panel import SettingsPanel
from .panels.verify_panel import VerifyPanel
from .panels.export_panel import ExportPanel
from .panels.warmup_panel import WarmupPanel
from .tasks import task_store
from . import style

PANEL_WORKBENCH = "workbench"
PANEL_SEARCH = PANEL_WORKBENCH
PANEL_DOWNLOAD = PANEL_WORKBENCH
PANEL_EXPORT = "archive"
PANEL_VERIFY = "verify"
PANEL_SETTINGS = "settings"
PANEL_WARMUP = "browser_profile"


class MainWindow(ctk.CTk):
    def __init__(self, config: ConfigManager = None, debug: bool = False):
        super().__init__()
        self._config = config or ConfigManager()
        self._debug = debug
        self._queue = queue.Queue()
        self._current_panel_name = None
        self._current_panel = None
        self._panels = {}  # cache: name -> panel instance

        self._setup_window()
        self._build_sidebar()
        self._build_content_area()
        self._build_status_bar()

        self.show_panel(PANEL_SEARCH)
        self._poll_queue()

    def _setup_window(self):
        self.title("linodl · 阅读工作台")
        self.geometry("1024x768")
        self.minsize(800, 600)

        theme = self._config.theme
        style.apply_appearance(theme)

        ctk.set_default_color_theme("blue")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(
            self,
            width=196,
            corner_radius=0,
            fg_color=style.COLOR_SIDEBAR,
        )
        self._sidebar.grid(row=0, column=0, sticky="ns")
        self._sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=14, pady=(20, 22))
        ctk.CTkFrame(
            brand,
            width=5,
            height=42,
            corner_radius=3,
            fg_color=style.COLOR_PRIMARY,
        ).pack(side="left", padx=(0, 10))
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left")
        ctk.CTkLabel(
            brand_text,
            text="linodl",
            text_color="#F4F7FB",
            font=style.title_font(),
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_text,
            text="LIGHT NOVEL DESK",
            text_color="#7F91AA",
            font=ctk.CTkFont(size=9, weight="bold"),
        ).pack(anchor="w")

        nav_buttons = [
            (PANEL_WORKBENCH, "▰  阅读工作台"),
            (PANEL_VERIFY, "✓  内容校验"),
            (PANEL_EXPORT, "▤  阅读档案"),
            (PANEL_WARMUP, "◉  浏览档案"),
            (PANEL_SETTINGS, "设置"),
        ]

        self._nav_btns = {}
        self._nav_base_labels = {}
        for name, label in nav_buttons:
            self._nav_base_labels[name] = label
            btn = ctk.CTkButton(
                self._sidebar, text=label, anchor="w",
                command=lambda n=name: self.show_panel(n),
                fg_color="transparent",
                text_color="#C8D3E1",
                hover_color=style.COLOR_SIDEBAR_ACTIVE,
                height=42,
                corner_radius=10,
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_btns[name] = btn

    def _build_content_area(self):
        self._content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._content_frame.grid(row=0, column=1, sticky="nsew")
        self._content_frame.grid_rowconfigure(0, weight=1)
        self._content_frame.grid_columnconfigure(0, weight=1)

    def _build_status_bar(self):
        self._status_bar = ctk.CTkFrame(self, height=30, corner_radius=0)
        self._status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._status_bar.grid_propagate(False)

        self._status_label = ctk.CTkLabel(
            self._status_bar, text="就绪", anchor="w",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self._status_label.pack(side="left", padx=12, pady=2)

        self._active_tasks_label = ctk.CTkLabel(
            self._status_bar, text="", anchor="e",
            font=ctk.CTkFont(size=11), text_color=style.COLOR_WARNING
        )
        self._active_tasks_label.pack(side="right", padx=12, pady=2)

    def _create_panel(self, name: str):
        """Create a panel instance for the given name."""
        if name == PANEL_WORKBENCH:
            return WorkbenchPanel(
                self._content_frame,
                self._config,
                self._queue,
            )
        elif name == PANEL_SETTINGS:
            return SettingsPanel(self._content_frame, self._config, self._queue)
        elif name == PANEL_VERIFY:
            return VerifyPanel(self._content_frame, self._config, self._queue)
        elif name == PANEL_EXPORT:
            return ExportPanel(self._content_frame, self._config, self._queue)
        elif name == PANEL_WARMUP:
            return WarmupPanel(self._content_frame, self._config, self._queue)
        return None

    def show_panel(self, name: str):
        if self._current_panel_name == name and self._current_panel is not None:
            return

        if self._current_panel is not None:
            self._current_panel.pack_forget()

        # Reuse cached panel or create a new one.
        panel = self._panels.get(name)
        if panel is None:
            panel = self._create_panel(name)
            if panel is None:
                return
            self._panels[name] = panel

        panel.pack(fill="both", expand=True)
        self._current_panel = panel
        self._current_panel_name = name

        for btn_name, btn in self._nav_btns.items():
            if btn_name == name:
                btn.configure(fg_color=style.COLOR_SIDEBAR_ACTIVE)
            else:
                btn.configure(fg_color="transparent")

    def _on_novel_selected(self, novel: NovelInfo):
        self.show_panel(PANEL_WORKBENCH)
        self._current_panel.open_novel(novel)

    def _on_url_download(self, url: str):
        self.show_panel(PANEL_WORKBENCH)
        self._current_panel.open_url(url)

    def run(self):
        self.mainloop()

    def _poll_queue(self):
        try:
            while True:
                msg_type, data, owner = self._queue.get_nowait()
                self._dispatch(msg_type, data, owner)
        except queue.Empty:
            pass
        self._update_sidebar_indicators()
        workbench = self._panels.get(PANEL_WORKBENCH)
        if workbench is not None:
            workbench.refresh_tasks(task_store.snapshot())
        self.after(100, self._poll_queue)

    def _dispatch(self, msg_type: str, data, owner):
        if msg_type == "progress":
            self._status_label.configure(text=str(data)[:120], text_color="gray")
            if owner is not None and hasattr(owner, "on_progress"):
                owner.on_progress(str(data))

        elif msg_type == "result":
            self._status_label.configure(text="完成。", text_color=style.COLOR_SUCCESS)
            if owner is not None:
                self._dispatch_result(data, owner)

        elif msg_type == "error":
            self._status_label.configure(text=f"错误: {str(data)[:120]}", text_color=style.COLOR_DANGER)
            if owner is not None and hasattr(owner, "on_error"):
                owner.on_error(str(data))

        elif msg_type == "done":
            if owner is not None and hasattr(owner, "on_done"):
                owner.on_done()

    def _dispatch_result(self, data, panel):
        if isinstance(data, list):
            if hasattr(panel, "on_search_complete") and all(isinstance(x, NovelInfo) for x in data):
                panel.on_search_complete(data)
            elif hasattr(panel, "on_export_result") and all(isinstance(x, str) for x in data):
                panel.on_export_result(data)

        elif isinstance(data, tuple) and len(data) == 2:
            volumes, novel_info = data
            if hasattr(panel, "on_catalog_result"):
                panel.on_catalog_result(data)

        elif isinstance(data, tuple) and len(data) == 3:
            if hasattr(panel, "on_download_result"):
                panel.on_download_result(data)

        elif hasattr(data, "issues"):
            if hasattr(panel, "on_verify_result"):
                panel.on_verify_result(data)

        elif isinstance(data, str):
            self._try_export_or_warmup_result(panel, data)

    def _try_export_or_warmup_result(self, panel, data: str):
        if hasattr(panel, "on_result"):
            panel.on_result(data)
        elif hasattr(panel, "on_export_result"):
            panel.on_export_result([data])

    def _update_sidebar_indicators(self):
        busy_panels = []
        for name, panel in self._panels.items():
            if name not in self._nav_btns:
                continue
            busy = hasattr(panel, 'is_busy') and panel.is_busy()
            base = self._nav_base_labels.get(name, "")
            if busy:
                self._nav_btns[name].configure(text=f"⏳ {base}")
                busy_panels.append(base)
            else:
                self._nav_btns[name].configure(text=base)
        if busy_panels:
            self._active_tasks_label.configure(
                text="运行中: " + ", ".join(busy_panels)
            )
        else:
            self._active_tasks_label.configure(text="")
