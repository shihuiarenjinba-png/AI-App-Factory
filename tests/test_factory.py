import json
import tempfile
import unittest
from pathlib import Path
from factory import plan, validate, promote, save

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"factory").mkdir()
        (self.root/".candidate").mkdir()
        (self.root/".runtime").mkdir()
        (self.root/"AGENTS.md").write_text("Safety first.")
        save(self.root/"factory/config.json",{"name":"test","kind":"app"})
        save(self.root/"factory/state.json",{
            "schema":1,"kind":"app","stage":"research","cycle":1,"revision":0,"slug":None})
        save(self.root/".runtime/market.json",{"kind":"app","signals":[
            {"url":"https://github.com/a/b/issues/1"},{"url":"https://github.com/c/d/issues/2"}]})
        self.proposal={"slug":"simple-product","title":"A useful Windows offline utility",
            "customer_problem":"Users spend too long sorting local documents",
            "audience":"Professionals using desktop computers daily",
            "differentiation":"Local-first simple no-telemetry operations",
            "scope":["Allow offline file selection","Show clear validation errors"],
            "evidence_urls":["https://github.com/a/b/issues/1","https://github.com/c/d/issues/2"]}

    def research(self):
        plan(self.root)
        save(self.root/".candidate/proposal.json",self.proposal)

    def test_research_transition(self):
        self.research()
        self.assertEqual(validate(self.root)["slug"],"simple-product")
        promote(self.root)
        s=json.loads((self.root/"factory/state.json").read_text())
        self.assertEqual(s["stage"],"build")

    def test_forged_evidence_rejected(self):
        self.research()
        self.proposal["evidence_urls"]=["https://bad.example/a","https://bad.example/b"]
        save(self.root/".candidate/proposal.json",self.proposal)
        with self.assertRaises(ValueError):validate(self.root)

    def test_duplicate_rejected(self):
        self.research()
        (self.root/"products/simple-product").mkdir(parents=True)
        with self.assertRaises(ValueError):validate(self.root)

    def test_symlink_rejected(self):
        self.research()
        try:(self.root/".candidate/link.py").symlink_to(self.root/"AGENTS.md")
        except OSError:self.skipTest("no symlinks")
        with self.assertRaises(ValueError):validate(self.root)

    def test_stale_plan_rejected(self):
        self.research()
        s=json.loads((self.root/"factory/state.json").read_text())
        s["cycle"]=2;save(self.root/"factory/state.json",s)
        with self.assertRaises(ValueError):validate(self.root)

    def test_full_cycle(self):
        self.research();promote(self.root)
        (self.root/".candidate/proposal.json").unlink()
        plan(self.root)
        base=self.root/".candidate/product"
        (base/"tests").mkdir(parents=True)
        save(base/"manifest.json",{"slug":"simple-product","kind":"app","entry":"main.py"})
        (base/"README.md").write_text("Run with python main.py")
        (base/"main.py").write_text("print('ok')")
        (base/"tests/test_smoke.py").write_text("import unittest\nclass Smoke(unittest.TestCase):\n def test_ok(self):self.assertTrue(True)\n")
        promote(self.root)
        for revision in (1,2):
            s=json.loads((self.root/"factory/state.json").read_text())
            self.assertEqual(s["revision"],revision)
            plan(self.root)
            (base/"main.py").write_text("print('verified round %d')\n" % revision)
            (base/"tests/test_smoke.py").write_text(
                "import unittest\nclass Smoke(unittest.TestCase):\n def test_revision(self): self.assertEqual(%d,%d)\n"
                % (revision,revision))
            promote(self.root)
        s=json.loads((self.root/"factory/state.json").read_text())
        self.assertEqual((s["stage"],s["cycle"]),("research",2))


    def test_bad_extension_rejected(self):
        self.research()
        (self.root/".candidate/unsafe.exe").write_bytes(b"bad")
        with self.assertRaises(ValueError):validate(self.root)

    def test_research_requires_distinct_issue_repos(self):
        self.research()
        self.proposal["evidence_urls"]=["https://github.com/a/b/issues/1","https://github.com/a/b/issues/2"]
        signals=json.loads((self.root/".runtime/market.json").read_text())
        signals["signals"].append({"url":"https://github.com/a/b/issues/2"})
        save(self.root/".runtime/market.json",signals)
        save(self.root/".candidate/proposal.json",self.proposal)
        with self.assertRaises(ValueError):validate(self.root)

    def test_missing_market_signals_holds(self):
        save(self.root/".runtime/market.json",{"signals":[]})
        with self.assertRaises(ValueError):plan(self.root)

    def test_game_mode_research(self):
        save(self.root/"factory/config.json",{"name":"test-game","kind":"game"})
        s=json.loads((self.root/"factory/state.json").read_text())
        s["kind"]="game";save(self.root/"factory/state.json",s)
        save(self.root/".runtime/market.json",{"kind":"game","signals":[
            {"url":"https://github.com/game1/one/issues/1"},
            {"url":"https://github.com/game2/two/issues/2"}]})
        self.proposal["evidence_urls"]=["https://github.com/game1/one/issues/1","https://github.com/game2/two/issues/2"]
        self.research()
        self.assertEqual(validate(self.root)["slug"],"simple-product")


    def _prototype_for_validation(self,kind="app"):
        self.research();promote(self.root)
        (self.root/".candidate/proposal.json").unlink()
        plan(self.root)
        base=self.root/".candidate/product"
        (base/"tests").mkdir(parents=True)
        save(base/"manifest.json",{"slug":"simple-product","kind":kind,"entry":"main.py"})
        (base/"README.md").write_text("Run with Python 3.12.")
        (base/"main.py").write_text("print('working prototype')\n")
        (base/"tests/test_smoke.py").write_text(
            "import unittest\nclass Smoke(unittest.TestCase):\n def test_run(self):self.assertEqual(1,1)\n")
        return base

    def test_no_actual_code_change_is_rejected(self):
        base=self._prototype_for_validation()
        promote(self.root)
        plan(self.root)
        with self.assertRaisesRegex(ValueError,"must change actual product code"):
            validate(self.root)

    def test_change_without_regression_tests_is_rejected(self):
        base=self._prototype_for_validation()
        promote(self.root)
        plan(self.root)
        (base/"main.py").write_text("print('different')\n")
        with self.assertRaisesRegex(ValueError,"regression tests"):
            validate(self.root)

    def test_removing_product_file_is_rejected(self):
        base=self._prototype_for_validation()
        (base/"data.txt").write_text("mandatory historic data")
        promote(self.root)
        plan(self.root)
        (base/"data.txt").unlink()
        (base/"main.py").write_text("print('different')\n")
        (base/"tests/test_smoke.py").write_text(
            "import unittest\nclass Smoke(unittest.TestCase):\n def test_new(self):self.assertTrue(True)\n")
        with self.assertRaisesRegex(ValueError,"cannot silently delete"):
            validate(self.root)

    def test_network_api_rejected(self):
        base=self._prototype_for_validation()
        (base/"main.py").write_text("import socket\nsocket.socket()\n")
        with self.assertRaisesRegex(ValueError,"prohibited"):
            validate(self.root)

    def test_exec_api_rejected(self):
        base=self._prototype_for_validation()
        (base/"main.py").write_text("exec('print(1)')\n")
        with self.assertRaisesRegex(ValueError,"dynamic execution"):
            validate(self.root)

    def test_product_missing_test_rejected(self):
        base=self._prototype_for_validation()
        (base/"tests/test_smoke.py").write_text("pass\n")
        with self.assertRaisesRegex(ValueError,"no runnable smoke tests"):
            validate(self.root)

if __name__=="__main__":unittest.main()
