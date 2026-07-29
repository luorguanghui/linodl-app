from __future__ import annotations

import os

import webview

from ..config.manager import ConfigManager
from .assets import DesktopAssets


def run_desktop(config: ConfigManager, debug: bool = False) -> None:
    from .bridge import DesktopBridge

    development_url = os.environ.get("LINODL_FRONTEND_URL", "").strip() if debug else ""
    url = development_url or DesktopAssets.resolve().url
    bridge = DesktopBridge(config=config, debug=debug)
    window = webview.create_window(
        "linodl 路 杞诲皬璇磋祫鏂欏簱",
        url=url,
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(900, 640),
    )
    bridge.attach_window(window)
    webview.start(debug=debug)
