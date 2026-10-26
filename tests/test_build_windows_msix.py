import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tools.build_windows_msix import appx_manifest, verify_inputs

PNG=b"\x89PNG\r\n\x1a\n"+"".encode()
IDENTITY={"reviewed":True,"source":"partner_center","store_id":"9PTEST123",
          "name":"OkinawaDesktopTools.Demo","publisher":"CN=TEST","version":"1.0.0.0",
          "verified_by":"local-operator",
          "evidence_url":"https://partner.microsoft.com/dashboard/products/demo"}

class WindowsPackageContractTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.product=self.root/"products/demo-product"
        asset_dir=self.product/"store/assets"
        asset_dir.mkdir(parents=True)
        (self.product/"main.py").write_text("print('ok')")
        (self.product/"manifest.json").write_text(json.dumps({"kind":"app","slug":"demo-product","entry":"main.py"}))
        (self.product/"store/approved-identity.json").write_text(json.dumps(IDENTITY))
        for name in ("StoreLogo.png","Square150.png","Square44.png"):
            (asset_dir/name).write_bytes(PNG+b"not-valid-image-but-magic-header")

    def test_identity_produces_xml(self):
        xml=appx_manifest(IDENTITY,"demo-product.exe")
        root=ET.fromstring(xml)
        identity=next(x for x in root.iter() if x.tag.endswith("}Identity"))
        self.assertEqual(identity.attrib["Name"],IDENTITY["name"])
        self.assertEqual(identity.attrib["Publisher"],IDENTITY["publisher"])
        self.assertEqual(identity.attrib["Version"],IDENTITY["version"])

    def test_verified_identity_preflight(self):
        _,cfg=verify_inputs(self.root,"demo-product")
        self.assertEqual(cfg["store_id"],"9PTEST123")

    def test_missing_asset_holds(self):
        (self.product/"store/assets/StoreLogo.png").unlink()
        with self.assertRaisesRegex(ValueError,"asset missing"):
            verify_inputs(self.root,"demo-product")

    def test_no_human_review_holds(self):
        obj=dict(IDENTITY,reviewed=False)
        (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,"not verified"):
            verify_inputs(self.root,"demo-product")

    def test_identity_not_guessed(self):
        (self.product/"store/approved-identity.json").unlink()
        with self.assertRaisesRegex(ValueError,"do not invent"):
            verify_inputs(self.root,"demo-product")

    def test_incomplete_official_identity_attestation_holds(self):
        for key in ("verified_by", "evidence_url", "store_id"):
            with self.subTest(key=key):
                obj=dict(IDENTITY)
                del obj[key]
                (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
                with self.assertRaises(ValueError):
                    verify_inputs(self.root,"demo-product")

    def test_untrusted_evidence_url_holds(self):
        for evidence in (
            "http://partner.microsoft.com/dashboard",
            "https://partner.microsoft.com.evil.example/dashboard",
            "https://user:secret@partner.microsoft.com/dashboard",
            "https://partner.microsoft.com/dashboard#fragment",
        ):
            with self.subTest(evidence=evidence):
                obj=dict(IDENTITY,evidence_url=evidence)
                (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
                with self.assertRaisesRegex(ValueError,"evidence URL"):
                    verify_inputs(self.root,"demo-product")

    def test_invalid_official_publisher_and_version_holds(self):
        for change in (
            {"publisher":"unverified-publisher"},
            {"version":"1.65536.0.0"},
            {"name":"A"+"x"*50},
            {"store_id":"fake"},
            {"verified_by":"name\\nnewline"},
        ):
            with self.subTest(change=change):
                obj=dict(IDENTITY,**change)
                (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
                with self.assertRaises(ValueError):
                    verify_inputs(self.root,"demo-product")

    def test_cross_lane_product_manifest_holds(self):
        (self.product/"manifest.json").write_text(
            json.dumps({"kind":"game","slug":"demo-product","entry":"main.py"}))
        with self.assertRaisesRegex(ValueError,"manifest not approved"):
            verify_inputs(self.root,"demo-product")

    def test_invalid_version_holds(self):
        obj=dict(IDENTITY,version="1.0")
        (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,"Invalid Name or Version"):
            verify_inputs(self.root,"demo-product")

if __name__=="__main__":unittest.main()
