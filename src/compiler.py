"""
GhostCore OS — Phase 0: Declarative Compiler Engine

Takes a validated UX Fingerprint JSON and renders it into a
syntactically valid NixOS configuration.nix using Jinja2 templates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from packages import (
    BROWSER_PACKAGES,
    ICON_PACKAGES,
    SHELL_PACKAGES,
    TERMINAL_PACKAGES,
    THEME_PACKAGES,
    WM_PACKAGES,
    resolve_packages,
)

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "ux_fingerprint.json"
TEMPLATES_DIR = ROOT / "templates"


# ── validation ───────────────────────────────────────────────────────────────
def load_schema() -> dict:
    """Load and return the UX Fingerprint JSON Schema."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_fingerprint(fingerprint: dict) -> list[str]:
    """
    Validate a UX Fingerprint dict against the JSON Schema.
    Returns a list of human-readable error strings (empty = valid).
    """
    schema = load_schema()
    errors: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(fingerprint), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"[{path}] {err.message}")
    return errors


# ── computed template variables ──────────────────────────────────────────────
def _compute_template_vars(fingerprint: dict) -> dict:
    """
    Derive package lists and other computed values from the fingerprint
    so the Jinja2 template can stay declarative.
    """
    desktop = fingerprint.get("desktop", {})
    packages = fingerprint.get("packages", {})
    security = fingerprint.get("security", {})

    # Resolve category packages
    category_pkgs = resolve_packages(packages.get("categories", []))

    # WM packages
    wm = desktop.get("wm", "none")
    wm_pkgs = WM_PACKAGES.get(wm, [])

    # Theme packages
    theme = desktop.get("theme", "adwaita")
    theme_pkgs = THEME_PACKAGES.get(theme, [])

    # Icon theme packages
    icon_theme = desktop.get("icon_theme", "adwaita")
    icon_pkgs = ICON_PACKAGES.get(icon_theme, [])

    # Browser
    browser = desktop.get("browser")
    browser_pkg = BROWSER_PACKAGES.get(browser) if browser else None

    # Terminal
    terminal_emulator = desktop.get("terminal")
    terminal_pkg = TERMINAL_PACKAGES.get(terminal_emulator) if terminal_emulator else None

    # Security tier (for template logic)
    paranoia = security.get("paranoia_level", "standard")

    return {
        "_category_packages": category_pkgs,
        "_wm_packages": wm_pkgs,
        "_theme_packages": theme_pkgs,
        "_icon_packages": icon_pkgs,
        "_browser_package": browser_pkg,
        "_terminal_package": terminal_pkg,
        "_paranoia_level": paranoia,
    }


# ── template rendering ───────────────────────────────────────────────────────
def render_nix(fingerprint: dict) -> str:
    """
    Render a validated UX Fingerprint into a NixOS configuration.nix string.
    Raises ValueError if the fingerprint fails schema validation.
    """
    errors = validate_fingerprint(fingerprint)
    if errors:
        raise ValueError("Invalid UX Fingerprint:\n" + "\n".join(f"  ✗ {e}" for e in errors))

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("configuration.nix.j2")

    # Merge fingerprint data with computed template variables
    context = {**fingerprint, **_compute_template_vars(fingerprint)}
    return template.render(**context)


# ── nix syntax check ────────────────────────────────────────────────────────
def check_nix_syntax(nix_code: str) -> tuple[bool, str]:
    """
    Run `nix-instantiate --parse` on the generated Nix code.
    Returns (ok, message). If nix is not installed, returns (True, "nix not available, skipped").
    """
    try:
        proc = subprocess.run(
            ["nix-instantiate", "--parse", "-"],
            input=nix_code,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, "nix-instantiate --parse: OK"
        return False, f"nix-instantiate error:\n{proc.stderr.strip()}"
    except FileNotFoundError:
        return True, "nix not installed — syntax check skipped (install Nix to enable)"
    except subprocess.TimeoutExpired:
        return False, "nix-instantiate timed out"


# ── CLI entry point ─────────────────────────────────────────────────────────
def main() -> None:
    """CLI: ghostcore-compile <fingerprint.json> [output.nix]"""
    if len(sys.argv) < 2:
        print("Usage: ghostcore-compile <fingerprint.json> [output.nix]")
        print("       If output is omitted, prints to stdout.")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    with open(input_path, "r", encoding="utf-8") as f:
        fingerprint = json.load(f)

    nix_code = render_nix(fingerprint)

    ok, msg = check_nix_syntax(nix_code)
    print(f"[ghostcore] {msg}", file=sys.stderr)

    if output_path:
        output_path.write_text(nix_code, encoding="utf-8")
        print(f"[ghostcore] Wrote {output_path}", file=sys.stderr)
    else:
        print(nix_code)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
