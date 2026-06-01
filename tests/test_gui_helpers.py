from pathlib import Path

from linodl.gui.directory_scan import scan_download_directories
from linodl.gui.app import MainWindow
from linodl.gui.widgets.progress_area import parse_progress_message


def test_parse_progress_message_extracts_current_and_total():
    assert parse_progress_message("[3/20] [第一卷] 标题...") == (3, 20)
    assert parse_progress_message("[10/10] [第二卷] 插图... OK") == (10, 10)


def test_parse_progress_message_ignores_non_progress_text():
    assert parse_progress_message("正在启动浏览器...") is None
    assert parse_progress_message("ERROR: failed") is None


def test_scan_download_directories_returns_empty_for_empty_output(tmp_path: Path):
    assert scan_download_directories(str(tmp_path), include_images=True) == []


def test_scan_download_directories_counts_text_and_images(tmp_path: Path):
    volume = tmp_path / "第一卷"
    volume.mkdir()
    (volume / "001_开端.txt").write_text("正文", encoding="utf-8")
    (volume / "readme.md").write_text("ignore", encoding="utf-8")
    illus_dir = volume / "插图"
    illus_dir.mkdir()
    (illus_dir / "cover.jpg").write_bytes(b"fake")
    (illus_dir / "cover.webp").write_bytes(b"fake")

    [info] = scan_download_directories(str(tmp_path), include_images=True)

    assert info.name == "第一卷"
    assert info.text_count == 1
    assert info.image_count == 2


def test_main_window_dispatches_string_result_to_active_panel_on_result():
    class FakePanel:
        def __init__(self):
            self.result = None

        def on_result(self, value):
            self.result = value

    window = MainWindow.__new__(MainWindow)
    panel = FakePanel()
    window._active_worker_panel = panel

    window._dispatch_result("Cloudflare 验证成功完成。")

    assert panel.result == "Cloudflare 验证成功完成。"
