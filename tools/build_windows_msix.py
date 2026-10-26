"""Windows-only gated PyInstaller -> MakeAppx MSIX candidate builder.

Never creates Store identities, signs packages, publishes, or claims certification.
Requires real brand assets and user-verified package identity before building.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,80}$")
VERSION=re.compile(r"^\d{1,5}\.\d{1,5}\.\d{1,5}\.\d{1,5}$")
ASSETS=("StoreLogo.png","Square150.png","Square44.png")
NS="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP="http://schemas.microsoft.com/appx/manifest/uap/windows10"
RESCAP="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"

def verify_inputs(root:Path,slug:str)->tuple[Path,dict]:
    product=root/"products"/slug
    if not product.is_dir() or product.is_symlink():
        raise ValueError("product source directory unavailable")
    manifest=json.loads((product/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("slug")!=slug or manifest.get("entry")!="main.py":
        raise ValueError("product manifest not approved for executable build")
    approved=product/"store/approved-identity.json"
    if not approved.is_file():
        raise ValueError("Store Identity missing; do not invent")
    cfg=json.loads(approved.read_text(encoding="utf-8"))
    if (cfg.get("reviewed") is not True or cfg.get("source")!="partner_center" or
        not isinstance(cfg.get("store_id"),str) or not cfg["store_id"].strip()):
        raise ValueError("Partner Center Identity not verified")
    for field in ("name","publisher","version"):
        if not isinstance(cfg.get(field),str) or not cfg[field]:
            raise ValueError("Missing verified "+field)
    if not NAME.fullmatch(cfg["name"]) or not VERSION.fullmatch(cfg["version"]):
        raise ValueError("Invalid Name or Version")
    for file in ASSETS:
        path=product/"store/assets"/file
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024:
            raise ValueError("Approved Store asset missing: "+file)
        if path.open("rb").read(8)!=b"\x89PNG\r\n\x1a\n":
            raise ValueError("Store asset is not PNG: "+file)
    if not (product/"main.py").is_file():raise ValueError("main.py absent")
    return product,cfg

def appx_manifest(identity:dict,executable:str)->bytes:
    ET.register_namespace("",NS)
    ET.register_namespace("uap",UAP)
    ET.register_namespace("rescap",RESCAP)
    def tag(ns,name):return "{"+ns+"}"+name
    root=ET.Element(tag(NS,"Package"),{"IgnorableNamespaces":"uap rescap"})
    ET.SubElement(root,tag(NS,"Identity"),{
      "Name":identity["name"],"Publisher":identity["publisher"],
      "Version":identity["version"],"ProcessorArchitecture":"x64"})
    props=ET.SubElement(root,tag(NS,"Properties"))
    ET.SubElement(props,tag(NS,"DisplayName")).text=identity.get("display_name",identity["name"])
    ET.SubElement(props,tag(NS,"PublisherDisplayName")).text=identity.get("publisher_display_name","OkinawaDesktopTools")
    ET.SubElement(props,tag(NS,"Logo")).text="Assets\\StoreLogo.png"
    resources=ET.SubElement(root,tag(NS,"Resources"))
    ET.SubElement(resources,tag(NS,"Resource"),{"Language":"en-us"})
    dependencies=ET.SubElement(root,tag(NS,"Dependencies"))
    ET.SubElement(dependencies,tag(NS,"TargetDeviceFamily"),{
      "Name":"Windows.Desktop","MinVersion":"10.0.17763.0","MaxVersionTested":"10.0.26100.0"})
    applications=ET.SubElement(root,tag(NS,"Applications"))
    app=ET.SubElement(applications,tag(NS,"Application"),{
        "Id":"App","Executable":executable,"EntryPoint":"Windows.FullTrustApplication"})
    ET.SubElement(app,tag(UAP,"VisualElements"),{
        "DisplayName":identity.get("display_name",identity["name"]),
        "Description":identity.get("display_name",identity["name"]),
        "BackgroundColor":"transparent",
        "Square150x150Logo":"Assets\\Square150.png",
        "Square44x44Logo":"Assets\\Square44.png"})
    capabilities=ET.SubElement(root,tag(NS,"Capabilities"))
    ET.SubElement(capabilities,tag(RESCAP,"Capability"),{"Name":"runFullTrust"})
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)

def locate_makeappx()->Path:
    base=Path("C:/Program Files (x86)/Windows Kits/10/bin")
    matches=sorted(base.glob("*/x64/makeappx.exe"),reverse=True)
    if not matches:
        raise ValueError("Windows SDK MakeAppx missing; HOLD")
    return matches[0]

def build(repo_root:Path,slug:str,out:Path)->Path:
    if sys.platform!="win32":raise ValueError("Windows runner required")
    product,identity=verify_inputs(repo_root,slug)
    if out.exists() and any(out.iterdir()):raise ValueError("refusing to overwrite existing output")
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="msix-pack-") as temp:
        work=Path(temp)
        exe=slug+".exe"
        subprocess.run([sys.executable,"-m","PyInstaller",
            "--noconfirm","--clean","--onefile","--windowed",
            "--name",slug,"--distpath",str(work/"dist"),"--workpath",str(work/"work"),
            "--specpath",str(work),str(product/"main.py")],
            check=True,timeout=600)
        layout=work/"layout"
        (layout/"Assets").mkdir(parents=True)
        shutil.copyfile(work/"dist"/exe,layout/exe)
        for file in ASSETS:
            shutil.copyfile(product/"store/assets"/file,layout/"Assets"/file)
        (layout/"AppxManifest.xml").write_bytes(appx_manifest(identity,exe))
        destination=out/(slug+".msix")
        subprocess.run([str(locate_makeappx()),"pack","/d",str(layout),
            "/p",str(destination),"/o"],check=True,timeout=180)
        if not destination.is_file() or destination.stat().st_size<1000:
            raise ValueError("MSIX output absent or implausibly small")
        return destination

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--slug",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(argv)
    try:
        product=build(args.root,args.slug,args.output)
        print(product)
        return 0
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError,
            subprocess.TimeoutExpired,json.JSONDecodeError) as error:
        print("MSIX_BUILD_HOLD:",str(error)[:220],file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())
