"""License validation and caching for CloakBrowser Pro.

Handles license key resolution, server validation with local caching,
and Pro version checks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import get_cache_dir, get_platform_tag, normalize_release_channel

logger = logging.getLogger("cloakbrowser")

VALIDATE_URL = "https://cloakbrowser.dev/api/license/validate"
PRO_VERSION_URL = "https://cloakbrowser.dev/api/download/version"
SESSION_COUNT_URL = "https://cloakbrowser.dev/api/license/session/count"

LICENSE_CACHE_TTL = 86400  # 24 hours
PRO_VERSION_CHECK_INTERVAL = 3600  # 1 hour


@dataclass
class LicenseInfo:
    valid: bool
    plan: str
    expires: str | None


@dataclass(frozen=True)
class ProReleaseInfo:
    version: str
    requested_channel: str
    resolved_channel: str
    fallback: bool


def _release_from_sidecar(
    data: Mapping[str, object], version: str, channel: str
) -> ProReleaseInfo:
    """Build a ProReleaseInfo from a resolution-sidecar dict (snake_case, with a
    camelCase fallback for sidecars written by an older JS wrapper). A missing
    ``fallback`` defaults to ``requested != resolved`` — mirrors JS and .NET."""
    requested = str(data.get("requested_channel", data.get("requestedChannel", channel)))
    resolved = str(data.get("resolved_channel", data.get("resolvedChannel", "stable")))
    fallback = data.get("fallback")
    return ProReleaseInfo(
        version=version,
        requested_channel=requested,
        resolved_channel=resolved,
        fallback=bool(fallback) if fallback is not None else requested != resolved,
    )


class CloakBrowserLicenseError(RuntimeError):
    """The Pro binary refused to run for a license reason.

    Raised when a launch fails and the browser process exited with one of the
    Pro binary's license exit codes (see ``_LICENSE_EXIT_MESSAGES``). Carries a
    human-readable reason instead of the opaque "target/browser closed" error
    the caller would otherwise see.
    """


# Exit codes the Pro binary uses for honest-user license denials. The binary
# emits only the number (no diagnostic strings, by design); the message text
# lives here in the wrapper.
_LICENSE_EXIT_MESSAGES = {
    76: (
        "CloakBrowser Pro: session limit reached for your plan. Close another "
        "running session or upgrade your plan."
    ),
    77: (
        "CloakBrowser Pro: license key is invalid, expired, or missing. Check "
        "CLOAKBROWSER_LICENSE_KEY."
    ),
    78: (
        "CloakBrowser Pro: couldn't verify your license (license server "
        "unreachable or a connection problem)."
    ),
    79: (
        "CloakBrowser Pro: local configuration problem, ~/.cloakbrowser "
        "is not writable."
    ),
}

# Playwright reports a child-process exit in the launch-failure text as
# "<process did exit: exitCode=N, signal=null>". Anchor to that record so an
# unrelated "exitCode=" elsewhere in the error can't false-match.
_EXIT_CODE_RE = re.compile(r"process did exit:\s*exitCode=(\d+)")


def license_error_message(error_text: str) -> str | None:
    """Map a launch-failure message to a license reason, or None.

    Returns the human message when the browser process exited with a known
    license exit code, else None so a genuine crash propagates unchanged.
    """
    match = _EXIT_CODE_RE.search(error_text or "")
    if not match:
        return None
    try:
        exit_code = int(match.group(1))
    except ValueError:
        return None
    return _LICENSE_EXIT_MESSAGES.get(exit_code)


_LICENSE_KEY_SOURCE_PARAM = "param"
_LICENSE_KEY_SOURCE_ENV = "env"
_LICENSE_KEY_SOURCE_DEFAULT_FILE = "default_file"
_LICENSE_KEY_SOURCE_CUSTOM_FILE = "custom_file"
_LICENSE_KEY_SOURCE_NONE = "none"


def _resolve_license_key_with_source(
    license_key: str | None = None,
) -> tuple[str | None, str]:
    """Resolve license key with source tracking for env-injection decisions.

    Returns (key, source) where source is one of the _LICENSE_KEY_SOURCE_*
    constants. The source tells the caller *how* the key was found so they
    can decide whether env injection is needed (e.g. the binary reads the
    default file path directly, so env injection is unnecessary).
    """
    # 1. Explicit param
    if license_key and license_key.strip():
        return (license_key.strip(), _LICENSE_KEY_SOURCE_PARAM)

    # 2. Environment variable
    env_key = os.environ.get("CLOAKBROWSER_LICENSE_KEY", "").strip()
    if env_key:
        return (env_key, _LICENSE_KEY_SOURCE_ENV)

    # 3. File in the wrapper cache dir
    cache_dir = get_cache_dir()
    key_file = cache_dir / "license.key"
    try:
        content = key_file.read_text().strip()
        if content:
            default_cache = Path.home() / ".cloakbrowser"
            if cache_dir.resolve() == default_cache.resolve():
                source = _LICENSE_KEY_SOURCE_DEFAULT_FILE
            else:
                source = _LICENSE_KEY_SOURCE_CUSTOM_FILE
            return (content, source)
    except OSError:
        pass

    return (None, _LICENSE_KEY_SOURCE_NONE)


def resolve_license_key(license_key: str | None = None) -> str | None:
    """Resolve the license key: explicit param > env var > file > None."""
    key, _ = _resolve_license_key_with_source(license_key)
    return key


def build_launch_env(
    license_key: str | None = None,
    user_env: Mapping[str, str | None] | None = None,
) -> dict[str, str] | None:
    """Build child process env dict with any needed license key injection.

    The Pro binary reads ``CLOAKBROWSER_LICENSE_KEY`` from its own process
    environment at startup.  This helper merges the resolved key into the
    child process env dict **only** when injection is necessary:

    * **param** or **custom_file** source -> inject the key into the child env
      (the binary cannot see the wrapper-only key or the custom file path).
    * **env** source -> the key is already in ``os.environ``, so the child
      inherits it naturally.  No injection.
    * **default_file** source -> the binary reads ``~/.cloakbrowser/license.key``
      directly, so injection is unnecessary (and keeps the key out of process
      env for security) — *unless* the caller passes a custom ``user_env``,
      which Playwright uses to replace (not merge) the child env; a replaced
      env can drop ``HOME`` and hide the file, so the key is injected then.
    * **none** -> no key at all, no injection.

    When *user_env* is provided (e.g. the caller passed ``env=`` via
    Playwright kwargs), it is used as the base instead of ``os.environ``,
    and the key is injected only when needed.

    Returns ``None`` when no injection is needed and no custom user_env was
    given — Playwright treats ``env=None`` as "inherit parent env", which
    is correct in those cases.
    """
    key, source = _resolve_license_key_with_source(license_key)

    # Normalize the custom env once so every return path behaves identically:
    # drop None values (Playwright's env is typed str->str).
    base_env = (
        {k: v for k, v in user_env.items() if v is not None}
        if user_env is not None
        else None
    )

    # Default file: binary reads it directly — no env injection needed,
    # UNLESS the caller passes a custom env. Playwright replaces (not merges)
    # the child env, which can drop HOME and hide the file from the binary,
    # so inject the key too in that case (fall through to the merge below).
    if source == _LICENSE_KEY_SOURCE_DEFAULT_FILE and base_env is None:
        return None

    # No key at all: pass through the custom env or None.
    if source == _LICENSE_KEY_SOURCE_NONE or key is None:
        return base_env

    # Env source, no custom user env: child inherits parent env, which
    # already has CLOAKBROWSER_LICENSE_KEY.
    if source == _LICENSE_KEY_SOURCE_ENV and base_env is None:
        return None

    # Build the merged env dict.
    merged = dict(base_env) if base_env is not None else dict(os.environ)

    # For param/custom_file this is THE injection into the child env.
    # For env source with a custom user_env this ensures the key persists
    # through the user's env override (Playwright replaces, not merges).
    merged["CLOAKBROWSER_LICENSE_KEY"] = key

    return merged


def validate_license(license_key: str) -> LicenseInfo | None:
    """Validate a license key with the CloakBrowser server.

    Checks a local file cache first (24h TTL). Falls back to stale
    cache if the server is unreachable.

    Returns LicenseInfo if validation succeeded, None on total failure.
    """
    cache_path = get_cache_dir() / ".license_cache"
    key_sha = hashlib.sha256(license_key.encode()).hexdigest()

    cached = _read_cache(cache_path, key_sha)
    if cached:
        return cached

    try:
        resp = httpx.post(
            VALIDATE_URL,
            json={"license_key": license_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        info = LicenseInfo(
            valid=data.get("valid", False),
            plan=data.get("plan", "solo"),
            expires=data.get("expires"),
        )

        if info.valid:
            _write_cache(cache_path, key_sha, info)
        return info

    except Exception as e:
        logger.warning("License validation request failed: %s", e)

        stale = _read_cache(cache_path, key_sha, ignore_ttl=True)
        if stale:
            logger.warning("Using cached license validation (server unreachable)")
            return stale

        return None


def get_pro_latest_release(
    release_channel: str | None = None,
) -> ProReleaseInfo | None:
    """Get the server-resolved Pro release and channel for this platform."""
    channel = normalize_release_channel(release_channel)
    marker_suffix = (
        f"preview_{get_platform_tag()}"
        if channel == "preview"
        else get_platform_tag()
    )
    marker = get_cache_dir() / f".last_pro_version_check_{marker_suffix}"
    resolution_marker = get_cache_dir() / f".last_pro_version_resolution_{marker_suffix}"

    if marker.exists():
        try:
            age = time.time() - marker.stat().st_mtime
            if age < PRO_VERSION_CHECK_INTERVAL and resolution_marker.exists():
                data = json.loads(resolution_marker.read_text())
                version = marker.read_text().strip()
                if version and data.get("version") == version:
                    return _release_from_sidecar(data, version, channel)
        except (OSError, ValueError, TypeError):
            pass

    try:
        version_url = (
            f"{PRO_VERSION_URL}?channel=preview"
            if channel == "preview"
            else PRO_VERSION_URL
        )
        resp = httpx.get(
            version_url,
            headers={"X-Platform": get_platform_tag()},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        version = data.get("version")
        if not version:
            return None
        resolved_channel = str(data.get("resolved_channel", "stable"))
        release = ProReleaseInfo(
            version=str(version),
            requested_channel=str(data.get("requested_channel", channel)),
            resolved_channel=resolved_channel,
            fallback=bool(
                data.get("fallback", channel != resolved_channel)
            ),
        )

        marker.parent.mkdir(parents=True, exist_ok=True)
        resolution_tmp = resolution_marker.with_suffix(".tmp")
        resolution_tmp.write_text(json.dumps(release.__dict__))
        os.replace(str(resolution_tmp), str(resolution_marker))
        tmp = marker.with_suffix(".tmp")
        tmp.write_text(release.version)
        os.replace(str(tmp), str(marker))
        return release

    except Exception as e:
        logger.debug("Pro version check failed: %s", e)
        try:
            version = marker.read_text().strip()
            if not version:
                return None
            # Prefer the last successful fetch's channel metadata (the resolution
            # sidecar) so an offline preview build is not mislabeled as a stable
            # fallback. Older wrappers left only the version marker, so its channel
            # is unknowable — hardcode a conservative stable fallback then.
            if resolution_marker.exists():
                try:
                    data = json.loads(resolution_marker.read_text())
                    if data.get("version") == version:
                        return _release_from_sidecar(data, version, channel)
                except (OSError, ValueError, TypeError):
                    pass
            return ProReleaseInfo(version, channel, "stable", channel == "preview")
        except OSError:
            pass
        return None


def get_pro_latest_version(release_channel: str | None = None) -> str | None:
    """Get only the version from the server-resolved Pro release."""
    release = get_pro_latest_release(release_channel)
    return release.version if release else None


def get_active_session_count(license_key: str) -> int | None:
    """How many concurrent sessions (seats) this license is holding right now.

    Deliberately NOT cached: a cached seat count is a wrong seat count. Returns
    None when the number is unknown — the server couldn't be reached, or it
    reported the count as unavailable (it does that instead of a false 0 while
    running in leaseless mode). Callers render None as "unavailable".
    """
    try:
        resp = httpx.post(
            SESSION_COUNT_URL,
            json={"license_key": license_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("active")
    except Exception as e:
        logger.debug("Session count lookup failed: %s", e)
        return None


def _read_cache(
    cache_path: Path, key_sha: str, ignore_ttl: bool = False
) -> LicenseInfo | None:
    """Read cached license validation if it exists and is fresh."""
    try:
        if not cache_path.exists():
            return None

        data = json.loads(cache_path.read_text())

        if data.get("key_sha256") != key_sha:
            return None

        if not ignore_ttl:
            validated_at = data.get("validated_at", 0)
            if time.time() - validated_at > LICENSE_CACHE_TTL:
                return None

        expires = data.get("expires")
        if expires:
            try:
                from datetime import datetime, timezone
                exp_dt = datetime.fromisoformat(expires)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt < datetime.now(timezone.utc):
                    return LicenseInfo(valid=False, plan=data.get("plan", "solo"), expires=expires)
            except (ValueError, TypeError):
                pass

        return LicenseInfo(
            valid=data.get("valid", False),
            plan=data.get("plan", "solo"),
            expires=expires,
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        # TypeError: a corrupted cache with a non-numeric validated_at. Treat any
        # unreadable cache as absent rather than crashing the caller.
        return None


def _write_cache(cache_path: Path, key_sha: str, info: LicenseInfo) -> None:
    """Write license validation result to local cache (atomic via tmp+rename)."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps({
            "key_sha256": key_sha,
            "valid": info.valid,
            "plan": info.plan,
            "expires": info.expires,
            "validated_at": time.time(),
        }))
        os.replace(str(tmp_path), str(cache_path))
    except OSError as e:
        logger.debug("Failed to write license cache: %s", e)
