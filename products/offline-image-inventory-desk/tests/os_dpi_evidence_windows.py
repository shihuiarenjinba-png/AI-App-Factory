"""Conservative real-Windows OS DPI gate for the exact unsigned review EXE.

No display-setting changes, Tk-scaling substitutions, or human QA claims.
Hosted runners at 100% yield OS_DPI_NOT_PROVEN_HOLD, never a false pass.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path


def dpi_gate(target_percent, system_dpi, monitor_dpi, per_monitor_aware):
    """Both independent Windows DPI observations must match exactly."""
    if target_percent not in (125, 150):
        raise ValueError("Unsupported display scale")
    expected = {125: 120, 150: 144}[target_percent]
    return (per_monitor_aware is True and type(system_dpi) is int
            and type(monitor_dpi) is int
            and system_dpi == expected and monitor_dpi == expected)


def os_dpi_observation():
    if os.name != "nt":
        raise OSError("Windows OS DPI evidence requires Windows")
    from ctypes import wintypes

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    # Must precede Tk/PIL/UI automation imports to avoid virtualized DPI.
    aware = bool(user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)))
    awareness_error = ctypes.get_last_error() if not aware else 0
    user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    monitor = user32.MonitorFromPoint(POINT(1, 1), 2)
    if not monitor:
        raise OSError("Primary monitor not available")
    shcore.GetDpiForMonitor.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                       ctypes.POINTER(ctypes.c_uint),
                                       ctypes.POINTER(ctypes.c_uint)]
    shcore.GetDpiForMonitor.restype = ctypes.c_long
    x, y = ctypes.c_uint(), ctypes.c_uint()
    status = shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(x), ctypes.byref(y))
    if status != 0:
        raise OSError("GetDpiForMonitor failed: %s" % status)
    user32.GetDpiForSystem.restype = ctypes.c_uint
    return {"system_dpi": int(user32.GetDpiForSystem()),
            "monitor_dpi_x": int(x.value), "monitor_dpi_y": int(y.value),
            "per_monitor_v2_aware": aware, "awareness_error": awareness_error,
            "measurement": "GetDpiForSystem + GetDpiForMonitor(MDT_EFFECTIVE_DPI)",
            "not_tk_scaling": True}


def run(exe, receipt_path, out, source_sha, calibration):
    out.mkdir(parents=True, exist_ok=True)
    exe_bytes = exe.read_bytes()
    digest = hashlib.sha256(exe_bytes).hexdigest()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if (receipt.get("source_sha") != source_sha or receipt.get("sha256") != digest
            or receipt.get("bytes") != len(exe_bytes)
            or receipt.get("stage") != "REVIEW_ONLY_UNSIGNED_EXE"
            or receipt.get("market_fit") != "MARKET_FIT_HOLD"):
        raise ValueError("EXACT_UNSIGNED_EXE_PROVENANCE_MISMATCH")
    try:
        observation = os_dpi_observation()
        measurement_error = None
    except (OSError, AttributeError, ctypes.ArgumentError) as exc:
        observation = None
        measurement_error = str(exc)
    results = {}
    for target in (125, 150):
        expected = {125: 120, 150: 144}[target]
        measured = (observation is not None
                    and dpi_gate(target, observation["system_dpi"],
                                 observation["monitor_dpi_x"],
                                 observation["per_monitor_v2_aware"])
                    and observation["monitor_dpi_y"] == expected)
        record = {"target_percent": target, "actual_os_dpi_proven": bool(measured),
                  "status": "OS_DPI_NOT_PROVEN_HOLD", "packaged_gui_e2e": False}
        if measured:
            # Same Windows session: source calibration and packaged EXE both
            # run at measured OS DPI, not at a synthetic Tk text multiplier.
            from gui_smoke_windows import run_packaged
            target_dir = out / ("real-os-dpi-%s" % target)
            run_packaged(target_dir, exe, source_sha, calibration)
            replay = json.loads((target_dir / "packaged-exe-e2e-receipt.json").read_text(encoding="utf-8"))
            if (replay.get("exe_sha256") != digest
                    or replay.get("source_sha") != source_sha
                    or replay.get("read_denied_fail_closed") is not True
                    or replay.get("client_html_sha256") is None):
                raise ValueError("REAL_OS_DPI_EXACT_EXE_E2E_MISMATCH")
            record.update(status="CLOUD_REAL_OS_DPI_GUI_E2E_PASS_NOT_LOCAL_NOT_HUMAN",
                          packaged_gui_e2e=True)
        results[str(target)] = record
    result = {"classification": "CLOUD_WINDOWS_OS_DPI_EVIDENCE_NOT_LOCAL_NOT_HUMAN",
              "source_sha": source_sha, "exe_sha256": digest,
              "observation": observation, "measurement_error": measurement_error,
              "targets": results,
              "os_dpi_125_150_both_proven": all(x["packaged_gui_e2e"] for x in results.values()),
              "human_buyers_observed": 0, "market_score": 64,
              "why_pay_verified": False, "market_fit": "MARKET_FIT_HOLD",
              "not_local_gui_pass": True, "not_msix": True}
    (out / "os-dpi-gate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--exe-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows-only OS DPI evidence")
    run(args.exe.resolve(), args.exe_receipt.resolve(), args.out.resolve(),
        args.source_sha, args.calibration.resolve())
