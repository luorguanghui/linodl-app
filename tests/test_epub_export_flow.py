from pathlib import Path

from linodl.cli.app import App


def test_parse_export_directory_selection_accepts_batch_choices():
    app = App()
    subdirs = ["Volume 1", "Volume 2", "Volume 3", "Volume 4"]

    assert app._parse_export_directory_selection("A", subdirs) == subdirs
    assert app._parse_export_directory_selection("1,3", subdirs) == [
        "Volume 1",
        "Volume 3",
    ]
    assert app._parse_export_directory_selection("2-4", subdirs) == [
        "Volume 2",
        "Volume 3",
        "Volume 4",
    ]
    assert app._parse_export_directory_selection("3,1-2,3", subdirs) == [
        "Volume 3",
        "Volume 1",
        "Volume 2",
    ]
    assert app._parse_export_directory_selection("0", subdirs) == []


def test_build_epub_export_from_directories_keeps_multiple_volumes(tmp_path: Path):
    first = tmp_path / "Book 1"
    second = tmp_path / "Book 2"
    first.mkdir()
    second.mkdir()
    (first / "001_Start.txt").write_text("title\n=====\n\nfirst", encoding="utf-8")
    (second / "002_Next.txt").write_text("title\n=====\n\nsecond", encoding="utf-8")

    app = App()
    novel_info, volumes = app._build_epub_export_from_directories(
        str(tmp_path),
        ["Book 1", "Book 2"],
    )

    assert novel_info.title == "Book"
    assert [vol.name for vol in volumes] == ["Book 1", "Book 2"]
    assert [vol.chapters[0].title for vol in volumes] == ["Start", "Next"]
    assert [vol.chapters[0].index for vol in volumes] == [1, 2]
