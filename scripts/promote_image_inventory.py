#!/usr/bin/env python3
"""Cohort 5 genuine controller research/build promotion, without direct state edits."""
import json, os, shutil, subprocess, sys, tempfile, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import factory
ROOT=Path(__file__).resolve().parents[1]
BRANCH="codex/app-cohort-image-inventory-20261028"
SLUG="offline-image-inventory-desk"
ISSUES=(("pwyq","Fabricum",29),("cemfirat","mediarama",91))
def cmd(*args,**kwargs):return subprocess.run(args,check=True,text=True,**kwargs)
def market():
    signals=[]
    for owner,repo,num in ISSUES:
        url=f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"
        headers={"Accept":"application/vnd.github+json","User-Agent":"ImageInventory-Factory/1"}
        if os.environ.get("GITHUB_TOKEN"):headers["Authorization"]="Bearer "+os.environ["GITHUB_TOKEN"]
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20) as response:
            raw=response.read(100001)
        if len(raw)>100000:raise ValueError("Oversized issue evidence")
        issue=json.loads(raw)
        exact=f"https://github.com/{owner}/{repo}/issues/{num}"
        if issue.get("html_url")!=exact or not issue.get("title"):raise ValueError("Unverified issue")
        signals.append({"url":exact,"title":str(issue["title"])[:140],"excerpt":str(issue.get("body") or "")[:350]})
    return {"schema":1,"kind":"app","signals":signals,"note":"Untrusted weak research signals"}
def run():
    if os.environ.get("GITHUB_REF")!="refs/heads/"+BRANCH:raise ValueError("Wrong branch")
    initial=cmd("git","rev-parse","HEAD",capture_output=True).stdout.strip()
    if initial!=os.environ.get("GITHUB_SHA"):raise ValueError("Checkout/event mismatch")
    if cmd("git","symbolic-ref","--quiet","--short","HEAD",capture_output=True).stdout.strip()!=BRANCH:
        raise ValueError("Wrong checked-out branch")
    if cmd("git","status","--porcelain",capture_output=True).stdout.strip():raise ValueError("Dirty checkout")
    cfg,state=factory.settings(ROOT)
    expected={"schema":1,"kind":"app","stage":"research","cycle":1,"revision":0,"slug":None}
    if cfg["kind"]!="app" or state!=expected:raise ValueError("Not an initial research state")
    candidate=ROOT/".candidate"
    proposal=json.loads((candidate/"proposal.json").read_text(encoding="utf-8"))
    urls=[f"https://github.com/{o}/{r}/issues/{n}" for o,r,n in ISSUES]
    if proposal.get("slug")!=SLUG or proposal.get("evidence_urls")!=urls:raise ValueError("Proposal mismatch")
    product=candidate/"product"
    for rel in ("main.py","manifest.json","README.md","tests/test_smoke.py"):
        if not (product/rel).is_file():raise ValueError("Candidate code missing: "+rel)
    (ROOT/".runtime").mkdir(exist_ok=True)
    factory.save(ROOT/".runtime/market.json",market())
    with tempfile.TemporaryDirectory(prefix="image-candidate-") as temp:
        parked=Path(temp)/"product"
        shutil.move(str(product),str(parked))
        try:
            assert factory.plan(ROOT)["stage"]=="research"
            assert factory.validate(ROOT)=={"stage":"research","slug":SLUG}
            assert factory.promote(ROOT)=={"stage":"research","slug":SLUG}
        finally:shutil.move(str(parked),str(product))
    if (candidate/"proposal.json").exists():raise ValueError("Stale research proposal")
    assert factory.plan(ROOT)["stage"]=="build"
    assert factory.validate(ROOT)=={"stage":"build","slug":SLUG}
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    result=cmd(sys.executable,"-m","unittest","discover","-s","tests","-v",
               cwd=product,capture_output=True,env=env,timeout=120)
    if "Ran 23 tests in" not in result.stderr or "skipped=" in result.stderr:
        raise ValueError("23 unskipped product tests not proven")
    print(result.stderr,flush=True)
    assert factory.promote(ROOT)=={"stage":"build","slug":SLUG}
    if factory.settings(ROOT)[1]["stage"]!="improve":raise ValueError("Promotion failed")
    for rel in ("main.py","manifest.json","README.md","tests/test_smoke.py"):
        if not (ROOT/"products"/SLUG/rel).is_file():raise ValueError("Promoted source missing")
    cmd(sys.executable,"-m","unittest","discover","-s","tests","-v",cwd=ROOT,env=env,timeout=180)
    cmd("git","add","-u","--",".candidate/proposal.json")
    cmd("git","add","--","factory/state.json",f"proposals/{SLUG}.json",f"products/{SLUG}")
    changed=cmd("git","diff","--cached","--name-only",capture_output=True).stdout.splitlines()
    allowed={"factory/state.json",".candidate/proposal.json",f"proposals/{SLUG}.json"}
    if not changed or any(p not in allowed and not p.startswith(f"products/{SLUG}/") for p in changed):
        raise ValueError("Unexpected staged files "+repr(changed))
    cmd("git","diff","--cached","--check")
    cmd("git","-c","user.name=github-actions[bot]",
        "-c","user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit","-m","feat(image-inventory): promote fifth real APP through Factory")
    remote=cmd("git","ls-remote","origin","refs/heads/"+BRANCH,capture_output=True).stdout.split()[0]
    if remote!=initial:raise ValueError("Remote changed; no blind overwrite")
    cmd("git","push","origin","HEAD:refs/heads/"+BRANCH)
    sha=cmd("git","rev-parse","HEAD",capture_output=True).stdout.strip()
    request="app-offline-image-inventory-desk-"+sha[:12]
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
            f.write(f"source_sha={sha}\nrequest_id={request}\n")
    print(json.dumps({"FACTORY_PRODUCT_GENERATED":True,"slug":SLUG,"source_branch":BRANCH,
                      "source_sha":sha,"request_id":request,"product_tests":23}))
if __name__=="__main__":run()
