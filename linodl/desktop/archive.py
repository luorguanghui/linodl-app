"""Read downloaded archives without widening the desktop filesystem boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..models.novel import Chapter, NovelInfo, Volume


PathResolver = Callable[[Path], Path]
_CANONICAL_CHAPTER = re.compile(r"^(\d+)_(.+)$")
_SPACE_CHAPTER = re.compile(r"^(\d+) (.+)$")
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*]')


class UnsafeArchivePath(ValueError):
    """Raised when a downloaded archive resolves outside its output root."""


class ArchivePathGuard:
    """Resolve every archive path against one immutable output boundary."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        resolver: PathResolver | None = None,
    ):
        self._resolver = resolver or (lambda path: path.resolve())
        self.root = Path(self._resolver(Path(output_dir)))

    def resolve(self, candidate: str | Path) -> Path:
        resolved = Path(self._resolver(Path(candidate)))
        if resolved != self.root and self.root not in resolved.parents:
            raise UnsafeArchivePath("archive path escaped the output directory")
        return resolved


@dataclass(frozen=True)
class ChapterSource:
    path: Path
    filename: str
    index: int
    title: str
    canonical_name: str


def scan_archives(
    output_dir: str | Path,
    *,
    path_guard: ArchivePathGuard | None = None,
) -> list[dict]:
    """List direct child directories after validating their complete trees."""
    guard = path_guard or ArchivePathGuard(output_dir)
    root = guard.resolve(output_dir)
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    archives = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        try:
            archive_path = guard.resolve(child)
        except UnsafeArchivePath:
            continue
        if not archive_path.is_dir():
            continue
        direct_chapters = _chapter_sources(archive_path, guard)
        if direct_chapters:
            _validate_illustrations(archive_path, guard)
            volume_count = 1
            chapter_count = len(direct_chapters)
        else:
            volumes = _volume_paths(archive_path, guard)
            for _, volume_path in volumes:
                _validate_illustrations(volume_path, guard)
            volume_count = len(volumes)
            chapter_count = sum(
                len(_chapter_sources(volume_path, guard))
                for _, volume_path in volumes
            )
        archives.append(
            {
                "id": child.name,
                "title": child.name,
                "path": str(archive_path),
                "volume_count": volume_count,
                "chapter_count": chapter_count,
            }
        )
    return archives


def load_archive(
    archive_path: str | Path,
    output_dir: str | Path,
    *,
    path_guard: ArchivePathGuard | None = None,
) -> tuple[NovelInfo, list[Volume], Path]:
    """Rebuild safe existing-worker inputs for one scanned archive."""
    guard = path_guard or ArchivePathGuard(output_dir)
    path = guard.resolve(archive_path)
    if not path.is_dir():
        raise NotADirectoryError(str(path))
    direct_chapters = _chapter_sources(path, guard)
    if direct_chapters:
        _validate_illustrations(path, guard)
        volumes = [_build_volume(path, path.name, guard)]
        base_dir = guard.resolve(path.parent)
    else:
        volume_paths = _volume_paths(path, guard)
        volumes = [
            _build_volume(volume_path, child.name, guard)
            for child, volume_path in volume_paths
        ]
        base_dir = path
    return NovelInfo(title=path.name), volumes, base_dir


def _build_volume(
    path: Path,
    name: str,
    guard: ArchivePathGuard,
) -> Volume:
    volume = Volume(name=name)
    for source in _chapter_sources(path, guard):
        volume.chapters.append(
            Chapter(
                index=source.index,
                url="",
                title=source.title,
                is_illustration=False,
                volume_name=name,
                source_filename=source.filename,
            )
        )
    if _validate_illustrations(path, guard):
        volume.chapters.append(
            Chapter(
                index=0,
                url="",
                title="插图",
                is_illustration=True,
                volume_name=name,
            )
        )
    return volume


def _chapter_sources(
    path: Path,
    guard: ArchivePathGuard,
) -> list[ChapterSource]:
    text_files = [
        (child, resolved)
        for child, resolved in _safe_children(path, guard)
        if resolved.is_file() and child.suffix.lower() == ".txt"
    ]
    candidates: list[tuple[bool, ChapterSource]] = []
    for position, (child, resolved) in enumerate(text_files, start=1):
        canonical_match = _CANONICAL_CHAPTER.match(child.stem)
        space_match = _SPACE_CHAPTER.match(child.stem)
        match = canonical_match or space_match
        index = int(match.group(1)) if match else position
        title = match.group(2) if match else child.stem
        canonical_name = (
            f"{index:03d}_{_UNSAFE_FILENAME.sub('_', title)}.txt"
        )
        candidates.append(
            (
                child.name == canonical_name,
                ChapterSource(
                    path=resolved,
                    filename=child.name,
                    index=index,
                    title=title,
                    canonical_name=canonical_name,
                ),
            )
        )

    selected: dict[str, tuple[bool, ChapterSource]] = {}
    for is_canonical, source in candidates:
        key = source.canonical_name.casefold()
        current = selected.get(key)
        # Legacy non-canonical sources outrank aliases; sorted input makes the
        # first filename the deterministic winner among peer legacy sources.
        if current is None or (not is_canonical and current[0]):
            selected[key] = (is_canonical, source)
    return [
        source
        for _, source in sorted(
            selected.values(),
            key=lambda item: (item[1].index, item[1].canonical_name),
        )
    ]


def _volume_paths(
    archive_path: Path,
    guard: ArchivePathGuard,
) -> list[tuple[Path, Path]]:
    return [
        (child, resolved)
        for child, resolved in _safe_children(archive_path, guard)
        if resolved.is_dir() and child.name != "插图"
    ]


def _safe_children(
    directory: Path,
    guard: ArchivePathGuard,
) -> list[tuple[Path, Path]]:
    guard.resolve(directory)
    return [
        (child, guard.resolve(child))
        for child in sorted(directory.iterdir(), key=lambda path: path.name)
    ]


def _validate_illustrations(
    volume_path: Path,
    guard: ArchivePathGuard,
) -> bool:
    illustration_dir = volume_path / "插图"
    if not illustration_dir.exists():
        return False
    resolved = guard.resolve(illustration_dir)
    if not resolved.is_dir():
        return False
    _validate_tree(resolved, guard, set())
    return any(resolved.iterdir())


def _validate_tree(
    directory: Path,
    guard: ArchivePathGuard,
    visited: set[Path],
) -> None:
    resolved_directory = guard.resolve(directory)
    if resolved_directory in visited:
        return
    visited.add(resolved_directory)
    for _, resolved in _safe_children(resolved_directory, guard):
        if resolved.is_dir():
            _validate_tree(resolved, guard, visited)
