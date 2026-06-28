# GhostCore OS

> **AI as a compiler, not a co-author of chaos.**

GhostCore OS is an intelligent translator that converts natural-language
descriptions of your ideal Linux desktop into a valid, reproducible
NixOS configuration. You describe what you want in plain language; a
local LLM turns that into a structured JSON profile; a deterministic
Python engine renders that JSON into a `configuration.nix` that NixOS
can apply directly.

The AI is **ephemeral** — it runs only during the design session, then
unloads. Your system is left with a clean, immutable, declarative
config that has no hidden state or background agents.

---

## What Problem Does This Solve?

Setting up a NixOS system means writing Nix expressions by hand. Most
people don't want to learn Nix syntax just to pick a desktop theme,
terminal emulator, and set of packages. GhostCore bridges that gap:

1. You say *"I want a Hyprland desktop with Catppuccin theme, Firefox,
   Alacritty, and ZSH with JetBrains Mono"*
2. The local LLM fills a structured JSON profile (validated by a strict
   schema)
3. A Jinja2 template renders that JSON into a complete
   `configuration.nix`
4. You run `nixos-rebuild switch` and your system is configured

No Bash scripts. No imperative mutations. No AI running in the
background.

---

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

### Key Design Principles

| Principle | What it means |
|-----------|---------------|
| **Declarative, not imperative** | The AI never generates executable code for the system level. It generates *state* — JSON that a deterministic engine turns into Nix configs. |
| **Structured UX Fingerprint** | The user profile is a strictly validated JSON Schema document. The LLM fills in predefined fields; it never invents structure. |
| **Ephemeral AI** | The LLM runs only during the design session. After the manifest is saved, models unload. No background AI processes. |
| **Tiered safety** | Operations are classified T0–T3 by risk. T0 (themes, dotfiles) is unrestricted. T3 (disk partitioning, bootloader) is blocked entirely. |

---

## Quick Start

### Prerequisites

- Python 3.11+
- NixOS (for full `nixos-rebuild` support)
- A local LLM (Qwen2.5-Coder-7B recommended) or API access

### Install

```bash
git clone https://github.com/pvnc228/ghostcore.git
cd ghostcore
pip install -r requirements.txt
```

### Compile a Profile

```bash
# Compile an example profile to NixOS config
PYTHONPATH=src python -m compiler examples/dev-station.json configuration.nix

# Check the output
cat configuration.nix

# On NixOS: apply it
sudo nixos-rebuild switch
```

### Run Tests

```bash
python tests/test_pipeline.py
```

### Generate a Profile from Natural Language

Use the prompt template with your local LLM:

```python
from src.prompt import build_prompt

system_prompt, user_prompt = build_prompt(
    "I want a minimal i3 setup with dark theme, Alacritty, and vim"
)

# Send (system_prompt, user_prompt) to your LLM
# Save the JSON output, then compile it
```

---

## Project Structure

```
ghostcore/
├── docs/
│   └── vision.md                 # Full project vision and roadmap
├── schemas/
│   └── ux_fingerprint.json       # JSON Schema (Draft 2020-12)
├── templates/
│   └── configuration.nix.j2      # Jinja2 → NixOS config template
├── src/
│   ├── __init__.py
│   ├── compiler.py               # Validation + rendering + nix check
│   ├── prompt.py                 # LLM prompt template (system + user)
│   └── packages.py               # Category → Nixpkgs name mapping
├── examples/
│   ├── dev-station.json          # Sample: full dev setup with Hyprland
│   └── minimalist.json           # Sample: minimal hardened server
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py          # 7 tests (schema, rendering, CLI)
├── requirements.txt
├── README.md
└── .gitignore
```

---

## UX Fingerprint Schema

The schema defines everything the system needs to generate a complete
NixOS configuration. Key sections:

| Section     | Purpose                                           |
|-------------|---------------------------------------------------|
| `desktop`   | WM/DE, theme, icons, browser, terminal emulator   |
| `terminal`  | Shell, font, font size                            |
| `keyboard`  | Layout, variant, caps-as-ctrl                     |
| `packages`  | Category-based + explicit allowlist/blocklist     |
| `security`  | Paranoia level (minimal → hardened), firewall     |
| `network`   | Hostname, bluetooth, VPN, timezone, locale        |
| `git`       | Username, email, GPG signing key                  |

All fields use strict enums and regex patterns — the LLM can only
choose from predefined options, never invent values.

### Example Profile

```json
{
  "schema_version": "0.1.0",
  "profile_name": "dev-station",
  "desktop": {
    "wm": "hyprland",
    "theme": "catppuccin-mocha",
    "icon_theme": "papirus",
    "browser": "firefox",
    "terminal": "alacritty"
  },
  "terminal": {
    "shell": "zsh",
    "font": "JetBrains Mono",
    "font_size": 12
  },
  "packages": {
    "categories": ["development", "system-tools", "communication"],
    "explicit_allowlist": ["docker", "kubectl"]
  },
  "security": {
    "paranoia_level": "standard",
    "enable_firewall": true,
    "full_disk_encryption": true
  }
}
```

---

## Safety Model

| Tier | Scope | How it works |
|------|-------|--------------|
| **T0** | User declarative (themes, dotfiles, aliases) | Applied via symlinks in home directory. Zero risk of breaking the system. |
| **T1** | User imperative (systemd services, flatpacks) | Run in `bubblewrap` sandbox with isolated `$HOME`. |
| **T2** | System declarative (system packages, network) | AI generates Nix files only. Applied via `nixos-rebuild switch`. |
| **T3** | Core/hardware (disk, bootloader, firmware) | **Blocked.** AI can only output a text recommendation. |

---

## Roadmap

### Phase 0 — Declarative Compiler Engine (current)
- [x] JSON Schema with strict enums and validation
- [x] Prompt template for Qwen2.5-Coder-7B
- [x] Jinja2 template → valid NixOS configuration.nix
- [x] Package category → Nixpkgs name resolver
- [x] Schema validation (jsonschema Draft 2020-12)
- [x] nix-instantiate --parse integration
- [x] CLI: `python -m src.compiler input.json output.nix`
- [x] 7/7 automated tests passing
- [x] Two example profiles (dev-station, minimalist)

### Phase 1 — Privacy & Verification
- [ ] Privacy Shield (PII scrubbing before API calls)
- [ ] Bubblewrap sandbox for T1 scripts
- [ ] End-to-end test with actual local model on NixOS

### Phase 2 — LangGraph Dialogue
- [ ] State machine: Interview → Fingerprint → Compile → Verify → Review → Apply

### Phase 3 — TUI
- [ ] Async Textual interface with chat + live diff preview

### Phase 4 — System Integration
- [ ] Manifest writer (`~/.config/ghostcore/manifest.json`)
- [ ] Atomic NixOS generation switching
- [ ] Auto-rollback daemon

### Phase 5 — Open Source Launch
- [ ] 50 destructive scenario tests
- [ ] CONTRIBUTING.md, demo GIFs

---

## License

MIT
