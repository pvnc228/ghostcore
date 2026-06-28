"""
GhostCore OS — Phase 1: Bubblewrap Sandbox

Wrapper around `bwrap` for executing user-level (T1) scripts in isolation.
Runs the script in a minimal environment with:
  - No network access (--unshare-net)
  - New PID/IPC/UTS namespaces (--unshare-all)
  - Read-only host mounts (except the designated workdir)
  - Optional overlay filesystem for safe file modification

If bwrap is not available (e.g. on Windows), the sandbox degrades gracefully
to a dry-run mode that logs what would have been executed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SandboxResult:
    """Result of a sandboxed execution."""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    files_modified: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    dry_run: bool = False
    command: list[str] = field(default_factory=list)


def is_bwrap_available() -> bool:
    """Check if bubblewrap is installed and accessible."""
    return shutil.which("bwrap") is not None


def _build_bwrap_cmd(
    workdir: Path,
    script_path: Path,
    extra_ro_mounts: list[Path] | None = None,
    extra_rw_mounts: list[Path] | None = None,
) -> list[str]:
    """Build the bwrap command line."""
    cmd = [
        "bwrap",
        "--unshare-all",
        "--unshare-net",        # no network
        "--die-with-parent",    # clean up on parent exit
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--dir", "/run",
        "--dir", "/var",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/etc", "/etc",
        "--ro-bind", "/nix", "/nix",  # NixOS systems
        "--bind", str(workdir), str(workdir),  # workdir is RW
    ]

    # Extra read-only mounts
    for mount in (extra_ro_mounts or []):
        cmd.extend(["--ro-bind", str(mount), str(mount)])

    # Extra read-write mounts
    for mount in (extra_rw_mounts or []):
        cmd.extend(["--bind", str(mount), str(mount)])

    # The script itself must be readable
    cmd.extend(["--ro-bind", str(script_path), str(script_path)])

    return cmd


def run_sandboxed(
    script_path: str | Path,
    workdir: str | Path,
    args: list[str] | None = None,
    extra_ro_mounts: list[Path] | None = None,
    extra_rw_mounts: list[Path] | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> SandboxResult:
    """
    Run a script inside a bubblewrap sandbox.

    Args:
        script_path: Path to the script to execute
        workdir: Directory the script can write to (RW)
        args: Additional arguments to pass to the script
        extra_ro_mounts: Additional read-only bind mounts
        extra_rw_mounts: Additional read-write bind mounts
        timeout: Maximum execution time in seconds
        env: Environment variables to set inside the sandbox

    Returns:
        SandboxResult with execution details
    """
    script_path = Path(script_path).resolve()
    workdir = Path(workdir).resolve()

    if not script_path.exists():
        return SandboxResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=f"Script not found: {script_path}",
            command=[],
        )

    # Determine the interpreter
    interpreter = _detect_interpreter(script_path)

    if not is_bwrap_available():
        # Dry-run mode: just log what would happen
        return _dry_run(script_path, workdir, interpreter, args, env)

    bwrap_cmd = _build_bwrap_cmd(workdir, script_path, extra_ro_mounts, extra_rw_mounts)
    full_cmd = bwrap_cmd + [interpreter, str(script_path)] + (args or [])

    # Snapshot workdir before execution for diff
    files_before = _snapshot_dir(workdir)

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
            cwd=str(workdir),
        )

        # Snapshot after
        files_after = _snapshot_dir(workdir)
        modified = _diff_snapshots(files_before, files_after)

        return SandboxResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            files_modified=modified,
            command=full_cmd,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=f"Script timed out after {timeout}s",
            command=full_cmd,
        )
    except Exception as e:
        return SandboxResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=f"Sandbox error: {e}",
            command=full_cmd,
        )


def _detect_interpreter(script_path: Path) -> str:
    """Detect the interpreter from the shebang line."""
    try:
        first_line = script_path.read_text().splitlines()[0]
        if first_line.startswith("#!"):
            shebang = first_line[2:].strip()
            # Extract the binary path
            return shebang.split()[0]
    except (IndexError, OSError):
        pass
    return "/bin/sh"


def _snapshot_dir(directory: Path) -> dict[str, str]:
    """Snapshot all files in a directory with their modification times."""
    snapshot: dict[str, str] = {}
    if not directory.exists():
        return snapshot
    for path in directory.rglob("*"):
        if path.is_file():
            try:
                stat = path.stat()
                # Normalize to forward slashes for cross-platform consistency
                key = path.relative_to(directory).as_posix()
                snapshot[key] = f"{stat.st_mtime}:{stat.st_size}"
            except OSError:
                pass
    return snapshot


def _diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Find files that were created or modified between snapshots."""
    modified: list[str] = []
    for path, meta in after.items():
        if path not in before or before[path] != meta:
            modified.append(path)
    return sorted(modified)


def _dry_run(
    script_path: Path,
    workdir: Path,
    interpreter: str,
    args: list[str] | None,
    env: dict[str, str] | None,
) -> SandboxResult:
    """Dry-run mode when bwrap is not available."""
    cmd = [interpreter, str(script_path)] + (args or [])
    return SandboxResult(
        success=True,
        returncode=0,
        stdout="",
        stderr=(
            f"[DRY RUN — bwrap not available] Would execute:\n"
            f"  interpreter: {interpreter}\n"
            f"  script: {script_path}\n"
            f"  workdir: {workdir}\n"
            f"  args: {args or []}\n"
            f"  env: {env or {}}\n"
        ),
        dry_run=True,
        command=cmd,
    )
