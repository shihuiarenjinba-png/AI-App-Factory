"""Windows-only gated PyInstaller -> MakeAppx MSIX candidate builder.

The immutable product source is identified by its Git HEAD. The approved Identity
return is an operator-provided, untracked file placed at
products/<slug>/store/approved-identity.json after that source commit. It must
bind to the exact HEAD and deterministic request ID. The builder never creates
Identity, guesses Version, signs, submits, or publishes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib
from urllib.parse import urlparse

SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,49}$")
STORE_ID = re.compile(r"^[A-Za-z0-9]{8,32}$")
VERSION = re.compile(r"^\d{1,5}\.\d{1,5}\.\d{1,5}\.\d{1,5}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
ASSETS = ("StoreLogo.png", "Square150.png", "Square44.png")
ASSET_DIMS = {
    "StoreLogo.png": (300, 300),
    "Square150.png": (150, 150),
    "Square44.png": (44, 44),
}
REPOSITORY = "shihuiarenjinba-png/AI-App-Factory"
FACTORY = "AI-App-Factory"
NS = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP = "http://schemas.microsoft.com/appx/manifest/uap/windows10"
RESCAP = "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
IDENTITY_FILE = "approved-identity.json"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout.strip()


def source_head(root: Path) -> str:
    root = Path(root).resolve(strict=True)
    top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if not top.samefile(root):
        raise ValueError("root must be the Git checkout top-level")
    head = _git(root, "rev-parse", "HEAD").lower()
    if not SHA.fullmatch(head):
        raise ValueError("unusable source Git HEAD")
    return head


def identity_path_for(product: Path) -> Path:
    return product / "store" / IDENTITY_FILE


def identity_is_tracked(root: Path, slug: str) -> bool:
    relative = f"products/{slug}/store/{IDENTITY_FILE}"
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", relative],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.returncode == 0


def _assert_immutable_product_source(root: Path, slug: str) -> None:
    relative = f"products/{slug}/store/{IDENTITY_FILE}"
    if identity_is_tracked(root, slug):
        raise ValueError(
            "approved Identity return is tracked in the source commit; "
            "keep the operator return external to the immutable source"
        )
    changed = _git(root, "diff", "--name-only", "HEAD", "--", f"products/{slug}").splitlines()
    if changed:
        raise ValueError("product source differs from committed HEAD")
    untracked = _git(
        root, "ls-files", "--others", "--exclude-standard", "--", f"products/{slug}"
    ).splitlines()
    unexpected = [item for item in untracked if item.replace("\\", "/") != relative]
    if unexpected:
        raise ValueError("untracked product source files are not allowed")


def verify_png(path: Path, expected_dimensions: tuple[int, int]) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("approved Store asset missing or unsafe: " + path.name)
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Store asset is not a complete PNG: " + path.name)

    offset = 8
    width = height = None
    seen_ihdr = seen_idat = seen_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk: " + path.name)
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(data):
            raise ValueError("truncated PNG data: " + path.name)
        chunk_data = data[start:end]
        expected_crc = struct.unpack(">I", data[end:end + 4])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("Store asset PNG CRC mismatch: " + path.name)

        if not seen_ihdr:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("PNG IHDR missing or invalid: " + path.name)
            width, height = struct.unpack(">II", chunk_data[:8])
            seen_ihdr = True
        elif chunk_type == b"IHDR":
            raise ValueError("duplicate PNG IHDR: " + path.name)

        if chunk_type == b"IDAT":
            seen_idat = True
        if chunk_type == b"IEND":
            if length != 0:
                raise ValueError("invalid PNG IEND: " + path.name)
            seen_iend = True
            offset = end + 4
            if offset != len(data):
                raise ValueError("trailing bytes after PNG IEND: " + path.name)
            break
        offset = end + 4

    if not (seen_ihdr and seen_idat and seen_iend):
        raise ValueError("PNG is incomplete: " + path.name)
    if (width, height) != expected_dimensions:
        raise ValueError(
            f"Store asset dimensions mismatch for {path.name}: "
            f"expected {expected_dimensions[0]}x{expected_dimensions[1]}, got {width}x{height}"
        )
    return hashlib.sha256(data).hexdigest()


def verify_assets(product: Path) -> dict[str, str]:
    result = {}
    for filename in ASSETS:
        path = product / "store" / "assets" / filename
        result[filename] = verify_png(path, ASSET_DIMS[filename])
    return result


def verify_inputs(root: Path, slug: str) -> tuple[Path, dict]:
    root = Path(root).resolve(strict=True)
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("unsafe product slug")
    source_sha = source_head(root)

    if (root / "products").is_symlink():
        raise ValueError("linked products directory forbidden")
    product = root / "products" / slug
    if not product.is_dir() or product.is_symlink():
        raise ValueError("product source directory unavailable")
    store = product / "store"
    if store.is_symlink() or (store / "assets").is_symlink():
        raise ValueError("linked Store directory forbidden")

    manifest_path = product / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("product manifest missing or linked")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("kind") != "app"
        or manifest.get("slug") != slug
        or manifest.get("entry") != "main.py"
    ):
        raise ValueError("product manifest not approved for executable build")

    approved = identity_path_for(product)
    if approved.is_symlink() or not approved.is_file():
        raise ValueError("approved Identity return missing; do not invent")
    cfg = json.loads(approved.read_text(encoding="utf-8"))

    source_fields = ("source_sha", "verified_source_sha", "expected_head_sha")
    if any(cfg.get(field) != source_sha for field in source_fields):
        raise ValueError("stale approved Identity: source binding does not match current HEAD")
    expected_request = f"app-{slug}-{source_sha[:12]}"
    if cfg.get("request_id") != expected_request:
        raise ValueError("approved Identity request ID does not match current source")
    if (
        cfg.get("product_type") != "APP"
        or cfg.get("source_factory") != FACTORY
        or cfg.get("source_repository") != REPOSITORY
    ):
        raise ValueError("approved Identity belongs to a different Factory source")

    _assert_immutable_product_source(root, slug)

    if cfg.get("reviewed") is not True or cfg.get("source") != "partner_center":
        raise ValueError("Partner Center Identity not verified")
    store_id = cfg.get("store_id")
    if not isinstance(store_id, str) or not STORE_ID.fullmatch(store_id):
        raise ValueError("Partner Center Store ID missing or invalid")

    verifier = cfg.get("verified_by")
    if (
        not isinstance(verifier, str)
        or not 3 <= len(verifier) <= 100
        or any(ord(c) < 32 or ord(c) == 127 for c in verifier)
    ):
        raise ValueError("Missing official Identity reviewer")

    evidence = cfg.get("evidence_url")
    if not isinstance(evidence, str):
        raise ValueError("Missing official Partner Center evidence")
    url = urlparse(evidence)
    if (
        url.scheme != "https"
        or url.hostname not in ("partner.microsoft.com", "partnercenter.microsoft.com")
        or url.username
        or url.password
        or url.fragment
    ):
        raise ValueError("Invalid official Partner Center evidence URL")

    if not isinstance(cfg.get("name"), str) or not NAME.fullmatch(cfg["name"]):
        raise ValueError("Missing or invalid verified Package Name")
    if not isinstance(cfg.get("publisher"), str):
        raise ValueError("Missing verified Publisher")
    if (
        not cfg["publisher"].startswith("CN=")
        or len(cfg["publisher"]) > 512
        or any(ord(c) < 32 or ord(c) == 127 for c in cfg["publisher"])
    ):
        raise ValueError("Invalid official Publisher")

    version = cfg.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("authoritative Package Version missing; do not infer")
    if not VERSION.fullmatch(version):
        raise ValueError("Invalid authoritative Package Version")
    if any(int(component) > 65535 for component in version.split(".")):
        raise ValueError("Package Version component exceeds MSIX limit")
    version_gate = cfg.get("package_version_gate")
    if version_gate is not None and str(version_gate).upper() not in {
        "PASS", "APPROVED", "VERIFIED"
    }:
        raise ValueError("authoritative Package Version gate is not approved")

    if (product / "main.py").is_symlink() or not (product / "main.py").is_file():
        raise ValueError("main.py absent or linked")
    verify_assets(product)
    return product, cfg


def appx_manifest(identity: dict, executable: str) -> bytes:
    ET.register_namespace("", NS)
    ET.register_namespace("uap", UAP)
    ET.register_namespace("rescap", RESCAP)

    def tag(namespace, name):
        return "{" + namespace + "}" + name

    root = ET.Element(tag(NS, "Package"), {"IgnorableNamespaces": "uap rescap"})
    ET.SubElement(
        root,
        tag(NS, "Identity"),
        {
            "Name": identity["name"],
            "Publisher": identity["publisher"],
            "Version": identity["version"],
            "ProcessorArchitecture": "x64",
        },
    )
    props = ET.SubElement(root, tag(NS, "Properties"))
    ET.SubElement(props, tag(NS, "DisplayName")).text = identity.get(
        "display_name", identity["name"]
    )
    ET.SubElement(props, tag(NS, "PublisherDisplayName")).text = identity.get(
        "publisher_display_name", identity["publisher"]
    )
    ET.SubElement(props, tag(NS, "Logo")).text = "Assets\\StoreLogo.png"
    resources = ET.SubElement(root, tag(NS, "Resources"))
    ET.SubElement(resources, tag(NS, "Resource"), {"Language": "en-us"})
    dependencies = ET.SubElement(root, tag(NS, "Dependencies"))
    ET.SubElement(
        dependencies,
        tag(NS, "TargetDeviceFamily"),
        {
            "Name": "Windows.Desktop",
            "MinVersion": "10.0.17763.0",
            "MaxVersionTested": "10.0.26100.0",
        },
    )
    applications = ET.SubElement(root, tag(NS, "Applications"))
    app = ET.SubElement(
        applications,
        tag(NS, "Application"),
        {"Id": "App", "Executable": executable, "EntryPoint": "Windows.FullTrustApplication"},
    )
    ET.SubElement(
        app,
        tag(UAP, "VisualElements"),
        {
            "DisplayName": identity.get("display_name", identity["name"]),
            "Description": identity.get("display_name", identity["name"]),
            "BackgroundColor": "transparent",
            "Square150x150Logo": "Assets\\Square150.png",
            "Square44x44Logo": "Assets\\Square44.png",
        },
    )
    capabilities = ET.SubElement(root, tag(NS, "Capabilities"))
    ET.SubElement(capabilities, tag(RESCAP, "Capability"), {"Name": "runFullTrust"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def locate_makeappx() -> Path:
    base = Path("C:/Program Files (x86)/Windows Kits/10/bin")
    matches = sorted(base.glob("*/x64/makeappx.exe"), reverse=True)
    if not matches:
        raise ValueError("Windows SDK MakeAppx missing; HOLD")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_package_layout(
    product: Path, identity: dict, executable_path: Path, layout: Path
) -> dict:
    if layout.exists() and any(layout.iterdir()):
        raise ValueError("refusing to overwrite non-empty package layout")
    layout.mkdir(parents=True, exist_ok=True)
    executable_name = product.name + ".exe"
    if executable_path.is_symlink() or not executable_path.is_file():
        raise ValueError("PyInstaller executable missing or linked")

    shutil.copyfile(executable_path, layout / executable_name)
    exe_sha = _sha256(executable_path)
    if _sha256(layout / executable_name) != exe_sha:
        raise ValueError("staged executable bytes do not match PyInstaller output")

    source_assets = verify_assets(product)
    staged_assets = {}
    (layout / "Assets").mkdir()
    for filename in ASSETS:
        source = product / "store" / "assets" / filename
        destination = layout / "Assets" / filename
        shutil.copyfile(source, destination)
        staged_sha = _sha256(destination)
        if staged_sha != source_assets[filename]:
            raise ValueError("staged Store asset SHA-256 mismatch: " + filename)
        staged_assets[filename] = staged_sha

    manifest = appx_manifest(identity, executable_name)
    (layout / "AppxManifest.xml").write_bytes(manifest)
    return {
        "executable": executable_name,
        "exe_sha256": exe_sha,
        "asset_sha256": staged_assets,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    }


def verify_msix(package: Path, identity: dict, staged: dict) -> None:
    if not package.is_file() or package.stat().st_size < 1000:
        raise ValueError("MSIX output absent or implausibly small")
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        required = {
            "AppxManifest.xml",
            staged["executable"],
            "Assets/StoreLogo.png",
            "Assets/Square150.png",
            "Assets/Square44.png",
        }
        if not required.issubset(names):
            raise ValueError("MSIX is missing executable, manifest, or Store assets")
        for filename, expected_sha in staged["asset_sha256"].items():
            actual_sha = hashlib.sha256(archive.read("Assets/" + filename)).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError("MSIX Store asset SHA-256 mismatch: " + filename)
        root = ET.fromstring(archive.read("AppxManifest.xml"))
        manifest_identity = next(
            (node for node in root.iter() if node.tag.endswith("}Identity")), None
        )
        if manifest_identity is None:
            raise ValueError("MSIX AppxManifest Identity missing")
        expected = {
            "Name": identity["name"],
            "Publisher": identity["publisher"],
            "Version": identity["version"],
        }
        if any(manifest_identity.attrib.get(key) != value for key, value in expected.items()):
            raise ValueError("MSIX AppxManifest Identity does not match approved return")


def build(repo_root: Path, slug: str, out: Path) -> Path:
    if sys.platform != "win32":
        raise ValueError("Windows runner required")
    repo_root = Path(repo_root).resolve(strict=True)
    source_sha = source_head(repo_root)
    product, identity = verify_inputs(repo_root, slug)
    out = Path(out)
    if out.exists() and (out.is_symlink() or any(out.iterdir())):
        raise ValueError("refusing to overwrite existing output")
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="msix-pack-") as temp:
        work = Path(temp)
        executable_name = slug + ".exe"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onefile",
                "--windowed",
                "--name",
                slug,
                "--distpath",
                str(work / "dist"),
                "--workpath",
                str(work / "work"),
                "--specpath",
                str(work),
                str(product / "main.py"),
            ],
            check=True,
            timeout=600,
        )
        layout = work / "layout"
        staged = stage_package_layout(
            product, identity, work / "dist" / executable_name, layout
        )
        makeappx = locate_makeappx()
        destination = out / (slug + ".msix")
        subprocess.run(
            [str(makeappx), "pack", "/d", str(layout), "/p", str(destination)],
            check=True,
            timeout=180,
        )
        verify_msix(destination, identity, staged)

    receipt = {
        "status": "PASS",
        "source_sha": source_sha,
        "request_id": identity["request_id"],
        "store_id": identity["store_id"],
        "package_version": identity["version"],
        "exe_sha256": staged["exe_sha256"],
        "asset_sha256": staged["asset_sha256"],
        "manifest_sha256": staged["manifest_sha256"],
        "msix_sha256": _sha256(destination),
        "makeappx_invoked": True,
        "signature_status": "UNSIGNED",
        "store_submission": False,
        "publish": False,
    }
    (out / (slug + ".build-receipt.json")).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        product = build(args.root, args.slug, args.output)
        print(product)
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as error:
        print("MSIX_BUILD_HOLD:", str(error)[:240], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
