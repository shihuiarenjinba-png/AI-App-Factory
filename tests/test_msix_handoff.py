import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.msix_handoff import create_handoff

SHA="a"*40
XML=(b'<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
     b'<Identity Name="OkinawaDesktopTools.Demo" Publisher="CN=TEST" Version="1.0.0.0"/>'
     b'<Applications><Application Id="App" Executable="demo.exe" '
     b'EntryPoint="Windows.FullTrustApplication"/></Applications></Package>')

class FactoryTransportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.kind=Path(__file__).resolve().parents[1].joinpath("factory/config.json")
        self.kind=json.loads(self.kind.read_text(encoding="utf-8"))["kind"]
        (self.root/"factory").mkdir()
        (self.root/"factory/config.json").write_text(json.dumps({"kind":self.kind}))
        self.prod=self.root/"products/demo-product"
        (self.prod/"store").mkdir(parents=True)
        (self.prod/"manifest.json").write_text(json.dumps({"slug":"demo-product","kind":self.kind}))
        (self.prod/"qa").mkdir()
        (self.prod/"qa/windows-product-qa-plan.json").write_text(json.dumps({
            "schema_version": "windows-product-qa-plan-template-v1",
            "product_slug": "demo-product",
            "product_type": "APP" if self.kind == "app" else "GAME",
            "plan_version": 1,
            "steps": [
                {"step_id": "artifact-hash", "action": "ARTIFACT_HASH",
                 "requires": [], "required": True, "params": {}},
                {"step_id": "process-start", "action": "PROCESS_START",
                 "requires": ["artifact-hash"], "required": True,
                 "params": {"observation_seconds": 5}},
            ],
            "allowed_diagnostics": ["PROCESS_STATUS", "EVENT_LOG_QUERY"],
            "forbidden_actions": [
                "SOURCE_EDIT", "ARBITRARY_SHELL", "GIT_WRITE",
                "STORE_SUBMIT", "STORE_PUBLISH", "SECURITY_POLICY_CHANGE",
            ],
            "success_policy": {
                "required_steps_must_pass": True,
                "evidence_return_required": True,
                "product_e2e_authority": False,
                "release_authority": False,
                "store_authority": False,
            },
        }))
        self.approved={"reviewed":True,"source":"partner_center","store_id":"9PTESTING",
            "name":"OkinawaDesktopTools.Demo","publisher":"CN=TEST","version":"1.0.0.0"}
        self.save_approved()
        self.package=self.root/"sample.msix"
        with zipfile.ZipFile(self.package,"w") as zipfileout:
            zipfileout.writestr("AppxManifest.xml",XML)
            zipfileout.writestr("demo.exe",b"windows test executable")
            zipfileout.writestr("AppxBlockMap.xml",
                b'<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap"/>')
            zipfileout.writestr("[Content_Types].xml",
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')

    def save_approved(self):
        (self.prod/"store/approved-identity.json").write_text(json.dumps(self.approved))

    def test_produces_handoff_with_actual_bytes(self):
        meta=create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)
        self.assertEqual(meta["type"],self.kind)
        self.assertEqual(meta["status"],"QA_UNSIGNED")
        saved=self.root/"exports/factory-msix-handoff"
        self.assertEqual((saved/"package.msix").read_bytes(),self.package.read_bytes())
        self.assertEqual(meta["package_sha256"],hashlib.sha256(self.package.read_bytes()).hexdigest())
        self.assertEqual(meta["executable_sha256"],
                         hashlib.sha256(b"windows test executable").hexdigest())
        self.assertEqual(meta["qa_plan"], "qa-plan.json")
        qa=json.loads((saved/"qa-plan.json").read_text())
        self.assertEqual(qa["schema_version"], "windows-product-qa-plan-v1")
        self.assertEqual(qa["source_sha"], SHA)
        self.assertEqual(qa["package_sha256"], meta["package_sha256"])
        self.assertEqual(qa["executable_sha256"], meta["executable_sha256"])
        self.assertEqual(qa["identity"], meta["identity"])
        self.assertFalse(qa["success_policy"]["store_authority"])

    def test_missing_qa_plan_fails(self):
        (self.prod/"qa/windows-product-qa-plan.json").unlink()
        with self.assertRaisesRegex(ValueError, "QA plan"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

    def test_raw_command_in_qa_plan_fails(self):
        plan=json.loads((self.prod/"qa/windows-product-qa-plan.json").read_text())
        plan["steps"][1]["command"]="powershell.exe -Command whoami"
        (self.prod/"qa/windows-product-qa-plan.json").write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, "step fields"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

    def test_no_partner_center_evidence_fails(self):
        self.approved["reviewed"]=False
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"approval"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

    def test_wrong_publisher_fails(self):
        self.approved["publisher"]="CN=FAKE"
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"approved publisher"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

    def test_wrong_source_sha_fails(self):
        with self.assertRaisesRegex(ValueError,"Git source"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports","not-a-sha")

    def test_kind_mismatch_fails(self):
        (self.prod/"manifest.json").write_text(json.dumps({"slug":"demo-product","kind":"unknown"}))
        with self.assertRaisesRegex(ValueError,"factory mismatch"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

    def test_invalid_msix_fails(self):
        self.package.write_bytes(b"not a msix")
        with self.assertRaisesRegex(ValueError,"invalid MSIX"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

    def test_plain_zip_with_manifest_is_not_msix(self):
        with zipfile.ZipFile(self.package, "w") as archive:
            archive.writestr("AppxManifest.xml", XML)
            archive.writestr("demo.exe", b"windows test executable")
        with self.assertRaisesRegex(ValueError, "required MSIX package metadata"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_duplicate_case_insensitive_member_is_rejected(self):
        with zipfile.ZipFile(self.package, "a") as archive:
            archive.writestr("appxmanifest.xml", XML)
        with self.assertRaisesRegex(ValueError, "duplicate MSIX ZIP member"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_malformed_block_map_is_rejected(self):
        with zipfile.ZipFile(self.package, "w") as archive:
            archive.writestr("AppxManifest.xml", XML)
            archive.writestr("demo.exe", b"windows test executable")
            archive.writestr("AppxBlockMap.xml", b"<Other/>")
            archive.writestr("[Content_Types].xml", b"<Types/>")
        with self.assertRaisesRegex(ValueError, "block map root"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_manifest_only_msix_metadata_cannot_export(self):
        with zipfile.ZipFile(self.package, "w") as archive:
            archive.writestr("AppxManifest.xml", XML)
            archive.writestr("AppxBlockMap.xml", b"<BlockMap/>")
            archive.writestr("[Content_Types].xml", b"<Types/>")
        with self.assertRaisesRegex(ValueError, "executable payload missing"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_wrong_executable_path_cannot_export(self):
        with zipfile.ZipFile(self.package, "w") as archive:
            archive.writestr("AppxManifest.xml", XML)
            archive.writestr("other.exe", b"unrelated program")
            archive.writestr("AppxBlockMap.xml", b"<BlockMap/>")
            archive.writestr("[Content_Types].xml", b"<Types/>")
        with self.assertRaisesRegex(ValueError, "executable payload missing"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_traversal_executable_path_cannot_export(self):
        with zipfile.ZipFile(self.package, "w") as archive:
            archive.writestr("AppxManifest.xml",
                             XML.replace(b'demo.exe', b'../demo.exe'))
            archive.writestr("demo.exe", b"windows test executable")
            archive.writestr("AppxBlockMap.xml", b"<BlockMap/>")
            archive.writestr("[Content_Types].xml", b"<Types/>")
        with self.assertRaisesRegex(ValueError, "unsafe MSIX executable path"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_crc_corrupted_executable_cannot_export(self):
        raw=bytearray(self.package.read_bytes())
        offset=raw.index(b"windows test executable")
        raw[offset]=ord("W")
        self.package.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "invalid MSIX container"):
            create_handoff(self.root, "demo-product", self.package,
                           self.root / "exports", SHA)

    def test_duplicate_bundle_fails(self):
        create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)
        with self.assertRaisesRegex(ValueError,"already exists"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

if __name__=="__main__":unittest.main()
