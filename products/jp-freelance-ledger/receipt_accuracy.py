from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass
class ReceiptTruth:
    doc_id: str
    date: str
    merchant: str
    total: str
    tax: str | None = None
    account: str | None = None
    high_risk: bool = False

@dataclass
class ReceiptPrediction:
    doc_id: str
    date: str | None = None
    merchant: str | None = None
    total: str | None = None
    tax: str | None = None
    account_candidates: tuple[str,...] = ()
    routed_to_review: bool = False
    auto_posted: bool = False

def _norm(v):
    return "" if v is None else " ".join(str(v).strip().lower().split())

def evaluate(truths: Iterable[ReceiptTruth], predictions: Iterable[ReceiptPrediction]):
    t={x.doc_id:x for x in truths}; p={x.doc_id:x for x in predictions}
    ids=sorted(set(t)&set(p))
    if not ids:
        return {"documents":0}
    date_ok=merchant_ok=total_ok=tax_ok=tax_n=top1=top3=acct_n=review_ok=review_n=unsafe=0
    for doc_id in ids:
        a,b=t[doc_id],p[doc_id]
        date_ok+=_norm(a.date)==_norm(b.date)
        merchant_ok+=_norm(a.merchant)==_norm(b.merchant)
        total_ok+=_norm(a.total)==_norm(b.total)
        if a.tax is not None:
            tax_n+=1;tax_ok+=_norm(a.tax)==_norm(b.tax)
        if a.account:
            acct_n+=1
            cand=[_norm(x) for x in b.account_candidates]
            top1+=bool(cand and cand[0]==_norm(a.account))
            top3+=_norm(a.account) in cand[:3]
        if a.high_risk:
            review_n+=1;review_ok+=bool(b.routed_to_review)
        if b.auto_posted and (a.high_risk or not a.account):
            unsafe+=1
    n=len(ids)
    pct=lambda x,d: None if d==0 else round(100*x/d,2)
    return {
        "documents":n,
        "tax_labeled_cases":tax_n,
        "account_labeled_cases":acct_n,
        "high_risk_cases":review_n,
        "date_exact_pct":pct(date_ok,n),
        "merchant_exact_pct":pct(merchant_ok,n),
        "total_exact_pct":pct(total_ok,n),
        "tax_exact_pct":pct(tax_ok,tax_n),
        "account_top1_pct":pct(top1,acct_n),
        "account_top3_pct":pct(top3,acct_n),
        "high_risk_review_recall_pct":pct(review_ok,review_n),
        "unsafe_auto_post_count":unsafe,
    }

def release_gate(metrics, *, benchmark_source=None):
    """Never certify OCR from synthetic or tiny example-only fixtures."""
    if benchmark_source != "user_owned_local_labeled":
        return {"pass":False,"reason":"verified local labeled benchmark required"}
    if (metrics.get("documents",0)<100 or metrics.get("tax_labeled_cases",0)<20
            or metrics.get("account_labeled_cases",0)<50
            or metrics.get("high_risk_cases",0)<20):
        return {"pass":False,"reason":"insufficient benchmark sample and risk coverage"}
    required=[
        metrics.get("date_exact_pct"),
        metrics.get("total_exact_pct"),
        metrics.get("account_top3_pct"),
        metrics.get("high_risk_review_recall_pct"),
    ]
    if any(v is None for v in required):
        return {"pass":False,"reason":"insufficient labeled benchmark coverage"}
    if metrics.get("unsafe_auto_post_count",1)!=0:
        return {"pass":False,"reason":"unsafe automatic posting observed"}
    if metrics["date_exact_pct"]<99 or metrics["total_exact_pct"]<99:
        return {"pass":False,"reason":"field extraction below target"}
    if metrics["account_top3_pct"]<95:
        return {"pass":False,"reason":"account suggestion below target"}
    if metrics["high_risk_review_recall_pct"]<99:
        return {"pass":False,"reason":"high-risk review routing below target"}
    return {"pass":True,"reason":"benchmark targets met"}
