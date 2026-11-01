from __future__ import annotations
import csv, html, json, shutil, subprocess
from pathlib import Path

def _edge_path():
    for name in ("msedge","msedge.exe"):
        p=shutil.which(name)
        if p:return p
    candidates=[
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in candidates:
        if p.exists():return str(p)
    return None

def _rows_for_month(store,year,month):
    """Read the complete selected month, never a UI-limited 10,000-row preview."""
    prefix=f"{int(year):04d}-{int(month):02d}-%"
    return [dict(row) for row in store.conn.execute(
        """SELECT id,txn_date,kind,amount_yen,category,counterparty,
                  document_type,document_path,memo
           FROM transactions WHERE txn_date LIKE ? ORDER BY txn_date,id""",
        (prefix,)
    )]

def export_month_end_package(store,year,month,out_dir):
    year,month=int(year),int(month)
    if not (1900 <= year <= 9999 and 1 <= month <= 12):
        raise ValueError("年または月が正しくありません")
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    stem=f"{year:04d}-{month:02d}"
    rows=_rows_for_month(store,year,month)
    summary=store.monthly(year,month)
    # Do not mix revenue and expenses in a single category total.
    categories={}
    for r in rows:
        key=f'{r["kind"]} / {r["category"]}'
        categories[key]=categories.get(key,0)+int(r["amount_yen"])
    for kind in ("収入","経費"):
        detail_total=sum(int(r["amount_yen"]) for r in rows if r["kind"]==kind)
        if detail_total != summary[kind]:
            raise ValueError("月次合計と取引明細が一致しません。出力を中止しました")
    # A 1,000-item UI preview must not silently truncate a legal review pack.
    pending=[dict(r) for r in store.conn.execute(
        """SELECT id,file_path,status,suggested_category,note,created_at
           FROM receipt_queue WHERE status='PENDING' ORDER BY id"""
    )]

    csv_path=out/f"{stem}_取引明細.csv"
    with csv_path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f)
        w.writerow(["日付","種別","金額(円)","勘定科目","取引先","証憑種別","証憑参照","摘要"])
        for r in sorted(rows,key=lambda x:(x["txn_date"],x["id"])):
            w.writerow([r["txn_date"],r["kind"],r["amount_yen"],r["category"],r["counterparty"],r["document_type"],r["document_path"],r["memo"]])

    data={
        "year":year,"month":month,"summary":summary,
        "categories":dict(sorted(categories.items())),
        "transaction_count":len(rows),
        "pending_receipts":pending,
        "pending_receipt_count":len(pending),
    }
    json_path=out/f"{stem}_月次総括.json"
    json_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

    trs="".join(
        f"<tr><td>{html.escape(str(r['txn_date']))}</td><td>{html.escape(str(r['kind']))}</td>"
        f"<td class='num'>{int(r['amount_yen']):,}</td><td>{html.escape(str(r['category']))}</td>"
        f"<td>{html.escape(str(r['counterparty']))}</td><td>{html.escape(str(r['memo']))}</td></tr>"
        for r in sorted(rows,key=lambda x:(x["txn_date"],x["id"]))
    ) or "<tr><td colspan='6'>取引なし</td></tr>"
    cats="".join(f"<tr><td>{html.escape(k)}</td><td class='num'>{v:,}</td></tr>" for k,v in sorted(categories.items()))
    pend="".join(f"<li>{html.escape(str(x['file_path']))}</li>" for x in pending) or "<li>なし</li>"
    doc=f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{stem} 月次帳簿</title>
<style>@page{{size:A4;margin:12mm}}body{{font-family:"Yu Gothic","Meiryo",sans-serif;font-size:10pt}}h1,h2{{margin:.4em 0}}table{{width:100%;border-collapse:collapse;margin:8px 0 18px}}th,td{{border:1px solid #999;padding:5px}}th{{background:#eee}}.num{{text-align:right}}.note{{font-size:9pt;color:#444}}</style>
</head><body>
<h1>{year}年{month}月 月次帳簿パック</h1>
<p>収入 {summary['収入']:,}円 / 経費 {summary['経費']:,}円 / 差引 {summary['差引']:,}円 / 取引 {len(rows)}件</p>
<h2>科目別集計</h2><table><tr><th>勘定科目</th><th>金額</th></tr>{cats}</table>
<h2>取引明細</h2><table><tr><th>日付</th><th>種別</th><th>金額</th><th>科目</th><th>取引先</th><th>摘要</th></tr>{trs}</table>
<h2>未処理証憑（{len(pending)}件）</h2><ul>{pend}</ul>
<p class="note">このPDFは月次確認用です。電子取引で受領した元の請求書・領収書データは別途保存してください。税務上の必要経費該当性は未確認項目を含む場合があります。</p>
</body></html>"""
    html_path=out/f"{stem}_月次帳簿.html";html_path.write_text(doc,encoding="utf-8")

    pdf_path=out/f"{stem}_月次帳簿.pdf"
    edge=_edge_path();pdf_ok=False
    if edge:
        try:
            cp=subprocess.run([edge,"--headless","--disable-gpu","--no-pdf-header-footer",f"--print-to-pdf={pdf_path}",html_path.resolve().as_uri()],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
            pdf_ok=(cp.returncode==0 and pdf_path.exists() and pdf_path.stat().st_size>0)
        except Exception:
            pdf_ok=False
    return {"html":str(html_path),"csv":str(csv_path),"json":str(json_path),"pdf":str(pdf_path) if pdf_ok else None,"pdf_generated":pdf_ok}
