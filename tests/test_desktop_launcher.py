import runpy
from pathlib import Path


def test_packaged_launcher_starts_desktop_with_user_config(monkeypatch, tmp_path):
    from linodl.desktop import launcher

    received = []
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr(launcher, "run_desktop", received.append)

    launcher.main()

    assert len(received) == 1
    assert received[0]._path == tmp_path / ".linovelib.ini"


def test_packaged_launcher_can_be_analyzed_as_a_standalone_script():
    launcher_path = Path(__file__).parents[1] / "linodl" / "desktop" / "launcher.py"

    namespace = runpy.run_path(str(launcher_path), run_name="pyinstaller_analysis")

    assert callable(namespace["main"])
