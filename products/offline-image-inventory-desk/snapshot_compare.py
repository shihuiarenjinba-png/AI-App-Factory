"""Deterministic, read-only image delivery snapshot comparison; no source writes."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

EXTENSIONS={".png",".jpg",".jpeg",".gif",".bmp"}
MAX_IMAGES=200
MAX_JSON=2*1024*1024
FIELDS={"relative_path","format","width","height","bytes","sha256"}
COLUMNS=("relative_path","status","old_sha256","new_sha256","old_dimensions","new_dimensions","old_bytes","new_bytes")

def relative(value):
    if not isinstance(value,str) or not value or len(value)>4096 or "\\" in value or ":" in value:
        raise ValueError("Unsafe relative path")
    if PurePosixPath(value).is_absolute() or any(x in ("",".","..") for x in value.split("/")):
        raise ValueError("Unsafe relative path")
    return value

def same_stat(a,b):
    return (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns)

def full_hash(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0))
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=64*1024*1024:
            raise ValueError("Unsafe image file")
        digest=hashlib.sha256()
        with os.fdopen(fd,"rb",closefd=False) as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):
                digest.update(chunk)
        if not same_stat(before,os.fstat(fd)):
            raise ValueError("File changed during hashing")
        return digest.hexdigest(),before
    finally:
        os.close(fd)

def capture_folder(folder,inspector):
    root=Path(folder).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Select an accessible real folder")
    files,errors=[],[]
    def error(path,exc):
        try: rel=Path(path).relative_to(root).as_posix()
        except ValueError: rel="."
        errors.append({"relative_path":rel,"error":type(exc).__name__})
    def onerror(exc):error(exc.filename or root,exc)
    for current,dirs,names in os.walk(root,topdown=True,followlinks=False,onerror=onerror):
        dirs.sort()
        for name in list(dirs):
            p=Path(current)/name
            try:
                if p.is_symlink():
                    error(p,ValueError("Linked directory"));dirs.remove(name)
            except OSError as exc:
                error(p,exc);dirs.remove(name)
        for name in sorted(names):
            p=Path(current)/name
            if p.suffix.lower() not in EXTENSIONS:continue
            if len(files)+len(errors)>=MAX_IMAGES:
                raise ValueError("More than 200 images; choose a smaller folder")
            try:
                rel=relative(p.relative_to(root).as_posix())
                before=p.lstat()
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("Linked/nonregular image")
                item=inspector(p)
                digest,hashed=full_hash(p)
                if not same_stat(before,hashed) or not same_stat(hashed,p.lstat()):
                    raise ValueError("File changed during scan")
                files.append({"relative_path":rel,"format":item["format"],
                              "width":item["width"],"height":item["height"],
                              "bytes":item["bytes"],"sha256":digest})
            except (OSError,ValueError,KeyError,TypeError) as exc:error(p,exc)
    files.sort(key=lambda r:r["relative_path"])
    errors.sort(key=lambda r:(r["relative_path"],r["error"]))
    return validate_snapshot({"schema":1,"root":str(root),"files":files,"errors":errors})

def validate_snapshot(value):
    if not isinstance(value,dict) or set(value)!={"schema","root","files","errors"} or type(value["schema"]) is not int or value["schema"]!=1:
        raise ValueError("Invalid snapshot schema")
    if not isinstance(value["root"],str) or not Path(value["root"]).is_absolute() or len(value["root"])>4096:
        raise ValueError("Invalid root")
    rows,errors=value["files"],value["errors"]
    if not isinstance(rows,list) or not isinstance(errors,list) or len(rows)+len(errors)>MAX_IMAGES:
        raise ValueError("Invalid item count")
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!=FIELDS:raise ValueError("Invalid image record")
        name=relative(row["relative_path"])
        if name in seen:raise ValueError("Duplicate relative path")
        seen.add(name)
        if row["format"] not in ("PNG","JPEG","GIF","BMP"):raise ValueError("Invalid format")
        if any(type(row[k]) is not int or not 1<=row[k]<=100000 for k in ("width","height")):
            raise ValueError("Invalid dimensions")
        if type(row["bytes"]) is not int or not 0<row["bytes"]<=64*1024*1024:
            raise ValueError("Invalid byte count")
        if not isinstance(row["sha256"],str) or re.fullmatch("[0-9a-f]{64}",row["sha256"]) is None:
            raise ValueError("Invalid SHA-256")
    for item in errors:
        if not isinstance(item,dict) or set(item)!={"relative_path","error"}:
            raise ValueError("Invalid error record")
        if item["relative_path"]!=".":relative(item["relative_path"])
        if not isinstance(item["error"],str) or not 1<=len(item["error"])<=80:
            raise ValueError("Invalid error code")
    if rows!=sorted(rows,key=lambda r:r["relative_path"]) or errors!=sorted(errors,key=lambda r:(r["relative_path"],r["error"])):
        raise ValueError("Unsorted evidence")
    return value

def compare_snapshots(old,new):
    validate_snapshot(old);validate_snapshot(new)
    if old["errors"] or new["errors"]:
        raise ValueError("Read/link errors: incomplete snapshots cannot prove removals")
    a={r["relative_path"]:r for r in old["files"]}
    b={r["relative_path"]:r for r in new["files"]}
    summary={k:0 for k in ("ADDED","REMOVED","MODIFIED","UNCHANGED")}
    changes=[]
    for name in sorted(set(a)|set(b)):
        x,y=a.get(name),b.get(name)
        status=("ADDED" if x is None else "REMOVED" if y is None else
                "MODIFIED" if any(x[k]!=y[k] for k in ("sha256","width","height","bytes","format")) else "UNCHANGED")
        summary[status]+=1
        changes.append({"relative_path":name,"status":status,
                        "old_sha256":x["sha256"] if x else "",
                        "new_sha256":y["sha256"] if y else "",
                        "old_dimensions":str(x["width"])+"x"+str(x["height"]) if x else "",
                        "new_dimensions":str(y["width"])+"x"+str(y["height"]) if y else "",
                        "old_bytes":x["bytes"] if x else "",
                        "new_bytes":y["bytes"] if y else ""})
    return {"schema":1,"old_root":old["root"],"new_root":new["root"],"summary":summary,"changes":changes}


def describe_scan_errors(errors, language="en", limit=5):
    """Explain incomplete scans in plain language without exposing exception internals."""
    if language not in ("en", "ja") or not isinstance(errors, list) or not 1 <= limit <= 20:
        raise ValueError("Invalid scan error request")
    reasons = {
        "PermissionError": ("Access denied. Check file permissions and retry.",
                            "読み取り権限がありません。アクセス権を確認して再試行してください。"),
        "FileNotFoundError": ("File disappeared. Check the folder and scan again.",
                              "ファイルが見つかりません。フォルダを確認して再実行してください。"),
        "ValueError": ("Invalid, linked, or changed image. Check the file and retry.",
                       "画像の形式・リンク・読み取り中の変更を確認して再実行してください。"),
        "OSError": ("File could not be read. Check the drive and retry.",
                    "ファイルを読み取れません。保存先ドライブを確認して再実行してください。"),
    }
    ja = language == "ja"
    lines = ["比較結果は作成していません。問題を修正し、フォルダを再比較してください。" if ja
             else "No comparison was created. Resolve these issues, then compare again."]
    for item in errors[:limit]:
        if not isinstance(item, dict):
            raise ValueError("Invalid scan error")
        name = str(item.get("relative_path", "?"))
        # JSON-quote filenames so control characters cannot forge report lines.
        name = json.dumps(name, ensure_ascii=False)
        reason = reasons.get(item.get("error"), (
            "Could not read this item. Check the file and retry.",
            "読み取れません。ファイルを確認して再実行してください。"))[int(ja)]
        lines.append("- " + name + ": " + reason)
    if len(errors) > limit:
        lines.append(("ほか {n} 件" if ja else "{n} more issue(s)").format(n=len(errors)-limit))
    return "\n".join(lines)


def render_delivery_summary(report, language="en", generated_at=None):
    """Human-readable evidence, not a signature or proof of modification time."""
    if language not in ("en", "ja") or not isinstance(report, dict) or report.get("schema") != 1:
        raise ValueError("Invalid report or language")
    counts, changes = report.get("summary"), report.get("changes")
    statuses = ("ADDED", "REMOVED", "MODIFIED", "UNCHANGED")
    if not isinstance(counts, dict) or set(counts) != set(statuses) or not isinstance(changes, list):
        raise ValueError("Invalid counts")
    actual = dict.fromkeys(statuses, 0)
    for row in changes:
        if not isinstance(row, dict) or set(row) != set(COLUMNS) or row["status"] not in actual:
            raise ValueError("Invalid evidence row")
        relative(row["relative_path"])
        for key in ("old_sha256", "new_sha256"):
            value = row[key]
            if not isinstance(value, str) or (value and not re.fullmatch(r"[0-9a-f]{64}", value)):
                raise ValueError("Invalid SHA-256")
        actual[row["status"]] += 1
    if counts != actual or changes != sorted(changes, key=lambda r: r["relative_path"]):
        raise ValueError("Inconsistent evidence")
    moment = generated_at if generated_at is not None else datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise ValueError("Timezone required")
    timestamp = moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    ja = language == "ja"
    lines = [
        "納品画像の変更証跡" if ja else "IMAGE DELIVERY CHANGE EVIDENCE",
        "=" * 40,
        ("レポート作成日時: " if ja else "Report generated: ") + timestamp,
        ("追加 {ADDED} / 削除 {REMOVED} / 同名変更 {MODIFIED} / 変更なし {UNCHANGED}" if ja else
         "Added {ADDED} / Removed {REMOVED} / Modified {MODIFIED} / Unchanged {UNCHANGED}").format(**counts),
        ("読取・リンクエラー: 0。エラー時は比較を拒否し、レポートを作成しません。" if ja else
         "Read/link errors: 0. Comparison is refused if any scan error occurs."),
        ("元画像は読み取り専用。削除・編集・自動修復は行っていません。" if ja else
         "Source images read-only: no deletion, editing or automatic repair."),
        ("日時の限界: 上記はレポート作成時刻で、画像の変更日時・納品日時の証明ではありません。" if ja else
         "Time limitation: report creation time does NOT prove modification or delivery time."),
        ("SHA-256は読み取った内容の比較であり、署名・第三者認証ではありません。" if ja else
         "SHA-256 compares scanned content; NOT a digital signature or third-party certification."),
        "",
        "お客様への確認ポイント" if ja else "CLIENT REVIEW: WHAT CHANGED",
        ("追加=新しい画像、削除=今回のフォルダにない画像、変更=同名でも内容や寸法が異なる画像。" if ja else
         "Added = new image; Removed = absent from latest folder; Modified = same filename with different content or dimensions."),
        ("次の操作: 下記の変更ファイルを確認し、納品先と差分を確認してください。" if ja else
         "Next step: Review the changed filenames below and confirm differences with the recipient."),
        ("比較方法: 2つのフォルダ内の相対パスを比較します。名前変更は「削除+追加」と表示されます。" if ja else
         "Comparison matches relative paths in two folders. A renamed file appears as removed + added."),
        ("変更なしの画像は件数に含まれますが、明細には表示しません。" if ja else
         "Unchanged images count toward the total but are omitted from details."),
        "", ("変更ファイルの詳細" if ja else "CHANGED FILE DETAILS"), "-" * 40
    ]
    labels = {"ADDED":"追加" if ja else "Added", "REMOVED":"削除" if ja else "Removed",
              "MODIFIED":"変更" if ja else "Modified"}
    for row in changes:
        if row["status"] == "UNCHANGED":
            continue
        lines += [
            "[" + labels[row["status"]] + "] " + json.dumps(row["relative_path"], ensure_ascii=False),
            "  Before SHA-256: " + (row["old_sha256"] or "—"),
            "  After  SHA-256: " + (row["new_sha256"] or "—"),
            "  Before dimensions/bytes: " + str(row["old_dimensions"] or "—") + " / " + str(row["old_bytes"] or "—"),
            "  After  dimensions/bytes: " + str(row["new_dimensions"] or "—") + " / " + str(row["new_bytes"] or "—")
        ]
    if not any(row["status"] != "UNCHANGED" for row in changes):
        lines.append("変更なし" if ja else "No changes detected")
    return "\n".join(lines) + "\n"

def write_delivery_summary(path, report, atomic_writer, language="en"):
    """One-step TXT export outside both source folders."""
    target = safe_output(path, [report["old_root"], report["new_root"]])
    if target.suffix.lower() != ".txt":
        raise ValueError("Use TXT")
    atomic_writer(target, render_delivery_summary(report, language))

def safe_output(path,roots):
    target=Path(path).absolute()
    if target.is_symlink() or target.parent.is_symlink() or not target.parent.is_dir():
        raise ValueError("Unsafe evidence output")
    resolved=target.resolve(strict=False)
    for root in roots:
        source=Path(root).resolve(strict=False)
        if resolved==source or source in resolved.parents:
            raise ValueError("Save evidence outside source image folders")
    return target

def write_snapshot(path,value,atomic_writer):
    validate_snapshot(value)
    target=safe_output(path,[value["root"]])
    if target.suffix.lower()!=".json":raise ValueError("Use JSON snapshot")
    content=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if len(content.encode("utf-8"))>MAX_JSON:raise ValueError("Snapshot too large")
    atomic_writer(target,content)

def load_snapshot(path):
    p=Path(path).absolute()
    if p.is_symlink() or not p.is_file() or p.stat().st_size>MAX_JSON:
        raise ValueError("Unsafe snapshot file")
    return validate_snapshot(json.loads(p.read_text(encoding="utf-8")))

def write_comparison(path,report,atomic_writer):
    if not isinstance(report,dict) or set(report)!={"schema","old_root","new_root","summary","changes"} or report["schema"]!=1:
        raise ValueError("Invalid report")
    target=safe_output(path,[report["old_root"],report["new_root"]])
    if target.suffix.lower()==".json":
        content=json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    elif target.suffix.lower()==".csv":
        output=io.StringIO(newline="")
        writer=csv.DictWriter(output,fieldnames=COLUMNS,lineterminator="\n")
        writer.writeheader()
        for row in report["changes"]:writer.writerow({k:row[k] for k in COLUMNS})
        content=output.getvalue()
    else:raise ValueError("Use CSV or JSON")
    atomic_writer(target,content)
