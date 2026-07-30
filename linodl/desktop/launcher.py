from __future__ import annotations

from linodl.config.manager import ConfigManager
from linodl.desktop.app import run_desktop


def main() -> None:
    run_desktop(ConfigManager())


if __name__ == "__main__":
    main()
