import customtkinter as ctk

from ..workers import SearchWorker


class SearchPanel(ctk.CTkFrame):
    def __init__(self, parent, config, message_queue, on_novel_selected, on_url_download, **kwargs):
        super().__init__(parent, **kwargs)
        self._config = config
        self._queue = message_queue
        self._on_novel_selected = on_novel_selected
        self._on_url_download = on_url_download
        self._results = []
        self._worker = None
        self._result_widgets = []

        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=16, pady=(16, 4))

        ctk.CTkLabel(search_frame, text="Search", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w")

        entry_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        entry_frame.pack(fill="x", pady=(8, 0))

        self._keyword_entry = ctk.CTkEntry(entry_frame, placeholder_text="Enter novel keyword...", height=36)
        self._keyword_entry.pack(side="left", fill="x", expand=True)
        self._keyword_entry.bind("<Return>", lambda e: self._start_search())

        self._search_btn = ctk.CTkButton(
            entry_frame, text="Search", command=self._start_search, width=100
        )
        self._search_btn.pack(side="left", padx=(8, 0))

        # URL download shortcut
        url_frame = ctk.CTkFrame(self, fg_color="transparent")
        url_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(url_frame, text="Or paste catalog URL:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        url_entry_frame = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_entry_frame.pack(fill="x", pady=(2, 0))

        self._url_entry = ctk.CTkEntry(
            url_entry_frame, placeholder_text="https://www.linovelib.com/novel/.../catalog", height=32
        )
        self._url_entry.pack(side="left", fill="x", expand=True)
        self._url_entry.bind("<Return>", lambda e: self._start_url_download())

        ctk.CTkButton(
            url_entry_frame, text="Open", command=self._start_url_download, width=80
        ).pack(side="left", padx=(8, 0))

        # Status
        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(anchor="w", padx=16, pady=(8, 4))

        # Results area
        self._results_frame = ctk.CTkScrollableFrame(self)
        self._results_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

    def _start_search(self):
        keyword = self._keyword_entry.get().strip()
        if not keyword:
            self._status_label.configure(text="Please enter a keyword.", text_color="red")
            return

        self._set_ui_busy(True)
        self._status_label.configure(text="Searching...", text_color="gray")
        self._clear_results()

        self._worker = SearchWorker(keyword, self._config, self._queue)
        self._worker.start()

    def _start_url_download(self):
        url = self._url_entry.get().strip()
        if not url:
            self._status_label.configure(text="Please paste a catalog URL.", text_color="red")
            return
        if "linovelib.com" not in url:
            self._status_label.configure(text="Invalid URL — must be a linovelib.com link.", text_color="red")
            return
        self._on_url_download(url)

    def on_search_complete(self, novels):
        self._set_ui_busy(False)
        self._results = novels
        if not novels:
            self._status_label.configure(text="No results found.", text_color="#f39c12")
            return

        self._status_label.configure(text=f"Found {len(novels)} result(s).", text_color="green")
        self._populate_results(novels)

    def on_search_error(self, msg):
        self._set_ui_busy(False)
        self._status_label.configure(text=f"Search failed: {msg}", text_color="red")

    def _populate_results(self, novels):
        self._clear_results()
        for i, novel in enumerate(novels[:30]):
            card = ctk.CTkFrame(self._results_frame)
            card.pack(fill="x", padx=4, pady=2)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8, pady=6)

            title = novel.title or "(Unknown)"
            ctk.CTkLabel(info_frame, text=title, font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x")
            detail = f"Author: {novel.author or '-'}   |   ID: {novel.novel_id}"
            ctk.CTkLabel(info_frame, text=detail, text_color="gray", font=ctk.CTkFont(size=11), anchor="w").pack(fill="x")

            n = novel
            ctk.CTkButton(
                card, text="Select", width=80,
                command=lambda novel=n: self._on_novel_selected(novel)
            ).pack(side="right", padx=8, pady=6)

            self._result_widgets.append(card)

    def _clear_results(self):
        for w in self._result_widgets:
            w.destroy()
        self._result_widgets.clear()
        self._results = []

    def _set_ui_busy(self, busy):
        if busy:
            self._search_btn.configure(text="Searching...", state="disabled")
        else:
            self._search_btn.configure(text="Search", state="normal")
