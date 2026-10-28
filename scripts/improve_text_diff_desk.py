#!/usr/bin/env python3
"""Controller-owned improvement: normalize Windows CRLF and add a regression."""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import factory

ROOT=Path(__file__).resolve().parents[1]
BRANCH="codex/app-cohort-text-diff-20261028"
SLUG="offline-text-diff-desk"

def command(*args,**kwargs):
    return subprocess.run(args,check=True,text=True,**kwargs)

def run():
    if os.environ.get("GITHUB_REF")!="refs/heads/"+BRANCH:
        raise ValueError("Wrong branch")
    start=command("git","rev-parse","HEAD",capture_output=True).stdout.strip()
    if start!=os.environ.get("GITHUB_SHA"):
        raise ValueError("Event SHA mismatch")
    current=command("git","symbolic-ref","--short","HEAD",capture_output=True).stdout.strip()
    if current!=BRANCH or command("git","status","--porcelain",capture_output=True).stdout.strip():
        raise ValueError("Dirty or wrong checkout")
    _,state=factory.settings(ROOT)
    if state!={"schema":1,"kind":"app","stage":"improve","cycle":1,"revision":1,"slug":SLUG}:
        raise ValueError("Improvement must run once at revision 1")
    assert factory.plan(ROOT)["stage"]=="improve"
    candidate=ROOT/".candidate/product"
    code=candidate/"main.py"
    source=code.read_text(encoding="utf-8")
    before='result = raw.decode("utf-8-sig")'
    after='result = raw.decode("utf-8-sig").replace("\\r\\n", "\\n").replace("\\r", "\\n")'
    if source.count(before)!=1:
        raise ValueError("Unexpected read_text implementation")
    code.write_text(source.replace(before,after),encoding="utf-8")
    test=candidate/"tests/test_smoke.py"
    source=test.read_text(encoding="utf-8")
    anchor="    def test_utf8_read(self):"
    new_test=('    def test_crlf_normalized_on_windows(self):\n'
              '        self.left.write_bytes(b"alpha\\r\\nbeta\\r\\n")\n'
              '        self.assertEqual(app.read_text(self.left),"alpha\\nbeta\\n")\n\n')
    if source.count(anchor)!=1 or "test_crlf_normalized_on_windows" in source:
        raise ValueError("Unexpected test source")
    test.write_text(source.replace(anchor,new_test+anchor),encoding="utf-8")
    assert factory.validate(ROOT)=={"stage":"improve","slug":SLUG}
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    result=command(sys.executable,"-m","unittest","discover","-s","tests","-v",
                   cwd=candidate,capture_output=True,env=env,timeout=120)
    if "Ran 19 tests in" not in result.stderr or "skipped=" in result.stderr:
        raise ValueError("19 unskipped product tests not established")
    print(result.stderr,flush=True)
    assert factory.promote(ROOT)=={"stage":"improve","slug":SLUG}
    if factory.settings(ROOT)[1]["revision"]!=2:
        raise ValueError("Revision did not advance")
    command(sys.executable,"-m","unittest","discover","-s","tests","-v",
            cwd=ROOT,env=env,timeout=180)
    command("git","add","--","factory/state.json",f"products/{SLUG}/main.py",
            f"products/{SLUG}/tests/test_smoke.py")
    command("git","add","-u","--",".candidate/product/main.py",
            ".candidate/product/tests/test_smoke.py")
    staged=command("git","diff","--cached","--name-only",capture_output=True).stdout.splitlines()
    allowed={"factory/state.json",f"products/{SLUG}/main.py",
             f"products/{SLUG}/tests/test_smoke.py",
             ".candidate/product/main.py",".candidate/product/tests/test_smoke.py"}
    if set(staged)!=allowed:
        raise ValueError("Unexpected staged changes: "+repr(staged))
    command("git","diff","--cached","--check")
    command("git","-c","user.name=github-actions[bot]",
            "-c","user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit","-m","fix(text-diff): normalize CRLF through audited improve lifecycle")
    remote=command("git","ls-remote","origin","refs/heads/"+BRANCH,
                   capture_output=True).stdout.split()[0]
    if remote!=start:
        raise ValueError("Remote changed; refuse overwrite")
    command("git","push","origin","HEAD:refs/heads/"+BRANCH)
    source_sha=command("git","rev-parse","HEAD",capture_output=True).stdout.strip()
    request_id="app-offline-text-diff-desk-"+source_sha[:12]
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
            f.write(f"source_sha={source_sha}\nrequest_id={request_id}\n")
    print({"FACTORY_IMPROVEMENT_PASS":True,"source_sha":source_sha,
           "request_id":request_id,"product_tests":19})

if __name__=="__main__":
    run()
