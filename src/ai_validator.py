"""
GhostCore OS — Phase 1: Incoming AI Code Validator

Validates JSON produced by the LLM before it enters the compilation pipeline.
Three layers:
  1. Structural validation — required fields, types, enum ranges
  2. Nix syntax check — if nix-instantiate is available, parse generated Nix
  3. Tier classification — auto-detect which tier (T0-T3) the operation belongs to

Tiers:
  T0 — Read-only queries (safe, auto-apply)
  T1 — User-space changes (dotfiles, home packages — sandboxed)
  T2 — System config changes (NixOS rebuild — requires confirmation)
  T3 — Destructive/irreversible (disk wipe, LUKS format — blocked by default)
"""

from __future__ import annotations

import json
import re
import subprocess
from enum import IntEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

class Tier(IntEnum):
    """Operation risk tiers."""
    T0_READONLY = 0
    T1_USERSPACE = 1
    T2_SYSTEM = 2
    T3_DESTRUCTIVE = 3


# Keywords that indicate destructive operations
_DESTRUCTIVE_KEYWORDS = {
    "wipe", "format", "mkfs", "dd", "shred", "luksformat",
    "fdisk", "parted", "disko", "destroy", "delete-all",
}

# Keywords that indicate system-level changes
_SYSTEM_KEYWORDS = {
    "nixos-rebuild", "systemd", "kernel", "boot", "luks",
    "networking", "firewall", "iptables", "nftables",
    "users.users", "fileSystems", "swapDevices",
}

# Keywords that indicate user-level changes
_USER_KEYWORDS = {
    "home-manager", "dotfiles", "stow", "dconf", "git clone",
    "nix-env", "profile", "bashrc", "zshrc", "config",
}


def classify_tier(nix_code: str) -> Tier:
    """
    Classify the risk tier of generated Nix code based on keyword analysis.

    This is a heuristic — the final tier decision also depends on context.
    """
    code_lower = nix_code.lower()

    for keyword in _DESTRUCTIVE_KEYWORDS:
        if keyword in code_lower:
            return Tier.T3_DESTRUCTIVE

    for keyword in _SYSTEM_KEYWORDS:
        if keyword in code_lower:
            return Tier.T2_SYSTEM

    for keyword in _USER_KEYWORDS:
        if keyword in code_lower:
            return Tier.T1_USERSPACE

    # Default: if it's a full NixOS configuration, it's at least T2
    if "configuration.nix" in code_lower or "{ config, pkgs" in nix_code:
        return Tier.T2_SYSTEM

    return Tier.T0_READONLY


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

# Valid enum values (mirror of schemas/ux_fingerprint.json)
_VALID_WM = {"hyprland", "sway", "i3", "gnome", "kde", "xfce", "none"}
_VALID_THEME = {
    "catppuccin-mocha", "catppuccin-latte", "dracula", "nord",
    "gruvbox-dark", "gruvbox-light", "tokyo-night", "rose-pine",
    "adwaita", "breeze",
}
_VALID_ICON = {"papirus", "tela", "colloid", "breeze", "adwaita", "nordic"}
_VALID_BROWSER = {"firefox", "chromium", "librewolf", "floorp", "qutebrowser", "nyxt"}
_VALID_TERMINAL = {"alacritty", "foot", "kitty", "wezterm", "ghostty", "konsole"}
_VALID_SHELL = {"bash", "zsh", "fish", "nushell", "dash"}
_VALID_LAYOUT = {"us", "ua", "ru", "de", "fr", "gb", "dvorak", "colemak"}
_VALID_PARANOIA = {"minimal", "standard", "paranoid", "hardened"}
_VALID_CATEGORIES = {
    "development", "media", "gaming", "office",
    "communication", "system-tools", "creative", "security",
}
_VALID_VPN = {"none", "wireguard", "openvpn", "tailscale"}
_VALID_CAMERA = {"allow", "deny", "ask"}

_REQUIRED_TOP = {
    "schema_version", "profile_name", "desktop", "terminal",
    "keyboard", "packages", "security", "network",
}


