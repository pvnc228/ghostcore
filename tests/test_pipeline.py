"""
GhostCore OS — Phase 0: Test suite

Runs in two modes:
  - MOCK mode (default on Windows/no-nix): validates pipeline logic with sample JSON
  - REAL mode (on NixOS): also runs nix-instantiate --parse on generated output

Usage:
  python -m pytest tests/ -v
  python tests/test_pipeline.py        # direct run, prints results
"""

import json
import sys
from pathlib import Path

# Add src/ to path so we can import without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compiler import check_nix_syntax, render_nix, validate_fingerprint


def test_validate_valid_fingerprint():
    """A well-formed fingerprint should produce zero validation errors."""
    fp = json.loads((Path(__file__).parent.parent / "examples" / "dev-station.json").read_text())
    errors = validate_fingerprint(fp)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_validate_invalid_fingerprint():
    """A fingerprint with invalid enum values should produce errors."""
    fp = {
        "schema_version": "0.1.0",
        "profile_name": "test",
        "desktop": {
            "wm": "invalid-wm-that-does-not-exist",
            "theme": "adwaita",
            "icon_theme": "adwaita"
        },
        "terminal": {"shell": "bash", "font": "mono"},
        "keyboard": {"layout": "us"},
        "packages": {"categories": ["development"]},
        "security": {"paranoia_level": "standard"},
    }
    errors = validate_fingerprint(fp)
    assert len(errors) > 0, "Expected validation errors for invalid WM"
    assert any("invalid-wm" in e or "desktop.wm" in e for e in errors)


def test_validate_missing_required_field():
    """Missing required fields should be caught."""
    fp = {
        "schema_version": "0.1.0",
        "profile_name": "test",
    }
    errors = validate_fingerprint(fp)
    assert len(errors) > 0


def test_render_dev_station():
    """Full pipeline: dev-station fingerprint → valid Nix code."""
    fp = json.loads((Path(__file__).parent.parent / "examples" / "dev-station.json").read_text())
    nix_code = render_nix(fp)

    # Basic structural checks
    assert "{ config, pkgs, lib, ... }:" in nix_code
    assert 'networking.hostName = "ghost-dev"' in nix_code
    assert "programs.hyprland.enable = true" in nix_code
    assert "zsh" in nix_code
    assert "firefox" in nix_code
    assert "alacritty" in nix_code
    assert "tailscale" in nix_code
    assert "Europe/Kyiv" in nix_code
    # Category packages should be present
    assert "neovim" in nix_code
    assert "git" in nix_code
    assert "htop" in nix_code
    # Explicit allowlist
    assert "docker" in nix_code
    assert "kubectl" in nix_code


def test_render_minimalist():
    """Full pipeline: minimalist fingerprint → valid Nix code."""
    fp = json.loads((Path(__file__).parent.parent / "examples" / "minimalist.json").read_text())
    nix_code = render_nix(fp)

    assert "{ config, pkgs, lib, ... }:" in nix_code
    assert "lockKernelModules = true" in nix_code
    assert "forcePageTableIsolation = true" in nix_code
    # Should NOT have bluetooth
    assert "bluetooth.enable = true" not in nix_code
    # Should NOT have WM packages
    assert "hyprland" not in nix_code


def test_nix_syntax_check():
    """If nix-instantiate is available, verify the generated code parses."""
    fp = json.loads((Path(__file__).parent.parent / "examples" / "dev-station.json").read_text())
    nix_code = render_nix(fp)
    ok, msg = check_nix_syntax(nix_code)
    # This test is lenient — if nix isn't installed, it still passes
    if "not installed" in msg:
        print(f"  ⚠ {msg}")
        return
    assert ok, f"Nix syntax check failed: {msg}"


def test_invalid_fingerprint_raises():
    """render_nix should raise ValueError for invalid input."""
    fp = {"schema_version": "0.1.0", "profile_name": "x"}
    try:
        render_nix(fp)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid UX Fingerprint" in str(e)


if __name__ == "__main__":
    """Run all tests directly and print results."""
    tests = [
        ("validate_valid_fingerprint", test_validate_valid_fingerprint),
        ("validate_invalid_fingerprint", test_validate_invalid_fingerprint),
        ("validate_missing_required_field", test_validate_missing_required_field),
        ("render_dev_station", test_render_dev_station),
        ("render_minimalist", test_render_minimalist),
        ("nix_syntax_check", test_nix_syntax_check),
        ("invalid_fingerprint_raises", test_invalid_fingerprint_raises),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} tests passed")
    sys.exit(0 if failed == 0 else 1)
