"""
GhostCore OS — Phase 1: Privacy Shield

Local PII scrubber. Runs entirely on-device before any data leaves for an LLM API.
Replaces sensitive tokens with placeholders and keeps a reversible mapping so the
real values can be restored after the LLM response comes back.

Design goals:
  - Zero network calls — pure regex + string ops
  - Reversible — restore_map lets you put real values back into LLM output
  - Idempotent — scrubbing an already-scrubbed text is a no-op
  - No false positives on enum values (e.g. "adwaita", "eu_us" must survive)
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Regex patterns for PII detection
# ---------------------------------------------------------------------------

# IPv4 addresses (exclude common non-sensitive ranges loosely)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b"
)

# IPv6 (simplified — matches standard hex-group notation)
_IPV6_RE = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"
)

# Email addresses
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# File paths — Unix home dirs
_UNIX_HOME_RE = re.compile(
    r"/home/([a-zA-Z0-9_.-]+)"
)

# File paths — Windows user dirs
_WIN_HOME_RE = re.compile(
    r"[A-Za-z]:[\\/]Users[\\/]([a-zA-Z0-9_.-]+)"
)

# SSH private key headers
_SSH_KEY_RE = re.compile(
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----.*?-----END[ A-Z]*PRIVATE KEY-----",
    re.DOTALL,
)

# Generic secrets / tokens (hex blobs ≥ 32 chars, base64 ≥ 40 chars with = padding)
_HEX_SECRET_RE = re.compile(
    r"\b[0-9a-fA-F]{32,}\b"
)
_B64_SECRET_RE = re.compile(
    r"\b[A-Za-z0-9+/]{40,}={0,3}\b"
)

# GPG key IDs (8 or 16 hex chars after "0x" or standalone)
_GPG_KEY_RE = re.compile(
    r"\b0x[0-9a-fA-F]{8,16}\b"
)

# Hostnames in URLs or ssh@host patterns
_HOST_RE = re.compile(
    r"\b(?:ssh://|https?://|git@)([a-zA-Z0-9][a-zA-Z0-9.-]{1,253})"
)


def _generate_placeholder(kind: str, index: int) -> str:
    """Generate a deterministic placeholder string."""
    return f"<{kind.upper()}_{index}>"


def scrub_text(text: str) -> tuple[str, dict[str, str]]:
    """
    Scrub PII from a plain text string.

    Returns:
        (scrubbed_text, restore_map) — restore_map maps placeholder → original
    """
    restore_map: dict[str, str] = {}
    counter: dict[str, int] = {}

    def _replace(pattern: re.Pattern, kind: str, s: str) -> str:
        """Replace all matches of pattern with placeholders."""
        def _sub(match: re.Match) -> str:
            original = match.group(0)
            if original in restore_map:
                return original  # already replaced
            counter[kind] = counter.get(kind, 0) + 1
            placeholder = _generate_placeholder(kind, counter[kind])
            restore_map[placeholder] = original
            return placeholder
        return pattern.sub(_sub, s)

    result = text

    # Order matters: more specific patterns first
    result = _replace(_SSH_KEY_RE, "ssh_key", result)
    result = _replace(_EMAIL_RE, "email", result)
    result = _replace(_GPG_KEY_RE, "gpg_key", result)
    result = _replace(_UNIX_HOME_RE, "unix_home", result)
    result = _replace(_WIN_HOME_RE, "win_home", result)
    result = _replace(_IPV4_RE, "ip", result)
    result = _replace(_IPV6_RE, "ipv6", result)
    result = _replace(_HOST_RE, "host", result)
    result = _replace(_HEX_SECRET_RE, "hex_secret", result)
    result = _replace(_B64_SECRET_RE, "b64_secret", result)

    return result, restore_map


def scrub_json(obj: Any) -> tuple[Any, dict[str, str]]:
    """
    Recursively scrub PII from a JSON-like object (dicts, lists, strings).

    Returns:
        (scrubbed_obj, restore_map)
    """
    if isinstance(obj, str):
        scrubbed, mp = scrub_text(obj)
        return scrubbed, mp
    elif isinstance(obj, dict):
        new_dict: dict[str, Any] = {}
        combined_map: dict[str, str] = {}
        for key, value in obj.items():
            scrubbed_val, mp = scrub_json(value)
            new_dict[key] = scrubbed_val
            combined_map.update(mp)
        return new_dict, combined_map
    elif isinstance(obj, list):
        new_list: list[Any] = []
        combined_map: dict[str, str] = {}
        for item in obj:
            scrubbed_item, mp = scrub_json(item)
            new_list.append(scrubbed_item)
            combined_map.update(mp)
        return new_list, combined_map
    else:
        # Numbers, booleans, None — pass through
        return obj, {}


def restore_text(text: str, restore_map: dict[str, str]) -> str:
    """Restore original values from a restore_map into scrubbed text."""
    result = text
    # Sort by length descending to avoid partial replacements
    for placeholder, original in sorted(restore_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(placeholder, original)
    return result


def restore_json(obj: Any, restore_map: dict[str, str]) -> Any:
    """Recursively restore original values in a JSON-like object."""
    if isinstance(obj, str):
        return restore_text(obj, restore_map)
    elif isinstance(obj, dict):
        return {k: restore_json(v, restore_map) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [restore_json(item, restore_map) for item in obj]
    else:
        return obj
