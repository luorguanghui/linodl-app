import customtkinter as ctk

from ..workers import SearchWorker
from .. import style


class SearchPanel(ctk.CTkFrame):
    def __init__(
        self, parent, config, message_queue, on_novel_selected, on_url_download,
        set_active_panel=None, **kwargs
    ):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._on_novel_selected = on_novel_selected
        self._on_url_download = on_url_download
        self._set_active_panel = set_active_panel or (lambda panel: None)
        self._results = []
        self._worker = None
        self._result_widgets = []
        self._empty_label = None

        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=style.PAD_X, pady=(16, 4))

        ctk.CTkLabel(search_frame, text="搜索", font=style.title_font()).pack(
            anchor="w")

        entry_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        entry_frame.pack(fill="x", pady=(8, 0))

        self._keyword_entry = ctk.CTkEntry(entry_frame, placeholder_text="输入小说关键词...", height=36)
        self._keyword_entry.pack(side="left", fill="x", expand=True)
        self._keyword_entry.bind("<Return>", lambda e: self._start_search())

        self._search_btn = ctk.CTkButton(
            entry_frame, text="搜索", command=self._start_search, width=100,
            fg_color=style.COLOR_PRIMARY, hover_color=style.COLOR_PRIMARY_HOVER
        )
        self._search_btn.pack(side="left", padx=(8, 0))

        # URL download shortcut
        url_frame = ctk.CTkFrame(self, fg_color="transparent")
        url_frame.pack(fill="x", padx=style.PAD_X, pady=4)

        ctk.CTkLabel(url_frame, text="或粘贴目录 URL:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        url_entry_frame = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_entry_frame.pack(fill="x", pady=(2, 0))

        self._url_entry = ctk.CTkEntry(
            url_entry_frame, placeholder_text="https://www.linovelib.com/novel/.../catalog", height=32
        )
        self._url_entry.pack(side="left", fill="x", expand=True)
        self._url_entry.bind("<Return>", lambda e: self._start_url_download())

        ctk.CTkButton(
            url_entry_frame, text="打开", command=self._start_url_download, width=80
        ).pack(side="left", padx=(8, 0))

        # Status
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=style.PAD_X, pady=(8, 4))

        # Results area
        self._results_frame = ctk.CTkScrollableFrame(self)
        self._results_frame.pack(fill="both", expand=True, padx=style.PAD_X, pady=(4, 16))
        self._show_empty_state("输入关键词搜索小说，或粘贴目录 URL 直接进入下载。")

    def _start_search(self):
        keyword = self._keyword_entry.get().strip()
        if not keyword:
            self._status_label.configure(text="请输入关键词。", text_color="red")
            return

        self._set_ui_busy(True)
        self._status_label.configure(text="正在搜索...", text_color="gray")
        self._clear_results()

        self._set_active_panel(self)
        self._worker = SearchWorker(keyword, self._config, self._queue)
        self._worker.start()

    def _start_url_download(self):
        url = self._url_entry.get().strip()
        if not url:
            self._status_label.configure(text="请粘贴目录 URL。", text_color="red")
            return
        if "linovelib.com" not in url:
            self._status_label.configure(text="无效 URL — 必须是 linovelib.com 链接。", text_color="red")
            return
        self._on_url_download(url)

    def on_search_complete(self, novels):
        self._set_ui_busy(False)
        self._results = novels
        if not novels:
            self._status_label.configure(text="未找到结果。", text_color="#f39c12")
            self._show_empty_state("没有匹配结果。可以换一个关键词，或直接粘贴目录 URL。")
            return

        self._status_label.configure(text=f"找到 {len(novels)} 条结果。", text_color="green")
        self._populate_results(novels)

    def on_search_error(self, msg):
        self._set_ui_busy(False)
        self._status_label.configure(text=f"搜索失败: {msg}", text_color="red")

    def _populate_results(self, novels):
        self._clear_results()
        for i, novel in enumerate(novels[:30]):
            card = ctk.CTkFrame(self._results_frame, corner_radius=style.CARD_RADIUS, fg_color=style.COLOR_CARD)
            card.pack(fill="x", padx=4, pady=4)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8, pady=6)

            title = novel.title or "(未知)"
            ctk.CTkLabel(info_frame, text=title, font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x")
            detail = f"作者: {novel.author or '-'}   |   ID: {novel.novel_id}"
            ctk.CTkLabel(info_frame, text=detail, text_color="gray", font=ctk.CTkFont(size=11), anchor="w").pack(fill="x")

            n = novel
            ctk.CTkButton(
                card, text="选择", width=80,
                command=lambda novel=n: self._on_novel_selected(novel)
            ).pack(side="right", padx=8, pady=6)

            self._result_widgets.append(card)

    def _clear_results(self):
        for w in self._result_widgets:
            w.destroy()
        self._result_widgets.clear()
        self._results = []
        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None

    def _show_empty_state(self, text):
        self._clear_results()
        self._empty_label = ctk.CTkLabel(
            self._results_frame, text=text, text_color=style.COLOR_MUTED,
            anchor="center", font=style.meta_font()
        )
        self._empty_label.pack(fill="both", expand=True, padx=16, pady=40)

    def _set_ui_busy(self, busy):
        if busy:
            self._search_btn.configure(text="搜索中...", state="disabled")
        else:
            self._search_btn.configure(text="搜索", state="normal")

    def on_error(self, msg):
        self._set_ui_busy(False)
        self._status_label.configure(text=f"搜索失败: {msg}", text_color=style.COLOR_DANGER)
