"""Data models for novels, volumes, chapters, and download results."""

from dataclasses import dataclass, field


@dataclass
class NovelInfo:
    novel_id: str = ""
    title: str = ""
    author: str = ""
    cover_url: str = ""
    description: str = ""
    catalog_url: str = ""
    chapter_count: int = 0
    word_count: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Chapter:
    index: int              # 1-based text-chapter index within volume; 0 for illustrations
    url: str                # relative URL e.g. "/novel/12345/67890.html"
    title: str
    is_illustration: bool
    volume_name: str = ""


@dataclass
class Volume:
    name: str               # e.g. "第一卷"
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def text_count(self) -> int:
        return sum(1 for c in self.chapters if not c.is_illustration)

    @property
    def illus_count(self) -> int:
        return sum(1 for c in self.chapters if c.is_illustration)


@dataclass
class DownloadResult:
    novel_title: str = ""
    total_text: int = 0
    total_illus: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    output_dir: str = ""


@dataclass
class ChapterIssue:
    volume_name: str
    chapter_index: int
    chapter_title: str
    chapter_url: str = ""
    issue: str = ""          # "missing", "empty", "truncated", "image_missing", "image_corrupt"
    detail: str = ""


@dataclass
class VerificationResult:
    total_expected: int = 0
    total_actual: int = 0
    complete: int = 0
    missing: int = 0
    empty: int = 0
    truncated: int = 0
    image_issues: int = 0
    issues: list[ChapterIssue] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0

    @property
    def issue_count(self) -> int:
        return len(self.issues)
