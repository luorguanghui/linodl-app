import queue
import customtkinter as ctk

from ..config.manager import ConfigManager
from ..models.novel import NovelInfo

from .panels.search_panel import SearchPanel
from .panels.download_panel import DownloadPanel
from .panels.settings_panel import SettingsPanel
from .panels.verify_panel import VerifyPanel
from .panels.export_panel import ExportPanel
from .panels.warmup_panel import WarmupPanel

PANEL_SEARCH = "search"
PANEL_DOWNLOAD = "download"
PANEL_EXPORT = "export"
PANEL_VERIFY = "verify"
PANEL_SETTINGS = "settings"
PANEL_WARMUP = "warmup"


class MainWindow(ctk.CTk):
    def __init__(self, config: ConfigManager = None, debug: bool = False):
        super().__init__()
        self._config = config or ConfigManager()
        self._debug = debug
        self._queue = queue.Queue()
        self._current_panel_name = None
        self._current_panel = None
        self._active_worker_panel = None

        self._setup_window()
        self._build_sidebar()
        self._build_content_area()
        self._build_status_bar()

        self.show_panel(PANEL_SEARCH)
        self._poll_queue()

    def _setup_window(self):
        self.title("linodl - Novel Downloader")
        self.geometry("1024x768")
        self.minsize(800, 600)

        theme = self._config.theme
        if theme == "dark":
            ctk.set_appearance_mode("dark")
        elif theme == "light":
            ctk.set_appearance_mode("light")
        else:
            ctk.set_appearance_mode("system")

        ctk.set_default_color_theme("blue")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def _build_sidebar(self):
        self._sidebar = ctk.CTkFrame(self, width=180, corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="ns")
        self._sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self._sidebar, text="linodl",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            self._sidebar, text="Novel Downloader",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).pack(pady=(0, 16))

        nav_buttons = [
            (PANEL_SEARCH, "Search & Download"),
            (PANEL_DOWNLOAD, "URL Download"),
            (PANEL_EXPORT, "EPUB Export"),
            (PANEL_VERIFY, "Verify"),
            (PANEL_SETTINGS, "Settings"),
            (PANEL_WARMUP, "CF Warmup"),
        ]

        self._nav_btns = {}
        for name, label in nav_buttons:
            btn = ctk.CTkButton(
                self._sidebar, text=label, anchor="w",
                command=lambda n=name: self.show_panel(n),
                fg_color="transparent", text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"), height=36
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[name] = btn

    def _build_content_area(self):
        self._content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._content_frame.grid(row=0, column=1, sticky="nsew")
        self._content_frame.grid_rowconfigure(0, weight=1)
        self._content_frame.grid_columnconfigure(0, weight=1)

    def _build_status_bar(self):
        self._status_bar = ctk.CTkFrame(self, height=28, corner_radius=0)
        self._status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._status_bar.grid_propagate(False)

        self._status_label = ctk.CTkLabel(
            self._status_bar, text="Ready", anchor="w",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self._status_label.pack(side="left", padx=12, pady=2)

    def show_panel(self, name: str):
        if self._current_panel_name == name and self._current_panel is not None:
            return

        if self._current_panel is not None:
            self._current_panel.pack_forget()

        if name == PANEL_SEARCH:
            panel = SearchPanel(
                self._content_frame, self._config, self._queue,
                on_novel_selected=self._on_novel_selected,
                on_url_download=self._on_url_download,
            )
        elif name == PANEL_DOWNLOAD:
            panel = DownloadPanel(
                self._content_frame, self._config, self._queue,
                show_search=lambda: self.show_panel(PANEL_SEARCH),
            )
        elif name == PANEL_SETTINGS:
            panel = SettingsPanel(self._content_frame, self._config, self._queue)
        elif name == PANEL_VERIFY:
            panel = VerifyPanel(self._content_frame, self._config, self._queue)
        elif name == PANEL_EXPORT:
            panel = ExportPanel(self._content_frame, self._config, self._queue)
        elif name == PANEL_WARMUP:
            panel = WarmupPanel(self._content_frame, self._config, self._queue)
        else:
            return

        panel.pack(fill="both", expand=True)
        self._current_panel = panel
        self._current_panel_name = name

        for btn_name, btn in self._nav_btns.items():
            if btn_name == name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

    def _on_novel_selected(self, novel: NovelInfo):
        self.show_panel(PANEL_DOWNLOAD)
        self._current_panel.load_catalog(None, None)
        if not novel.catalog_url:
            novel.catalog_url = f"https://www.linovelib.com/novel/{novel.novel_id}/catalog"
        self._active_worker_panel = self._current_panel
        self._current_panel.load_catalog(novel.catalog_url)

    def _on_url_download(self, url: str):
        self.show_panel(PANEL_DOWNLOAD)
        self._active_worker_panel = self._current_panel
        self._current_panel.load_catalog(url)

    def run(self):
        self.mainloop()

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self._queue.get_nowait()
                self._dispatch(msg_type, data)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _dispatch(self, msg_type: str, data):
        if msg_type == "progress":
            self._status_label.configure(text=str(data)[:120])
            if self._active_worker_panel and hasattr(self._active_worker_panel, "on_progress"):
                self._active_worker_panel.on_progress(str(data))

        elif msg_type == "result":
            self._status_label.configure(text="Done.", text_color="green")
            if self._active_worker_panel is not None:
                self._dispatch_result(data)
            self._active_worker_panel = None

        elif msg_type == "error":
            self._status_label.configure(text=f"Error: {str(data)[:120]}", text_color="red")
            if self._active_worker_panel and hasattr(self._active_worker_panel, "on_error"):
                self._active_worker_panel.on_error(str(data))
            self._active_worker_panel = None

        elif msg_type == "done":
            if self._active_worker_panel and hasattr(self._active_worker_panel, "on_done"):
                self._active_worker_panel.on_done()

    def _dispatch_result(self, data):
        panel = self._active_worker_panel

        if isinstance(data, list) and all(isinstance(x, NovelInfo) for x in data):
            if hasattr(panel, "on_search_complete"):
                panel.on_search_complete(data)

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

        elif isinstance(data, (str, list)):
            if isinstance(data, str):
                if hasattr(panel, "on_export_result"):
                    self._try_export_or_warmup_result(panel, data)
            elif isinstance(data, list) and all(isinstance(x, str) for x in data):
                if hasattr(panel, "on_export_result"):
                    panel.on_export_result(data)

    def _try_export_or_warmup_result(self, panel, data: str):
        if hasattr(panel, "on_result"):
            panel.on_result(data)
        elif hasattr(panel, "on_export_result"):
            panel.on_export_result([data])
