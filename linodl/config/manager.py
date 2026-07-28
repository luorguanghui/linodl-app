"""Configuration manager using INI file."""

import os
import configparser
import tempfile
from pathlib import Path


def effective_geoip(proxy: str, requested: bool) -> bool:
    """GeoIP matching is meaningful only when traffic uses a proxy."""
    return bool((proxy or "").strip() and requested)


class ConfigManager:
    """Singleton-style config manager backed by ~/.linovelib.ini."""

    def __init__(self, config_path: str = None):
        if config_path:
            self._path = Path(config_path)
        else:
            self._path = Path.home() / ".linovelib.ini"
        self._cfg = configparser.ConfigParser()
        self._ensure_defaults()

    def _ensure_defaults(self):
        if not self._path.exists():
            self._apply_default_values()
            self._save()
        else:
            self._cfg.read(str(self._path), encoding="utf-8")
            self._apply_default_values()

    def _apply_default_values(self):
        defaults = {
            "account": {"username": "", "password": ""},
            "download": {
                "output_dir": "novel_output",
                "delay_min": "0.3",
                "delay_max": "1.0",
                "headless": "true",
                "anti_bot_mode": "cloak",
                "profile_dir": str(Path.home() / ".linodl-browser"),
            },
            "network": {"proxy": "", "geoip": "false"},
            "ui": {"theme": "auto"},
        }

        for section, values in defaults.items():
            if not self._cfg.has_section(section):
                self._cfg.add_section(section)
            for key, value in values.items():
                if not self._cfg.has_option(section, key):
                    self._cfg.set(section, key, value)

    def _save(self):
        os.makedirs(str(self._path.parent), exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self._path.parent),
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                self._cfg.write(temp_file)
                temp_path = temp_file.name
            os.replace(temp_path, self._path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def update_settings(
        self,
        *,
        username: str,
        password: str,
        output_dir: str,
        headless: bool,
        anti_bot_mode: str,
        profile_dir: str,
        proxy: str,
        geoip: bool,
        theme: str,
    ):
        """Validate and persist the settings form as one consistent snapshot."""
        proxy = (proxy or "").strip()
        anti_bot_mode = (anti_bot_mode or "").strip().lower()
        if anti_bot_mode not in {"auto", "playwright", "cloak"}:
            anti_bot_mode = "auto"
        theme = (theme or "").strip().lower()
        if theme not in {"auto", "light", "dark"}:
            theme = "auto"

        values = {
            "account": {
                "username": username or "",
                "password": password or "",
            },
            "download": {
                "output_dir": output_dir or "novel_output",
                "headless": "true" if headless else "false",
                "anti_bot_mode": anti_bot_mode,
                "profile_dir": profile_dir or str(Path.home() / ".linodl-browser"),
            },
            "network": {
                "proxy": proxy,
                "geoip": "true" if effective_geoip(proxy, geoip) else "false",
            },
            "ui": {"theme": theme},
        }
        for section, options in values.items():
            for key, value in options.items():
                self._cfg.set(section, key, value)
        self._save()

    # ---- account ----

    @property
    def username(self) -> str:
        return self._cfg.get("account", "username", fallback="")

    @username.setter
    def username(self, value: str):
        self._cfg.set("account", "username", value)
        self._save()

    @property
    def password(self) -> str:
        return self._cfg.get("account", "password", fallback="")

    @password.setter
    def password(self, value: str):
        self._cfg.set("account", "password", value)
        self._save()

    def has_credentials(self) -> bool:
        return bool(self.username and self.password)

    def set_credentials(self, username: str, password: str):
        self.username = username
        self.password = password

    # ---- download ----

    @property
    def output_dir(self) -> str:
        return self._cfg.get("download", "output_dir", fallback="novel_output")

    @output_dir.setter
    def output_dir(self, value: str):
        self._cfg.set("download", "output_dir", value)
        self._save()

    @property
    def delay_range(self) -> tuple:
        lo = self._cfg.getfloat("download", "delay_min", fallback=0.3)
        hi = self._cfg.getfloat("download", "delay_max", fallback=1.0)
        return (lo, hi)

    @property
    def headless(self) -> bool:
        return self._cfg.getboolean("download", "headless", fallback=True)

    @headless.setter
    def headless(self, value: bool):
        self._cfg.set("download", "headless", "true" if value else "false")
        self._save()

    @property
    def anti_bot_mode(self) -> str:
        value = self._cfg.get("download", "anti_bot_mode", fallback="auto").strip().lower()
        return value if value in {"auto", "playwright", "cloak"} else "auto"

    @anti_bot_mode.setter
    def anti_bot_mode(self, value: str):
        value = value.strip().lower()
        if value not in {"auto", "playwright", "cloak"}:
            value = "auto"
        self._cfg.set("download", "anti_bot_mode", value)
        self._save()

    @property
    def profile_dir(self) -> str:
        return self._cfg.get(
            "download",
            "profile_dir",
            fallback=str(Path.home() / ".linodl-browser"),
        )

    @profile_dir.setter
    def profile_dir(self, value: str):
        self._cfg.set("download", "profile_dir", value)
        self._save()

    @property
    def proxy(self) -> str:
        return self._cfg.get("network", "proxy", fallback="").strip()

    @proxy.setter
    def proxy(self, value: str):
        self._cfg.set("network", "proxy", value.strip())
        self._save()

    @property
    def geoip(self) -> bool:
        return self._cfg.getboolean("network", "geoip", fallback=False)

    @geoip.setter
    def geoip(self, value: bool):
        self._cfg.set("network", "geoip", "true" if value else "false")
        self._save()

    # ---- ui ----

    @property
    def theme(self) -> str:
        value = self._cfg.get("ui", "theme", fallback="auto").strip().lower()
        return value if value in {"auto", "light", "dark"} else "auto"

    @theme.setter
    def theme(self, value: str):
        value = value.strip().lower()
        if value not in {"auto", "light", "dark"}:
            value = "auto"
        self._cfg.set("ui", "theme", value)
        self._save()
