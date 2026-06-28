# GhostCore OS — Development Progress & Roadmap

> Living document tracking what's done, what's in progress, and what's next.

---

## Phase 0 — Declarative Compiler Engine ✅ COMPLETED

**Goal:** Prove the core concept — natural language → validated JSON → NixOS config works.

### What was done:

- [x] JSON Schema `schemas/ux_fingerprint.json` — strict enums, regex patterns, all required fields defined
- [x] Prompt template `src/prompt.py` — system + user prompts for Qwen2.5-Coder-7B to produce schema-valid JSON
- [x] Package resolver `src/packages.py` — category → Nixpkg name mapping (deduplicated, sorted)
- [x] Jinja2 template `templates/configuration.nix.j2` — renders a full `configuration.nix`
- [x] Compiler engine `src/compiler.py` — schema validation via jsonschema (Draft 2020-12), template rendering, `nix-instantiate --parse` syntax check, CLI entry point
- [x] Two example profiles — `examples/dev-station.json` (Hyprland, Catppuccin, dev tools) and `examples/minimalist.json` (hardened, minimal)
- [x] Test suite `tests/test_pipeline.py` — 7 tests: valid fingerprint, invalid enum, missing required field, render dev-station, render minimalist, nix syntax check, invalid fingerprint raises ValueError
- [x] README.md — architecture diagram, quick start, project structure, safety model
- [x] requirements.txt — jsonschema, jinja2

### How to run:
```bash
PYTHONPATH=src python -m compiler examples/dev-station.json output.nix
python tests/test_pipeline.py
```

---

## Phase 1 — Privacy & Verification 🔨 IN PROGRESS

**Goal:** Add a privacy shield (PII scrubbing) and make the verification pipeline airtight before any LLM output touches the system.

### Tasks:

- [x] **Privacy Shield** (`src/privacy_shield.py`)
  - Regex-based local parser that strips PII before any API call
  - Scrubs: file paths (`/home/user/...`, `C:\Users\...`), IP addresses (v4/v6), SSH keys, emails, GPG key IDs, hostnames, hex/base64 secrets
  - Replaces with placeholders like `<EMAIL_1>`, `<IP_1>`, `<SSH_KEY_1>`
  - Supports restore (output mapping) so final config gets real values back
  - Idempotent — scrubbing already-scrubbed text is a no-op
  - Preserves enum values (adwaita, us, bash, etc.)
  - 11 tests passing

- [x] **Incoming AI Code Validator** (`src/ai_validator.py`)
  - Structural validation: required fields, types, enum ranges (mirrors JSON Schema)
  - Nix syntax check via `nix-instantiate --parse` (graceful skip if not installed)
  - Tier classification: T0 (readonly) → T3 (destructive) based on keyword analysis
  - Combined `validate_ai_output()` returns structured result dict
  - 11 tests passing

- [x] **Bubblewrap Sandbox** (`src/sandbox.py`)
  - Wrapper around `bwrap` for executing user-level (T1) scripts
  - `--unshare-all`, `--unshare-net`, `--die-with-parent`, read-only host mounts
  - File diff: snapshots workdir before/after to detect modifications
  - Dry-run mode when bwrap is not available (Windows/dev environments)
  - 6 tests passing

- [ ] **End-to-end test with actual local model on NixOS**
  - Run the full pipeline: user text → LLM → privacy shield → validator → compiler → nix check
  - Verify the output is a valid, applicable NixOS config

### Dependencies:
- Phase 0 complete ✅
- NixOS host for bubblewrap and nix-instantiate tests
- Local LLM (Qwen2.5-Coder-7B) or OpenRouter API for e2e test

---

## Phase 2 — LangGraph Dialogue Graph

**Goal:** Build the state machine that orchestrates the full conversation flow.

### Tasks:

- [ ] Define LangGraph state schema
- [ ] Node 1: Interview — collect user requirements
- [ ] Node 2: Fingerprint Generation — build UX Fingerprint JSON
- [ ] Node 3: Code Compilation — generate NixOS / Stow manifests
- [ ] Node 4: Verification Pipeline — schema + nix + tier check
- [ ] Node 5: Human Review — pause for user confirmation
- [ ] Node 6: System Apply — hand off to execution layer

---

## Phase 3 — TUI (Textual Interface)

**Goal:** Async terminal UI with chat + live diff preview.

### Tasks:

- [ ] Async Textual app skeleton
- [ ] Left panel: chat with streaming tokens + spinner
- [ ] Right panel: live diff of generated configs with syntax highlighting
- [ ] Modal warnings color-coded by tier (T0=green, T1=yellow, T2=orange, T3=red)

---

## Phase 4 — System Integration & Manifest

**Goal:** Make it actually apply configs and track state.

### Tasks:

- [ ] Manifest Writer — save to `~/.config/ghostcore/manifest.json`
- [ ] Atomic NixOS generation switching (`nixos-rebuild switch`)
- [ ] Auto-rollback daemon (detect failed services, auto-revert)

---

## Phase 5 — Open Source Launch

**Goal:** Polish, test, and publish.

### Tasks:

- [ ] 50 destructive scenario tests (AI jailbreaks, injection attempts)
- [ ] CONTRIBUTING.md, demo GIFs, polished README

---

## Notes & Decisions

- **2026-06-28:** Phase 0 verified complete. All 7 tests pass. Starting Phase 1.
- **2026-06-28:** Phase 1 modules implemented. 29/29 Phase 1 tests pass. 7/7 Phase 0 tests still pass.
- Architecture decision: AI never generates executable code — only JSON state. Deterministic engine handles all file generation.
- Target platform: NixOS (imperative mutations are forbidden at the system level).
- Privacy Shield runs entirely local — no PII ever leaves the device for LLM APIs.
- Sandbox degrades to dry-run on non-Linux platforms for development convenience.
