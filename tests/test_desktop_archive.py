from __future__ import annotations

import queue
import zipfile
from pathlib import Path

import pytest

from linodl.core.epub import EpubExporter
from linodl.desktop.archive import (
    ArchivePathGuard,
    UnsafeArchivePath,
    load_archive,
    scan_archives,
)
from linodl.gui.workers import VerifyWorker
from linodl.models.novel import Chapter, NovelInfo, Volume


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


def test_load_archive_preserves_space_source_without_creating_alias(tmp_path):
    output_dir = tmp_path / "output"
    book = output_dir / "Book A"
    volume = book / "Volume 1"
    volume.mkdir(parents=True)
    source = volume / "001 Prologue.txt"
    source.write_text("body", encoding="utf-8")

    scan_archives(output_dir)
    assert not (volume / "001_Prologue.txt").exists()
    novel, volumes, base_dir = load_archive(book, output_dir)

    assert novel.title == "Book A"
    assert base_dir == book.resolve()
    assert [
        (chapter.index, chapter.title, chapter.source_filename)
        for chapter in volumes[0].chapters
    ] == [
        (1, "Prologue", "001 Prologue.txt")
    ]
    assert not (volume / "001_Prologue.txt").exists()


def test_verify_worker_consumes_space_separated_archive_source(tmp_path):
    output_dir = tmp_path / "output"
    book = output_dir / "Book A"
    volume_dir = book / "Volume 1"
    volume_dir.mkdir(parents=True)
    (volume_dir / "001 Prologue.txt").write_text(
        "Prologue\n" + "=" * 50 + "\n\n" + "complete body " * 20,
        encoding="utf-8",
    )
    _, volumes, base_dir = load_archive(book, output_dir)
    messages = queue.Queue()

    worker = VerifyWorker(volumes, {"Volume 1"}, str(base_dir), messages)
    worker.run()

    events = []
    while not messages.empty():
        events.append(messages.get_nowait())
    result = next(data for event, data, _ in events if event == "result")
    assert result.is_clean
    assert result.complete == 1
    assert not (volume_dir / "001_Prologue.txt").exists()


def test_epub_export_reloads_modified_space_separated_source(tmp_path):
    output_dir = tmp_path / "output"
    book = output_dir / "Book A"
    volume_dir = book / "Volume 1"
    volume_dir.mkdir(parents=True)
    source = volume_dir / "001 Prologue.txt"
    source.write_text(
        "Prologue\n" + "=" * 50 + "\n\nfirst archive body",
        encoding="utf-8",
    )
    novel, volumes, base_dir = load_archive(book, output_dir)
    exporter = EpubExporter()

    [epub_path] = exporter.export(novel, volumes, str(base_dir))
    with zipfile.ZipFile(epub_path) as archive:
        first_export = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )
    source.write_text(
        "Prologue\n" + "=" * 50 + "\n\nsecond archive body",
        encoding="utf-8",
    )
    reloaded_novel, reloaded_volumes, reloaded_base_dir = load_archive(
        book,
        output_dir,
    )

    [reloaded_epub_path] = exporter.export(
        reloaded_novel,
        reloaded_volumes,
        str(reloaded_base_dir),
    )
    with zipfile.ZipFile(reloaded_epub_path) as archive:
        second_export = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )
    assert "first archive body" in first_export
    assert "second archive body" in second_export
    assert "first archive body" not in second_export
    assert not (volume_dir / "001_Prologue.txt").exists()


def test_verify_and_epub_fall_back_from_unsafe_source_filename(tmp_path):
    volume_dir = tmp_path / "Volume 1"
    volume_dir.mkdir()
    safe_content = "Safe\n" + "=" * 50 + "\n\n" + "safe body " * 20
    (volume_dir / "001_Safe.txt").write_text(safe_content, encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text(
        "Outside\n" + "=" * 50 + "\n\noutside secret",
        encoding="utf-8",
    )
    volume = Volume(
        name="Volume 1",
        chapters=[
            Chapter(
                index=1,
                url="",
                title="Safe",
                is_illustration=False,
                volume_name="Volume 1",
                source_filename="../outside.txt",
            )
        ],
    )
    messages = queue.Queue()

    worker = VerifyWorker([volume], {"Volume 1"}, str(tmp_path), messages)
    worker.run()
    events = []
    while not messages.empty():
        events.append(messages.get_nowait())
    result = next(data for event, data, _ in events if event == "result")
    [epub_path] = EpubExporter().export(
        NovelInfo(title="Book"),
        [volume],
        str(tmp_path),
    )
    with zipfile.ZipFile(epub_path) as archive:
        exported = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )

    assert result.is_clean
    assert "safe body" in exported
    assert "outside secret" not in exported
