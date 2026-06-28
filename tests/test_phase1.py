"""
GhostCore OS — Phase 1: Test suite for new modules.

Tests for:
  - privacy_shield.py
  - ai_validator.py
  - sandbox.py

Usage:
  python -m pytest tests/test_phase1.py -v
  python tests/test_phase1.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from privacy_shield import restore_json, scrub_json, scrub_text
from ai_validator import (
    Tier,
    classify_tier,
    check_nix_syntax,
    validate_ai_output,
    validate_fingerprint_structure,
)
from sandbox import (
    SandboxResult,
    _diff_snapshots,
    _snapshot_dir,
    _dry_run,
    is_bwrap_available,
    run_sandboxed,
)


# ===========================================================================
# Privacy Shield Tests
# ===========================================================================

def test_scrub_email():
    text = "Contact me at alice@example.com for details."
    scrubbed, mp = scrub_text(text)
    assert "alice@example.com" not in scrubbed
    assert "<EMAIL_" in scrubbed
    assert mp  # non-empty restore map


def test_scrub_ipv4():
    text = "Server at 192.168.1.100 is up."
    scrubbed, mp = scrub_text(text)
    assert "192.168.1.100" not in scrubbed
    assert "<IP_" in scrubbed


def test_scrub_unix_home():
    text = "My configs are in /home/bob/dotfiles/"
    scrubbed, mp = scrub_text(text)
    assert "/home/bob" not in scrubbed
    assert "<UNIX_HOME_" in scrubbed


def test_scrub_windows_home():
    text = "Found at C:\\Users\\alice\\Documents\\file.txt"
    scrubbed, mp = scrub_text(text)
    assert "C:\\Users\\alice" not in scrubbed
    assert "<WIN_HOME_" in scrubbed


def test_scrub_ssh_key():
    text = """Key: -----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACB0h8yL9z4E0oLgX+6KqP0O4wJ7H9kSuQ7F3vT5qgJfQAAAA
