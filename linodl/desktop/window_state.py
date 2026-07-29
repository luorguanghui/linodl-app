"""Safe persistence for the React desktop window's normal bounds."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


_DEFAULT_WIDTH = 1280
_DEFAULT_HEIGHT = 820
_MIN_WIDTH = 900
_MIN_HEIGHT = 640
_MAX_WIDTH = 7680
_MAX_HEIGHT = 4320
_MAX_POSITION = 10000


@dataclass(frozen=True)
class WindowState:
    width: int = _DEFAULT_WIDTH
    height: int = _DEFAULT_HEIGHT
    x: int | None = None
    y: int | None = None
    maximized: bool = False


class WindowStateStore:
    def __init__(self, path: Path):
        self._path = Path(path)

    def load(self) -> WindowState:
        try:
            with self._path.open(encoding="utf-8") as state_file:
                raw = json.load(state_file)
        except (OSError, ValueError, TypeError):
            return WindowState()
        if not isinstance(raw, dict):
            return WindowState()
        return self._normalize(raw)

    def save(self, state: WindowState) -> None:
        normalized = self._normalize(asdict(state))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as state_file:
                json.dump(asdict(normalized), state_file)
                temporary_path = state_file.name
            os.replace(temporary_path, self._path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _normalize(raw: dict) -> WindowState:
        width = WindowStateStore._bounded_int(
            raw.get("width"), _DEFAULT_WIDTH, _MIN_WIDTH, _MAX_WIDTH
        )
        height = WindowStateStore._bounded_int(
            raw.get("height"), _DEFAULT_HEIGHT, _MIN_HEIGHT, _MAX_HEIGHT
        )
        x = WindowStateStore._position(raw.get("x"))
        y = WindowStateStore._position(raw.get("y"))
        if x is None or y is None:
            x = None
            y = None
        return WindowState(
            width=width,
            height=height,
            x=x,
            y=y,
            maximized=raw.get("maximized") is True,
        )

    @staticmethod
    def _bounded_int(value: object, fallback: int, minimum: int, maximum: int) -> int:
        if type(value) is not int:
            return fallback
        return max(minimum, min(value, maximum))

    @staticmethod
    def _position(value: object) -> int | None:
        if type(value) is not int or abs(value) > _MAX_POSITION:
            return None
        return value
