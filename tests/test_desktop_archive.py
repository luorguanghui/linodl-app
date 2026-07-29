from __future__ import annotations

from pathlib import Path

import pytest

from linodl.desktop.archive import (
    ArchivePathGuard,
    UnsafeArchivePath,
    load_archive,
    scan_archives,
)


def test_scan_archives_ignores_files_and_reports_chapter_count(tmp_path):
    book = tmp_path / "作品 A"
    volume = book / "第一卷"
    volume.mkdir(parents=True)
    (volume / "001 序章.txt").write_text("正文", encoding="utf-8")
    (tmp_path / "note.txt").write_text("ignore", encoding="utf-8")

    archives = scan_archives(tmp_path)

    assert archives == [
        {
            "id": "作品 A",
            "title": "作品 A",
            "path": str(book),
            "volume_count": 1,
            "chapter_count": 1,
        }
    ]


def test_scan_archives_counts_only_direct_volume_chapters(tmp_path):
    book = tmp_path / "作品 B"
    volume = book / "第一卷"
    nested = volume / "临时目录"
    nested.mkdir(parents=True)
    (volume / "001_开场.txt").write_text("正文", encoding="utf-8")
    (volume / "cover.jpg").write_bytes(b"image")
    (nested / "002_不应计入.txt").write_text("临时", encoding="utf-8")

    [archive] = scan_archives(tmp_path)

    assert archive["volume_count"] == 1
    assert archive["chapter_count"] == 1


def test_scan_archives_skips_directory_symlinks_outside_output(tmp_path):
    output_dir = tmp_path / "output"
    outside_volume = tmp_path / "outside" / "第一卷"
    output_dir.mkdir()
    outside_volume.mkdir(parents=True)
    (outside_volume / "001_外部章节.txt").write_text("正文", encoding="utf-8")
    try:
        (output_dir / "外部作品").symlink_to(
            outside_volume.parent,
            target_is_directory=True,
        )
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    assert scan_archives(output_dir) == []


@pytest.mark.parametrize(
    "unsafe_part",
    ["volume", "chapter", "illustration"],
)
def test_archive_path_guard_rejects_nested_reparse_targets_without_os_symlinks(
    tmp_path,
    unsafe_part,
):
    output_dir = tmp_path / "output"
    book = output_dir / "作品 A"
    volume = book / "第一卷"
    illustration = volume / "插图" / "cover.jpg"
    outside = tmp_path / "outside"
    illustration.parent.mkdir(parents=True)
    outside.mkdir()
    chapter = volume / "001_序章.txt"
    chapter.write_text("正文", encoding="utf-8")
    illustration.write_bytes(b"image")
    targets = {
        "volume": volume,
        "chapter": chapter,
        "illustration": illustration,
    }

    def fake_resolve(path):
        candidate = Path(path)
        if candidate == targets[unsafe_part]:
            return outside / candidate.name
        return candidate.resolve()

    guard = ArchivePathGuard(output_dir, resolver=fake_resolve)

    with pytest.raises(UnsafeArchivePath):
        scan_archives(output_dir, path_guard=guard)


def test_load_archive_materializes_canonical_alias_for_space_separator(tmp_path):
    output_dir = tmp_path / "output"
    book = output_dir / "作品 A"
    volume = book / "第一卷"
    volume.mkdir(parents=True)
    source = volume / "001 序章.txt"
    source.write_text("正文", encoding="utf-8")

    novel, volumes, base_dir = load_archive(book, output_dir)

    assert novel.title == "作品 A"
    assert base_dir == book.resolve()
    assert [(chapter.index, chapter.title) for chapter in volumes[0].chapters] == [
        (1, "序章")
    ]
    assert (volume / "001_序章.txt").read_text(encoding="utf-8") == "正文"
