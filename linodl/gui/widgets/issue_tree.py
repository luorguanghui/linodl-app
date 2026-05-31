import customtkinter as ctk


class IssueTree(ctk.CTkScrollableFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._issue_labels = []

    def set_issues(self, issues):
        self.clear()
        if not issues:
            label = ctk.CTkLabel(self, text="未发现问题。", text_color="green", anchor="w")
            label.pack(fill="x", padx=8, pady=2)
            self._issue_labels.append(label)
            return

        issue_labels_map = {
            "missing": "缺失",
            "empty": "空内容",
            "truncated": "可能截断",
            "image_missing": "图片缺失",
            "image_corrupted": "图片损坏",
        }

        for issue in issues:
            color = {
                "missing": "#e74c3c",
                "empty": "#f39c12",
                "truncated": "#3498db",
                "image_missing": "#e67e22",
                "image_corrupted": "#c0392b",
            }.get(issue.issue, "#95a5a6")

            issue_cn = issue_labels_map.get(issue.issue, issue.issue)
            text = f"[{issue.volume_name}] 第{issue.chapter_index:03d}章 {issue.chapter_title}  [{issue_cn}]"
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
