import json
import os
from importlib.util import find_spec
from pathlib import Path

from PyInstaller.building.datastruct import Tree


project_root = Path(SPEC).resolve().parent
frontend_dist = project_root / "frontend" / "dist"
branding_dir = project_root / "assets" / "branding"
application_icon = branding_dir / "linodl.ico"
vendor_cloakbrowser = project_root / "vendor" / "cloakbrowser"
playwright_spec = find_spec("playwright")
if playwright_spec is None or playwright_spec.origin is None:
    raise SystemExit("Playwright is missing. Run: python -m pip install -r requirements-build.txt")
playwright_package = Path(playwright_spec.origin).resolve().parent
playwright_browsers = json.loads(
    (playwright_package / "driver" / "package" / "browsers.json").read_text(
        encoding="utf-8"
    )
)["browsers"]
chromium = next(browser for browser in playwright_browsers if browser["name"] == "chromium")
browser_cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
chromium_dir = browser_cache / f"chromium-{chromium['revision']}"

if not (frontend_dist / "index.html").is_file():
    raise SystemExit("Frontend assets are missing. Run: cd frontend && npm run build")
if not application_icon.is_file():
    raise SystemExit("Application icon is missing: assets/branding/linodl.ico")
if not (chromium_dir / "chrome-win64" / "chrome.exe").is_file():
    raise SystemExit("Playwright Chromium is missing. Run: python -m playwright install chromium")

a = Analysis(
    [str(project_root / "linodl" / "desktop" / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(frontend_dist), "frontend/dist"),
        (str(branding_dir), "assets/branding"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += Tree(
    str(vendor_cloakbrowser),
    prefix="vendor/cloakbrowser",
    excludes=["cloak", "cloak/*", "__pycache__", "*.pyc"],
)
a.datas += Tree(
    str(chromium_dir),
    prefix=f"playwright/driver/package/.local-browsers/{chromium_dir.name}",
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="linodl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(application_icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="linodl",
)
