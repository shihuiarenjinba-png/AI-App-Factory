"""Create MSIX transfer artifact for Windows-all-auto, never a Store submission."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

SLUG=re.compile(r"^[a-z][a-z0-9-]{3,39}$")
SHA40=re.compile(r"^[a-f0-9]{40}$")
OWNER="shihuiarenjinba-png"

def fail(reason):
    raise ValueError("FACTORY_HANDOFF_HOLD: "+reason)

def msix_data(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 300*1024*1024:
        fail("MSIX missing, symlinked or oversized")
    try:
        with zipfile.ZipFile(path) as z:
            entries=z.infolist()
            if not 1 <= len(entries) <= 2000:fail("unsafe MSIX file count")
            for entry in entries:
                name=entry.filename.replace("\\","/")
                if (name.startswith("/") or ".." in name.split("/") or
                    entry.file_size>300*1024*1024 or
                    (entry.compress_size and entry.file_size>100*entry.compress_size)):
                    fail("unsafe MSIX ZIP member")
            found=[e for e in entries if e.filename.lower()=="appxmanifest.xml"]
            if len(found)!=1 or found[0].file_size>2*1024*1024:fail("AppxManifest.xml unavailable")
            root=ET.fromstring(z.read(found[0]))
    except (zipfile.BadZipFile,ET.ParseError,KeyError,RuntimeError,OSError) as error:
        fail("invalid MSIX container: "+type(error).__name__)
    identity=next((x for x in root.iter() if x.tag=="Identity" or x.tag.endswith("}Identity")),None)
    if identity is None:fail("MSIX identity absent")
    fields={key:identity.attrib.get(key.title()) for key in ("name","publisher","version")}
    if not all(isinstance(v,str) and v for v in fields.values()):fail("MSIX identity fields incomplete")
    digest=sha256()
    with path.open("rb") as reader:
        for piece in iter(lambda:reader.read(1024*1024),b""):digest.update(piece)
    fields.update(package_sha256=digest.hexdigest(),package_bytes=path.stat().st_size)
    return fields

def create_handoff(repo_root:Path,slug:str,package:Path,output:Path,source_sha:str)->dict:
    if not isinstance(slug,str) or not SLUG.fullmatch(slug):fail("invalid product slug")
    if not SHA40.fullmatch(str(source_sha)):fail("invalid Git source commit")
    config=json.loads((repo_root/"factory/config.json").read_text(encoding="utf-8"))
    kind=config.get("kind")
    if kind not in ("app","game"):fail("factory app/game kind missing")
    manifest_path=repo_root/"products"/slug/"manifest.json"
    app_manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if app_manifest.get("slug")!=slug or app_manifest.get("kind")!=kind:
        fail("product manifest / factory mismatch")
    approved_path=repo_root/"products"/slug/"store/approved-identity.json"
    if not approved_path.is_file():fail("official Identity approval input missing")
    approved=json.loads(approved_path.read_text(encoding="utf-8"))
    if (approved.get("reviewed") is not True or
        approved.get("source")!="partner_center" or
        not isinstance(approved.get("store_id"),str) or
        not approved["store_id"].strip()):
        fail("Partner Center approval not recorded")
    actual=msix_data(package)
    for field in ("name","publisher","version"):
        if approved.get(field)!=actual[field]:fail("MSIX identity differs from approved "+field)
    basename="AI-App-Factory" if kind=="app" else "AI-Game-Factory"
    result={
       "schema_version":1,"source_repository":"https://github.com/"+OWNER+"/"+basename,
       "source_sha":source_sha,"type":kind,"slug":slug,
       "package":"package.msix","status":"QA_UNSIGNED",
       "package_sha256":actual["package_sha256"],
       "package_bytes":actual["package_bytes"],
       "identity":{k:actual[k] for k in ("name","publisher","version")},
    }
    dest=output/"factory-msix-handoff"
    if dest.exists():fail("output artifact already exists")
    dest.mkdir(parents=True)
    try:
        shutil.copyfile(package,dest/"package.msix")
        (dest/"handoff.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        if msix_data(dest/"package.msix")["package_sha256"]!=actual["package_sha256"]:
            fail("copied MSIX hash mismatch")
    except BaseException:
        shutil.rmtree(dest,ignore_errors=True)
        raise
    return result

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--slug",required=True)
    parser.add_argument("--msix",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--repository-root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(argv)
    try:
        head=subprocess.check_output(["git","rev-parse","HEAD"],
            cwd=args.repository_root,encoding="utf-8",timeout=8).strip()
        print(json.dumps(create_handoff(args.repository_root,args.slug,args.msix,
            args.output,head),ensure_ascii=False))
        return 0
    except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired,KeyError) as exc:
        print("HOLD:",type(exc).__name__,str(exc)[:160],file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())