def validate_fingerprint_structure(fp: dict[str, Any]) -> list[str]:
    """
    Validate the structure of a UX Fingerprint JSON object.

    Returns a list of error strings. Empty list means valid.
    """
    errors: list[str] = []

    # Check required top-level fields
    for field in _REQUIRED_TOP:
        if field not in fp:
            errors.append(f"Missing required field: {field}")

    # schema_version
    if fp.get("schema_version") != "0.1.0":
        errors.append(f"Invalid schema_version: {fp.get('schema_version')!r} (expected '0.1.0')")

    # profile_name
    profile_name = fp.get("profile_name", "")
    if not isinstance(profile_name, str) or not re.match(r"^[a-zA-Z0-9_-]+$", profile_name):
        errors.append(f"Invalid profile_name: {profile_name!r}")
    elif len(profile_name) > 64:
        errors.append(f"profile_name too long: {len(profile_name)} > 64")

    # desktop
    desktop = fp.get("desktop", {})
    if not isinstance(desktop, dict):
        errors.append("desktop must be an object")
    else:
        wm = desktop.get("wm")
        if wm and wm not in _VALID_WM:
            errors.append(f"Invalid desktop.wm: {wm!r}")
        theme = desktop.get("theme")
        if theme and theme not in _VALID_THEME:
            errors.append(f"Invalid desktop.theme: {theme!r}")
        icon = desktop.get("icon_theme")
        if icon and icon not in _VALID_ICON:
            errors.append(f"Invalid desktop.icon_theme: {icon!r}")
        browser = desktop.get("browser")
        if browser and browser not in _VALID_BROWSER:
            errors.append(f"Invalid desktop.browser: {browser!r}")
        terminal = desktop.get("terminal")
        if terminal and terminal not in _VALID_TERMINAL:
            errors.append(f"Invalid desktop.terminal: {terminal!r}")

    # terminal
    term = fp.get("terminal", {})
    if not isinstance(term, dict):
        errors.append("terminal must be an object")
    else:
        shell = term.get("shell")
        if shell and shell not in _VALID_SHELL:
            errors.append(f"Invalid terminal.shell: {shell!r}")
        font_size = term.get("font_size")
        if font_size is not None and (not isinstance(font_size, (int, float)) or font_size < 6 or font_size > 32):
            errors.append(f"Invalid terminal.font_size: {font_size!r} (must be 6-32)")

    # keyboard
    kb = fp.get("keyboard", {})
    if not isinstance(kb, dict):
        errors.append("keyboard must be an object")
    else:
        layout = kb.get("layout")
        if layout and layout not in _VALID_LAYOUT:
            errors.append(f"Invalid keyboard.layout: {layout!r}")

    # packages
    pkgs = fp.get("packages", {})
    if not isinstance(pkgs, dict):
        errors.append("packages must be an object")
    else:
        categories = pkgs.get("categories", [])
        if not isinstance(categories, list) or len(categories) == 0:
            errors.append("packages.categories must be a non-empty array")
        else:
            for cat in categories:
                if cat not in _VALID_CATEGORIES:
                    errors.append(f"Invalid package category: {cat!r}")

    # security
    sec = fp.get("security", {})
    if not isinstance(sec, dict):
        errors.append("security must be an object")
    else:
        paranoia = sec.get("paranoia_level")
        if paranoia and paranoia not in _VALID_PARANOIA:
            errors.append(f"Invalid security.paranoia_level: {paranoia!r}")

    # network
    net = fp.get("network", {})
    if not isinstance(net, dict):
        errors.append("network must be an object")
    else:
        vpn = net.get("enable_vpn")
        if vpn and vpn not in _VALID_VPN:
            errors.append(f"Invalid network.enable_vpn: {vpn!r}")

    return errors


# ---------------------------------------------------------------------------
# Nix syntax check
# ---------------------------------------------------------------------------

def check_nix_syntax(nix_code: str) -> tuple[bool, str]:
    """
    Check if Nix code is syntactically valid using nix-instantiate --parse.

    Returns (ok, message). If nix-instantiate is not installed, returns (True, "nix not installed").
    """
    try:
        result = subprocess.run(
            ["nix-instantiate", "--parse", "-"],
            input=nix_code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, "Nix syntax OK"
        else:
            return False, f"Nix syntax error: {result.stderr.strip()}"
    except FileNotFoundError:
        return True, "nix-instantiate not installed — skipping syntax check"
    except subprocess.TimeoutExpired:
        return False, "nix-instantiate timed out (10s)"


# ---------------------------------------------------------------------------
# Combined validation
# ---------------------------------------------------------------------------

def validate_ai_output(
    fingerprint: dict[str, Any],
    nix_code: str | None = None,
) -> dict[str, Any]:
    """
    Full validation of AI output: structure + Nix syntax + tier classification.

    Returns a dict with:
        - valid: bool
        - errors: list[str]
        - tier: Tier
        - tier_name: str
        - nix_ok: bool | None
        - nix_msg: str
    """
    # 1. Structural validation
    struct_errors = validate_fingerprint_structure(fingerprint)

    # 2. Nix syntax check (if code provided)
    nix_ok = None
    nix_msg = "No Nix code provided"
    if nix_code is not None:
        nix_ok, nix_msg = check_nix_syntax(nix_code)

    # 3. Tier classification
    tier = classify_tier(nix_code or "")

    all_errors = list(struct_errors)
    if nix_ok is False:
        all_errors.append(nix_msg)

    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "tier": int(tier),
        "tier_name": tier.name,
        "nix_ok": nix_ok,
        "nix_msg": nix_msg,
    }