-----END OPENSSH PRIVATE KEY-----"""
    scrubbed, mp = scrub_text(text)
    assert "PRIVATE KEY" not in scrubbed
    assert "<SSH_KEY_" in scrubbed


def test_scrub_gpg_key():
    text = "Signing key: 0xDEADBEEF12345678"
    scrubbed, mp = scrub_text(text)
    assert "0xDEADBEEF12345678" not in scrubbed
    assert "<GPG_KEY_" in scrubbed


def test_scrub_preserves_enums():
    """Enum values like 'adwaita', 'us', 'bash' must NOT be scrubbed."""
    text = "I use adwaita theme with us layout and bash shell."
    scrubbed, mp = scrub_text(text)
    assert "adwaita" in scrubbed
    assert "us" in scrubbed
    assert "bash" in scrubbed
    assert mp == {}  # nothing should have been scrubbed


def test_scrub_json_nested():
    fp = {
        "profile_name": "test",
        "network": {
            "hostname": "my-server",
            "enable_vpn": "wireguard",
        },
        "git": {
            "email": "user@example.com",
            "username": "alice",
        },
    }
    scrubbed, mp = scrub_json(fp)
    assert "user@example.com" not in json.dumps(scrubbed)
    assert "test" == scrubbed["profile_name"]  # preserved
    assert "wireguard" == scrubbed["network"]["enable_vpn"]  # preserved


def test_restore_roundtrip():
    original = "Email alice@example.com from 10.0.0.1"
    scrubbed, mp = scrub_text(original)
    restored = restore_json(scrubbed, mp)
    assert restored == original


def test_restore_json_roundtrip():
    original = {
        "user": "bob",
        "email": "bob@example.org",
        "path": "/home/bob/.config",
    }
    scrubbed, mp = scrub_json(original)
    restored = restore_json(scrubbed, mp)
    assert restored == original


def test_idempotent_scrub():
    text = "Safe text with no PII."
    scrubbed1, mp1 = scrub_text(text)
    scrubbed2, mp2 = scrub_text(scrubbed1)
    assert scrubbed1 == scrubbed2
    assert mp1 == mp2


# ===========================================================================
# AI Validator Tests
# ===========================================================================

def test_validate_valid_fingerprint():
    fp = {
        "schema_version": "0.1.0",
        "profile_name": "test-profile",
        "desktop": {"wm": "hyprland", "theme": "catppuccin-mocha", "icon_theme": "papirus"},
        "terminal": {"shell": "zsh", "font": "JetBrains Mono"},
        "keyboard": {"layout": "us"},
        "packages": {"categories": ["development"]},
        "security": {"paranoia_level": "standard"},
        "network": {"hostname": "myhost"},
    }
    errors = validate_fingerprint_structure(fp)
    assert errors == [], f"Unexpected errors: {errors}"


def test_validate_invalid_wm():
    fp = {
        "schema_version": "0.1.0",
        "profile_name": "test",
        "desktop": {"wm": "invalid-wm", "theme": "adwaita", "icon_theme": "adwaita"},
        "terminal": {"shell": "bash", "font": "mono"},
        "keyboard": {"layout": "us"},
        "packages": {"categories": ["development"]},
        "security": {"paranoia_level": "standard"},
        "network": {},
    }
    errors = validate_fingerprint_structure(fp)
    assert any("wm" in e for e in errors)


def test_validate_missing_required():
    fp = {"schema_version": "0.1.0"}
    errors = validate_fingerprint_structure(fp)
    assert len(errors) > 5  # many missing fields


def test_validate_invalid_category():
    fp = {
        "schema_version": "0.1.0",
        "profile_name": "test",
        "desktop": {"wm": "sway", "theme": "nord", "icon_theme": "tela"},
        "terminal": {"shell": "fish", "font": "mono"},
        "keyboard": {"layout": "dvorak"},
        "packages": {"categories": ["nonexistent-category"]},
        "security": {"paranoia_level": "paranoid"},
        "network": {},
    }
    errors = validate_fingerprint_structure(fp)
    assert any("category" in e for e in errors)


def test_validate_invalid_schema_version():
    fp = {
        "schema_version": "9.9.9",
        "profile_name": "test",
        "desktop": {"wm": "none", "theme": "adwaita", "icon_theme": "adwaita"},
        "terminal": {"shell": "bash", "font": "mono"},
        "keyboard": {"layout": "us"},
        "packages": {"categories": ["development"]},
        "security": {"paranoia_level": "minimal"},
        "network": {},
    }
    errors = validate_fingerprint_structure(fp)
    assert any("schema_version" in e for e in errors)


def test_tier_classify_t0():
    code = "# Just a comment\n{ }"
    assert classify_tier(code) == Tier.T0_READONLY


def test_tier_classify_t1():
    code = "home-manager.users.bob = { programs.zsh.enable = true; };"
    assert classify_tier(code) == Tier.T1_USERSPACE


def test_tier_classify_t2():
    code = "{ config, pkgs, ... }: { networking.hostName = \"foo\"; }"
    assert classify_tier(code) == Tier.T2_SYSTEM


def test_tier_classify_t3():
    code = "mkfs.ext4 /dev/sda1"
    assert classify_tier(code) == Tier.T3_DESTRUCTIVE


def test_tier_classify_wipe():
    code = "shred -vfz -n 5 /dev/sdb"
    assert classify_tier(code) == Tier.T3_DESTRUCTIVE


def test_validate_ai_output_valid():
    fp = {
        "schema_version": "0.1.0",
        "profile_name": "test",
        "desktop": {"wm": "hyprland", "theme": "nord", "icon_theme": "papirus"},
        "terminal": {"shell": "zsh", "font": "mono"},
        "keyboard": {"layout": "us"},
        "packages": {"categories": ["development"]},
        "security": {"paranoia_level": "standard"},
        "network": {},
    }
    result = validate_ai_output(fp)
    assert result["valid"] is True
    assert result["errors"] == []
    assert "tier" in result


def test_validate_ai_output_invalid():
    fp = {"schema_version": "0.1.0"}
    result = validate_ai_output(fp)
    assert result["valid"] is False
    assert len(result["errors"]) > 0


# ===========================================================================
# Sandbox Tests
# ===========================================================================

def test_bwrap_available_returns_bool():
    result = is_bwrap_available()
    assert isinstance(result, bool)


def test_snapshot_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        (td / "file1.txt").write_text("hello")
        (td / "subdir").mkdir()
        (td / "subdir" / "file2.txt").write_text("world")

        snap = _snapshot_dir(td)
        assert "file1.txt" in snap
        assert "subdir/file2.txt" in snap


def test_diff_snapshots():
    before = {"a.txt": "100:10", "b.txt": "200:20"}
    after = {"a.txt": "100:10", "b.txt": "300:30", "c.txt": "400:40"}
    diff = _diff_snapshots(before, after)
    assert "b.txt" in diff  # modified
    assert "c.txt" in diff  # new
    assert "a.txt" not in diff  # unchanged


def test_dry_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        script = td / "test.sh"
        script.write_text("#!/bin/sh\necho hello\n")

        result = _dry_run(script, td, "/bin/sh", None, None)
        assert result.dry_run is True
        assert result.success is True
        assert "DRY RUN" in result.stderr


def test_run_sandboxed_missing_script():
    result = run_sandboxed("/nonexistent/script.sh", "/tmp")
    assert result.success is False
    assert "not found" in result.stderr.lower()


def test_run_sandboxed_dry_run():
    """On Windows (no bwrap), this should produce a dry-run result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        script = td / "test.sh"
        script.write_text("#!/bin/sh\necho hello from sandbox\n")

        result = run_sandboxed(script, td)
        # On Windows, bwrap is not available → dry run
        if not is_bwrap_available():
            assert result.dry_run is True
        # Either way, it shouldn't crash
        assert isinstance(result, SandboxResult)


