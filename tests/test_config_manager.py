from pathlib import Path

from linodl.config import manager as config_manager
from linodl.config.manager import ConfigManager


def test_config_manager_supplies_new_defaults_for_existing_config(tmp_path: Path):
    cfg_path = tmp_path / ".linovelib.ini"
    cfg_path.write_text(
        """
[account]
username = user
password = pass

[download]
output_dir = old_output
delay_min = 1.0
delay_max = 2.0
headless = false
""".strip(),
        encoding="utf-8",
    )

    cfg = ConfigManager(str(cfg_path))

    assert cfg.anti_bot_mode == "cloak"
    assert cfg.proxy == ""
    assert cfg.geoip is False
    assert cfg.profile_dir.endswith(".linodl-browser")


def test_config_manager_persists_network_and_antibot_settings(tmp_path: Path):
    cfg = ConfigManager(str(tmp_path / ".linovelib.ini"))

    cfg.anti_bot_mode = "cloak"
    cfg.profile_dir = str(tmp_path / "profile")
    cfg.proxy = "socks5://127.0.0.1:1080"
    cfg.geoip = True

    reloaded = ConfigManager(str(tmp_path / ".linovelib.ini"))

    assert reloaded.anti_bot_mode == "cloak"
    assert reloaded.profile_dir == str(tmp_path / "profile")
    assert reloaded.proxy == "socks5://127.0.0.1:1080"
    assert reloaded.geoip is True


def test_config_manager_persists_theme_setting(tmp_path: Path):
    cfg = ConfigManager(str(tmp_path / ".linovelib.ini"))

    cfg.theme = "dark"

    reloaded = ConfigManager(str(tmp_path / ".linovelib.ini"))
    assert reloaded.theme == "dark"


def test_config_manager_rejects_unknown_theme(tmp_path: Path):
    cfg = ConfigManager(str(tmp_path / ".linovelib.ini"))

    cfg.theme = "sepia"

    assert cfg.theme == "auto"


def test_update_settings_writes_consistent_snapshot_and_disables_geoip_without_proxy(
    tmp_path: Path,
):
    cfg = ConfigManager(str(tmp_path / ".linovelib.ini"))

    cfg.update_settings(
        username="reader",
        password="secret",
        output_dir="books",
        headless=True,
        anti_bot_mode="cloak",
        profile_dir="profile",
        proxy="",
        geoip=True,
        theme="dark",
    )

    reloaded = ConfigManager(str(tmp_path / ".linovelib.ini"))
    assert reloaded.username == "reader"
    assert reloaded.output_dir == "books"
    assert reloaded.geoip is False
    assert reloaded.theme == "dark"


def test_effective_geoip_requires_proxy():
    assert config_manager.effective_geoip("", True) is False
    assert config_manager.effective_geoip("socks5://127.0.0.1:1080", True) is True
    assert config_manager.effective_geoip("http://127.0.0.1:8080", False) is False
