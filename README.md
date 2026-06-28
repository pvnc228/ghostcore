# GhostCore OS — Phase 0: Declarative Compiler Engine

> **AI as a compiler, not a co-author of chaos.**

Phase 0 proves the core concept: a local LLM fills a structured JSON
schema from free-form user input, and a deterministic Python engine
renders that JSON into a valid NixOS `configuration.nix`.

## Architecture

```
User Input (free text)
        │
        ▼
┌─────────────────────┐
│  Local LLM (7B)     │  ← Qwen2.5-Coder-7B (runs on NixOS host)
│  + prompt template  │     See: src/prompt.py
└────────┬────────────┘
         │ JSON (UX Fingerprint)
         ▼
┌─────────────────────┐
│  Schema Validator   │  ← jsonschema (Draft 2020-12)
│  schemas/           │     See: schemas/ux_fingerprint.json
│  ux_fingerprint.json│
└────────┬────────────┘
         │ Validated dict
         ▼
┌─────────────────────┐
│  Jinja2 Renderer    │  ← src/compiler.py
│  + package resolver │     See: src/packages.py
│  templates/         │     See: templates/configuration.nix.j2
│  configuration.nix  │
│  .j2                │
└────────┬────────────┘
         │ Nix code (string)
         ▼
┌─────────────────────┐
│  nix-instantiate    │  ← syntax check (--parse only, no build)
│  --parse            │
└────────┬────────────┘
         │ Valid NixOS configuration.nix
         ▼
    nixos-rebuild switch
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Compile a UX Fingerprint into a NixOS configuration
python -m src.compiler examples/dev-station.json configuration.nix

# Run tests
python tests/test_pipeline.py
```

## Project Structure

```
ghostcore/
├── schemas/
│   └── ux_fingerprint.json      # JSON Schema (Draft 2020-12)
├── templates/
│   └── configuration.nix.j2     # Jinja2 → NixOS config template
├── src/
│   ├── __init__.py
│   ├── compiler.py              # Validation + rendering + nix check
│   ├── prompt.py                # LLM prompt template (system + user)
│   └── packages.py              # Category → Nixpkgs name mapping
├── examples/
│   ├── dev-station.json         # Sample: full dev setup with Hyprland
│   └── minimalist.json          # Sample: minimal hardened server
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py         # 7 tests (schema, rendering, CLI)
├── requirements.txt
└── .gitignore
```

## UX Fingerprint Schema

The schema defines everything the system needs to generate a complete
NixOS configuration. Key sections:

| Section      | Purpose                                          |
|-------------|--------------------------------------------------|
| `desktop`   | WM/DE, theme, icons, browser, terminal emulator  |
| `terminal`  | Shell, font, font size                           |
| `keyboard`  | Layout, variant, caps-as-ctrl                    |
| `packages`  | Category-based + explicit allowlist/blocklist    |
| `security`  | Paranoia level (minimal → hardened), firewall    |
| `network`   | Hostname, bluetooth, VPN, timezone, locale       |
| `git`       | Username, email, GPG signing key                 |

All fields use strict enums and regex patterns — the LLM can only
choose from predefined options, never invent values.

## Phase 0 Verification Checklist

- [x] JSON Schema with strict enums and validation
- [x] Prompt template for Qwen2.5-Coder-7B
- [x] Jinja2 template → valid NixOS configuration.nix
- [x] Package category → Nixpkgs name resolver
- [x] Schema validation (jsonschema Draft 2020-12)
- [x] nix-instantiate --parse integration (runs on NixOS)
- [x] CLI: `python -m src.compiler input.json output.nix`
- [x] 7/7 automated tests passing
- [x] Two example profiles (dev-station, minimalist)

## Next: Phase 1

- Privacy Shield (PII scrubbing before API calls)
- Bubblewrap sandbox for T1 scripts
- End-to-end test with actual local model on NixOS

## License

MIT