# ===========================================================================
# Main runner
# ===========================================================================

if __name__ == "__main__":
    tests = [
        # Privacy Shield
        ("scrub_email", test_scrub_email),
        ("scrub_ipv4", test_scrub_ipv4),
        ("scrub_unix_home", test_scrub_unix_home),
        ("scrub_windows_home", test_scrub_windows_home),
        ("scrub_ssh_key", test_scrub_ssh_key),
        ("scrub_gpg_key", test_scrub_gpg_key),
        ("scrub_preserves_enums", test_scrub_preserves_enums),
        ("scrub_json_nested", test_scrub_json_nested),
        ("restore_roundtrip", test_restore_roundtrip),
        ("restore_json_roundtrip", test_restore_json_roundtrip),
        ("idempotent_scrub", test_idempotent_scrub),
        # AI Validator
        ("validate_valid_fingerprint", test_validate_valid_fingerprint),
        ("validate_invalid_wm", test_validate_invalid_wm),
        ("validate_missing_required", test_validate_missing_required),
        ("validate_invalid_category", test_validate_invalid_category),
        ("validate_invalid_schema_version", test_validate_invalid_schema_version),
        ("tier_classify_t0", test_tier_classify_t0),
        ("tier_classify_t1", test_tier_classify_t1),
        ("tier_classify_t2", test_tier_classify_t2),
        ("tier_classify_t3", test_tier_classify_t3),
        ("tier_classify_wipe", test_tier_classify_wipe),
        ("validate_ai_output_valid", test_validate_ai_output_valid),
        ("validate_ai_output_invalid", test_validate_ai_output_invalid),
        # Sandbox
        ("bwrap_available_returns_bool", test_bwrap_available_returns_bool),
        ("snapshot_dir", test_snapshot_dir),
        ("diff_snapshots", test_diff_snapshots),
        ("dry_run", test_dry_run),
        ("run_sandboxed_missing_script", test_run_sandboxed_missing_script),
        ("run_sandboxed_dry_run", test_run_sandboxed_dry_run),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} tests passed")
    sys.exit(0 if failed == 0 else 1)
