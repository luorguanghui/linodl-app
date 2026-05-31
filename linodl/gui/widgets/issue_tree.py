import customtkinter as ctk


class IssueTree(ctk.CTkScrollableFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._issue_labels = []

    def set_issues(self, issues):
        self.clear()
        if not issues:
            label = ctk.CTkLabel(self, text="No issues found.", text_color="green", anchor="w")
            label.pack(fill="x", padx=8, pady=2)
            self._issue_labels.append(label)
            return

        for issue in issues:
            color = {
                "missing": "#e74c3c",
                "empty": "#f39c12",
                "truncated": "#3498db",
                "image_missing": "#e67e22",
                "image_corrupted": "#c0392b",
            }.get(issue.issue, "#95a5a6")

            text = f"[{issue.volume_name}] Ch.{issue.chapter_index:03d} {issue.chapter_title}"
            if issue.detail:
                text += f"  —  {issue.detail}"

            label = ctk.CTkLabel(
                self, text=text, text_color=color, anchor="w",
                font=ctk.CTkFont(size=11)
            )
            label.pack(fill="x", padx=8, pady=1)
            self._issue_labels.append(label)

    def clear(self):
        for label in self._issue_labels:
            label.destroy()
        self._issue_labels.clear()
