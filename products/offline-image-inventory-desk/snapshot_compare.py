"""Deterministic, read-only image delivery snapshot comparison; no source writes."""
import csv
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
