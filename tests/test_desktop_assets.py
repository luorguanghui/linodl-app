from pathlib import Path

import pytest

from linodl.desktop.assets import DesktopAssets


def test_resolve_uses_built_index_from_project_root(tmp_path: Path):
    index = tmp_path / "frontend" / "dist" / "index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<main>linodl</main>", encoding="utf-8")
    icon = tmp_path / "assets" / "branding" / "linodl.ico"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"icon")

    assets = DesktopAssets.resolve(tmp_path)

    assert assets.index_file == index.resolve()
    assert assets.icon_file == icon.resolve()
    assert assets.url.startswith("file:")


def test_resolve_explains_missing_frontend_build(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="npm run build"):
        DesktopAssets.resolve(tmp_path)


def test_resolve_explains_missing_desktop_icon(tmp_path: Path):
    index = tmp_path / "frontend" / "dist" / "index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<main>linodl</main>", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="application icon"):
        DesktopAssets.resolve(tmp_path)
