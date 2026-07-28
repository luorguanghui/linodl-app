"""Four-step reading workflow indicator."""

import customtkinter as ctk

from .. import style


_STEPS = (
    ("search", "查找作品"),
    ("volumes", "选择分卷"),
    ("download", "下载内容"),
    ("verify_export", "校验与导出"),
)


class WorkflowSteps(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._active = "search"
        self._badges = {}
        self._labels = {}

        for column, (name, label) in enumerate(_STEPS):
            self.grid_columnconfigure(column, weight=1)
            cell = ctk.CTkFrame(self, fg_color="transparent")
            cell.grid(row=0, column=column, sticky="ew")
            badge = ctk.CTkLabel(
                cell,
                text=str(column + 1),
                width=26,
                height=26,
                corner_radius=13,
                fg_color=style.COLOR_CARD_ELEVATED,
                text_color=style.COLOR_MUTED,
                font=ctk.CTkFont(size=11, weight="bold"),
            )
            badge.pack()
            text = ctk.CTkLabel(
                cell,
                text=label,
                font=style.meta_font(),
                text_color=style.COLOR_MUTED,
            )
            text.pack(pady=(4, 0))
            self._badges[name] = badge
            self._labels[name] = text

        self.set_active("search")

    def set_active(self, step: str):
        if step not in self._badges:
            return
        self._active = step
        active_index = [name for name, _ in _STEPS].index(step)
        for index, (name, _label) in enumerate(_STEPS):
            completed = index < active_index
            active = name == step
            if active:
                color = style.COLOR_PRIMARY
                text_color = "#ffffff"
                label_color = style.COLOR_TEXT
            elif completed:
                color = style.COLOR_SUCCESS
                text_color = "#ffffff"
                label_color = style.COLOR_TEXT
            else:
                color = style.COLOR_CARD_ELEVATED
                text_color = style.COLOR_MUTED
                label_color = style.COLOR_MUTED
            self._badges[name].configure(
                fg_color=color,
                text_color=text_color,
                text="✓" if completed else str(index + 1),
            )
            self._labels[name].configure(text_color=label_color)
