"""Stable, JSON-ready data transfer object serialization for the desktop UI."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import TypeAlias

from ..core.sanitization import redact_sensitive_text
from ..models.novel import VerificationResult, Volume

JSONPrimitive: TypeAlias = (
    None | bool | int | float | str | list["JSONPrimitive"] | dict[str, "JSONPrimitive"]
)


def to_primitive(value: object) -> JSONPrimitive:
    """Convert supported UI data into redacted, JSON-ready primitive values."""
    if isinstance(value, Enum):
        return to_primitive(value.value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {
            redact_sensitive_text(key): to_primitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        payload = {
            field.name: to_primitive(getattr(value, field.name))
            for field in fields(value)
        }
        if isinstance(value, Volume):
            payload["text_count"] = value.text_count
            payload["illus_count"] = value.illus_count
        if isinstance(value, VerificationResult):
            payload["is_clean"] = value.is_clean
            payload["issue_count"] = value.issue_count
        return payload
    raise TypeError(f"Unsupported desktop DTO value: {type(value).__name__}")
