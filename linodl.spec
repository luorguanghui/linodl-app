from pathlib import Path

from PyInstaller.building.datastruct import Tree


project_root = Path(SPEC).resolve().parent
frontend_dist = project_root / "frontend" / "dist"
branding_dir = project_root / "assets" / "branding"
application_icon = branding_dir / "linodl.ico"
vendor_cloakbrowser = project_root / "vendor" / "cloakbrowser"

if not (frontend_dist / "index.html").is_file():
    raise SystemExit("Frontend assets are missing. Run: cd frontend && npm run build")
if not application_icon.is_file():
    raise SystemExit("Application icon is missing: assets/branding/linodl.ico")

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
