"""Redaction helpers for user-visible diagnostics."""

from __future__ import annotations

import re


_URL_USERINFO = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)"
    r"(?P<username>[^/\s:@]+):(?P<password>[^@\s/]+)@",
    re.IGNORECASE,
)
_NAMED_SECRET = re.compile(
    r"\b(?P<name>password|passwd|token|api[_-]?key|authorization|cookie|cf_clearance)"
    r"(?P<separator>\s*[=:]\s*)"
    r"(?P<value>[^\s;,]+)",
    re.IGNORECASE,
)


def redact_sensitive_text(value) -> str:
    """Remove common credentials and tokens from diagnostic text."""
    text = str(value)
    text = _URL_USERINFO.sub(
        lambda match: f"{match.group('scheme')}***:***@",
        text,
    )
    return _NAMED_SECRET.sub(
        lambda match: (
            f"{match.group('name')}{match.group('separator')}***"
        ),
        text,
    )
