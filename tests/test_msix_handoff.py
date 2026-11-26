import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
import struct
import zlib

from tools.msix_handoff import create_handoff

XML=(b'<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
     b'<Identity Name="OkinawaDesktopTools.Demo" Publisher="CN=TEST" Version="1.0.0.0"/>'
     b'<Applications><Application Id="App" Executable="demo.exe" '
     b'EntryPoint="Windows.FullTrustApplication"/></Applications></Package>')


def png_bytes(width, height, value=0):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )
    raw = b"".join(
        b"\x00" + bytes([value, 0, 0, 255]) * width for _ in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FactoryTransportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        self.git("config","user.name","Handoff Fixture")
        self.git("config","user.email","handoff@example.invalid")

        self.kind="app"
        (self.root/"factory").mkdir()
        (self.root/"factory/config.json").write_text(json.dumps({"kind":self.kind}))
        self.prod=self.root/"products/demo-product"
        assets=self.prod/"store/assets"
        assets.mkdir(parents=True)
        (self.prod/"manifest.json").write_text(
            json.dumps({"slug":"demo-product","kind":self.kind,"entry":"main.py"})
        )
        (self.prod/"main.py").write_text("print('handoff fixture')\n",encoding="utf-8")
        for name,dimensions in (
            ("StoreLogo.png",(300,300)),
            ("Square150.png",(150,150)),
            ("Square44.png",(44,44)),
        ):
            (assets/name).write_bytes(png_bytes(*dimensions))

        self.git("add",".")
        self.git("commit","-qm","immutable app source and Store assets")
        self.source_sha=self.git("rev-parse","HEAD")
        self.request_id=f"app-demo-product-{self.source_sha[:12]}"
        self.approved={
            "reviewed":True,
            "source":"partner_center",
            "request_id":self.request_id,
            "product_type":"APP",
            "source_factory":"AI-App-Factory",
            "source_repository":"shihuiarenjinba-png/AI-App-Factory",
            "source_branch":"codex/handoff-fixture",
            "source_sha":self.source_sha,
            "verified_source_sha":self.source_sha,
            "expected_head_sha":self.source_sha,
            "store_id":"9PTESTING",
            "name":"OkinawaDesktopTools.Demo",
            "publisher":"CN=TEST",
            "version":"1.0.0.0",
            "verified_by":"LOCAL_OPERATOR_FIXTURE",
            "evidence_url":"https://partner.microsoft.com/dashboard/products/demo",
            "package_version_gate":"APPROVED",
        }
        self.save_approved()
        self.package=self.root/"sample.msix"
        self.write_package()

    def git(self,*args):
        return subprocess.run(
            ["git","-C",str(self.root),*args],
            check=True,capture_output=True,text=True
        ).stdout.strip()

    def save_approved(self):
        (self.prod/"store/approved-identity.json").write_text(
            json.dumps(self.approved),encoding="utf-8"
        )

    def write_package(self,manifest=XML,asset_overrides=None,include_metadata=True):
        asset_overrides=asset_overrides or {}
        with zipfile.ZipFile(self.package,"w") as archive:
            archive.writestr("AppxManifest.xml",manifest)
            archive.writestr("demo.exe",b"windows test executable")
            if include_metadata:
                archive.writestr(
                    "AppxBlockMap.xml",
                    b'<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap"/>'
                )
                archive.writestr(
                    "[Content_Types].xml",
                    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
                )
            for name in ("StoreLogo.png","Square150.png","Square44.png"):
                data=asset_overrides.get(
                    name,(self.prod/"store/assets"/name).read_bytes()
                )
                archive.writestr("Assets/"+name,data)

    def create(self):
        return create_handoff(
            self.root,"demo-product",self.package,self.root/"exports",self.source_sha
        )

    def test_produces_handoff_with_actual_bytes_and_asset_hashes(self):
        meta=self.create()
        self.assertEqual(meta["type"],self.kind)
        self.assertEqual(meta["status"],"QA_UNSIGNED")
        saved=self.root/"exports/factory-msix-handoff"
        self.assertEqual((saved/"package.msix").read_bytes(),self.package.read_bytes())
        self.assertEqual(meta["package_sha256"],hashlib.sha256(self.package.read_bytes()).hexdigest())
        self.assertEqual(meta["executable_sha256"],hashlib.sha256(b"windows test executable").hexdigest())
        self.assertEqual(set(meta["asset_sha256"]),{"StoreLogo.png","Square150.png","Square44.png"})

    def test_no_partner_center_evidence_fails(self):
        self.approved["reviewed"]=False
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"Partner Center Identity not verified"):
            self.create()

    def test_wrong_publisher_fails(self):
        self.approved["publisher"]="CN=FAKE"
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"approved publisher"):
            self.create()

    def test_wrong_source_sha_fails(self):
        with self.assertRaisesRegex(ValueError,"Git source"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports","not-a-sha")

    def test_kind_mismatch_fails(self):
        (self.root/"factory/config.json").write_text(json.dumps({"kind":"game"}))
        self.git("add","factory/config.json")
        self.git("commit","-qm","factory kind changed")
        new_head=self.git("rev-parse","HEAD")
        self.approved.update(
            source_sha=new_head,
            verified_source_sha=new_head,
            expected_head_sha=new_head,
            request_id=f"app-demo-product-{new_head[:12]}",
        )
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"factory mismatch"):
            self.create()

    def test_factory_config_worktree_change_fails(self):
        (self.root/"factory/config.json").write_text(json.dumps({"kind":"game"}))
        with self.assertRaisesRegex(ValueError,"Factory config differs"):
            self.create()

    def test_stale_identity_source_fails(self):
        self.approved.update(
            source_sha="0"*40,
            verified_source_sha="0"*40,
            expected_head_sha="0"*40,
            request_id="app-demo-product-000000000000",
        )
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"stale approved Identity"):
            self.create()

    def test_missing_identity_fails(self):
        (self.prod/"store/approved-identity.json").unlink()
        with self.assertRaisesRegex(ValueError,"Identity missing"):
            self.create()

    def test_msix_store_asset_mismatch_fails(self):
        self.write_package(asset_overrides={"Square150.png":b"not-the-source-asset"})
        with self.assertRaisesRegex(ValueError,"Store asset differs from current source"):
            self.create()

    def test_invalid_msix_fails(self):
        self.package.write_bytes(b"not a msix")
        with self.assertRaisesRegex(ValueError,"invalid MSIX"):
            self.create()

    def test_plain_zip_with_manifest_is_not_msix(self):
        with zipfile.ZipFile(self.package,"w") as archive:
            archive.writestr("AppxManifest.xml",XML)
            archive.writestr("demo.exe",b"windows test executable")
        with self.assertRaisesRegex(ValueError,"required MSIX package metadata"):
            self.create()

    def test_duplicate_case_insensitive_member_is_rejected(self):
        with zipfile.ZipFile(self.package,"a") as archive:
            archive.writestr("appxmanifest.xml",XML)
        with self.assertRaisesRegex(ValueError,"duplicate MSIX ZIP member"):
            self.create()

    def test_malformed_block_map_is_rejected(self):
        with zipfile.ZipFile(self.package,"w") as archive:
            archive.writestr("AppxManifest.xml",XML)
            archive.writestr("demo.exe",b"windows test executable")
            archive.writestr("AppxBlockMap.xml",b"<Other/>")
            archive.writestr("[Content_Types].xml",b"<Types/>")
        with self.assertRaisesRegex(ValueError,"block map root"):
            self.create()

    def test_manifest_only_msix_metadata_cannot_export(self):
        with zipfile.ZipFile(self.package,"w") as archive:
            archive.writestr("AppxManifest.xml",XML)
            archive.writestr("AppxBlockMap.xml",b"<BlockMap/>")
            archive.writestr("[Content_Types].xml",b"<Types/>")
        with self.assertRaisesRegex(ValueError,"executable payload missing"):
            self.create()

    def test_wrong_executable_path_cannot_export(self):
        with zipfile.ZipFile(self.package,"w") as archive:
            archive.writestr("AppxManifest.xml",XML.replace(b"demo.exe",b"other.exe"))
            archive.writestr("demo.exe",b"unrelated program")
            archive.writestr("AppxBlockMap.xml",b"<BlockMap/>")
            archive.writestr("[Content_Types].xml",b"<Types/>")
        with self.assertRaisesRegex(ValueError,"executable payload missing"):
            self.create()

    def test_traversal_executable_path_cannot_export(self):
        with zipfile.ZipFile(self.package,"w") as archive:
            archive.writestr("AppxManifest.xml",XML.replace(b"demo.exe",b"../demo.exe"))
            archive.writestr("demo.exe",b"windows test executable")
            archive.writestr("AppxBlockMap.xml",b"<BlockMap/>")
            archive.writestr("[Content_Types].xml",b"<Types/>")
        with self.assertRaisesRegex(ValueError,"unsafe MSIX executable path"):
            self.create()

    def test_crc_corrupted_executable_cannot_export(self):
        raw=bytearray(self.package.read_bytes())
        offset=raw.index(b"windows test executable")
        raw[offset]=ord("W")
        self.package.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,"invalid MSIX container"):
            self.create()

    def test_duplicate_bundle_fails(self):
        self.create()
        with self.assertRaisesRegex(ValueError,"already exists"):
            self.create()


if __name__=="__main__":
    unittest.main()
