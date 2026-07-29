"""Read downloaded archives without widening the desktop filesystem boundary."""

from __future__ import annotations

import re
from pathlib import Path

from ..gui.directory_scan import scan_download_directories
from ..models.novel import Chapter, NovelInfo, Volume


def scan_archives(output_dir: str | Path) -> list[dict]:
    """List direct child directories and summarize their downloaded content."""
    root = Path(output_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    archives = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        archive_path = child.resolve()
        if (
            not archive_path.is_dir()
            or root not in archive_path.parents
        ):
            continue
        direct_chapters = _chapter_files(archive_path)
        if direct_chapters:
            volume_count = 1
            chapter_count = len(direct_chapters)
        else:
            volumes = scan_download_directories(str(archive_path))
            volume_count = len(volumes)
            chapter_count = sum(volume.text_count for volume in volumes)
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
) -> tuple[NovelInfo, list[Volume], Path]:
    """Rebuild the existing worker inputs for one scanned archive."""
    path = Path(archive_path).resolve()
    direct_chapters = _chapter_files(path)
    if direct_chapters:
        volumes = [_build_volume(path, path.name)]
        base_dir = path.parent
    else:
        directory_info = scan_download_directories(str(path))
        volumes = [
            _build_volume(path / info.name, info.name)
            for info in directory_info
        ]
        base_dir = path
    return NovelInfo(title=path.name), volumes, base_dir


def _build_volume(path: Path, name: str) -> Volume:
    volume = Volume(name=name)
    for position, chapter_path in enumerate(_chapter_files(path), start=1):
        match = re.match(r"^(\d+)[_ ](.+)$", chapter_path.stem)
        chapter_index = int(match.group(1)) if match else position
        chapter_title = match.group(2) if match else chapter_path.stem
        volume.chapters.append(
            Chapter(
                index=chapter_index,
                url="",
                title=chapter_title,
                is_illustration=False,
                volume_name=name,
            )
        )
    illustration_dir = path / "插图"
    if illustration_dir.is_dir() and any(illustration_dir.iterdir()):
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


def _chapter_files(path: Path) -> list[Path]:
    return sorted(
        (
            child
            for child in path.iterdir()
            if child.is_file() and child.suffix.lower() == ".txt"
        ),
        key=lambda child: child.name,
    )
