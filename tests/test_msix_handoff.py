import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.msix_handoff import create_handoff

SHA="a"*40
XML=b'<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"><Identity Name="OkinawaDesktopTools.Demo" Publisher="CN=TEST" Version="1.0.0.0"/></Package>'

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
        self.approved={"reviewed":True,"source":"partner_center","store_id":"9PTESTING",
            "name":"OkinawaDesktopTools.Demo","publisher":"CN=TEST","version":"1.0.0.0"}
        self.save_approved()
        self.package=self.root/"sample.msix"
        with zipfile.ZipFile(self.package,"w") as zipfileout:
            zipfileout.writestr("AppxManifest.xml",XML)
            zipfileout.writestr("demo.exe",b"windows test executable")

    def save_approved(self):
        (self.prod/"store/approved-identity.json").write_text(json.dumps(self.approved))

    def test_produces_handoff_with_actual_bytes(self):
        meta=create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)
        self.assertEqual(meta["type"],self.kind)
        self.assertEqual(meta["status"],"QA_UNSIGNED")
        saved=self.root/"exports/factory-msix-handoff"
        self.assertEqual((saved/"package.msix").read_bytes(),self.package.read_bytes())
        self.assertEqual(meta["package_sha256"],hashlib.sha256(self.package.read_bytes()).hexdigest())

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

    def test_duplicate_bundle_fails(self):
        create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)
        with self.assertRaisesRegex(ValueError,"already exists"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA)

if __name__=="__main__":unittest.main()
