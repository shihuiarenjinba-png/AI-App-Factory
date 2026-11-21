"""Build a genuine Windows PE from a temporary committed QA fixture.

This fixture is NOT a commercial Factory product and must never be submitted
to Microsoft Store. It proves PyInstaller and EXE receipt work on Windows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from tools.build_windows_exe import build_exe


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        check=True, timeout=30,
    ).stdout.strip()


def smoke(output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="factory-windows-exe-smoke-") as tmp:
        root = Path(tmp)
        _git(root, "init", "-q", "-b", "codex/preidentity-qa-fixture")
        _git(root, "config", "user.name", "Factory QA")
        _git(root, "config", "user.email", "factory-qa@example.invalid")
        (root / "factory").mkdir()
        (root / "factory/config.json").write_text('{"kind":"app"}', encoding="utf-8")
        (root / "proposals").mkdir()
        (root / "proposals/qa-smoke-tool.json").write_text(
            '{"slug":"qa-smoke-tool","title":"Windows EXE Build QA Fixture"}', encoding="utf-8")
        product = root / "products" / "qa-smoke-tool"
        (product / "tests").mkdir(parents=True)
        (product / "manifest.json").write_text(
            '{"kind":"app","slug":"qa-smoke-tool","entry":"main.py"}', encoding="utf-8")
        (product / "main.py").write_text(
            'import tkinter as tk\n'
            'window = tk.Tk()\n'
            'window.title("Build QA fixture - not for sale")\n'
            'tk.Label(window, text="Pre-Identity EXE QA only").pack(padx=20, pady=20)\n'
            'window.mainloop()\n', encoding="utf-8")
        (product / "tests/test_smoke.py").write_text(
            'def test_smoke(): assert 2 + 2 == 4\n', encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "fixture: offline Windows GUI packaging smoke")
        sha = _git(root, "rev-parse", "HEAD")
        result = build_exe(root, "qa-smoke-tool", sha, output)
    executable = output / result["executable"]
    if not executable.is_file() or executable.read_bytes()[:2] != b"MZ":
        raise ValueError("real Windows PE artifact missing")
    if hashlib.sha256(executable.read_bytes()).hexdigest() != result["executable_sha256"]:
        raise ValueError("real Windows PE artifact checksum mismatch")
    if json.loads((output / "exe-receipt.json").read_text(encoding="utf-8")) != result:
        raise ValueError("EXE receipt mismatch")
    print("WINDOWS_EXE_SMOKE_BUILT_QA_ONLY", result["executable_sha256"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    smoke(args.output)
