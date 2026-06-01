from pathlib import Path

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
