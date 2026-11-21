"""Native Windows EXE first-use smoke; no source files or Store state changed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from pywinauto import Desktop

exe = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert source == os.environ["EXPECTED_SOURCE_SHA"], "Not an exact raw source checkout"
assert exe.is_file(), "Native EXE missing"
receipt = {
    "source_sha": source,
    "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
    "exe_name": exe.name,
    "steps": [],
    "result": "FAIL",
}
proc = None
try:
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    window = Desktop(backend="uia").window(title_re=".*File Integrity Ledger.*")
    window.wait("visible", timeout=45)
    window.set_focus()
    time.sleep(1)
    assert proc.poll() is None, "EXE exited before first-use capture"
    rect = window.rectangle()
    assert rect.width() >= 850 and rect.height() >= 620, "Unexpected GUI geometry"
    receipt["window_rectangle"] = [rect.left, rect.top, rect.right, rect.bottom]
    receipt["window_title"] = window.window_text()
    window.capture_as_image().save(out / "01-first-use.png")
    assert (out / "01-first-use.png").stat().st_size > 1000
    receipt["steps"].append("native_exe_first_use_visible_and_screenshot_saved")
    # No automatic file selection or dialog acceptance: read-only first-use check.
    window.close()
    proc.wait(timeout=15)
    assert proc.returncode == 0, f"Native EXE exit code {proc.returncode}"
    receipt["steps"].append("native_normal_exit")
    receipt["visual_review_required"] = True
    receipt["result"] = "PASS"
except BaseException as exc:
    receipt["error"] = str(exc)
    (out / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
    if proc is not None and proc.poll() is None:
        try:
            window.capture_as_image().save(out / "failure-window.png")
        except Exception:
            pass
    raise
finally:
    if proc is not None and proc.poll() is None:
        proc.kill()
        proc.wait(timeout=10)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False))
