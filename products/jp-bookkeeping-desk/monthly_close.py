from __future__ import annotations
import calendar, csv, html, json, shutil, subprocess
from pathlib import Path

def _edge_path():
    for name in ("msedge","msedge.exe"):
        p=shutil.which(name)
        if p:return p
    for p in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")):
        if p.exists():return str(p)
    return None

def _month_journal(store,year,month):
    prefix=f"{int(year):04d}-{int(month):02d}-"
    return [r for r in store.journal() if str(r["entry_date"]).startswith(prefix)]

def _pnl_from_lines(lines):
    revenue=expense=0
    for row in lines:
        if row["type"]=="収益":
            revenue+=int(row["credit_yen"])-int(row["debit_yen"])
        elif row["type"]=="費用":
            expense+=int(row["debit_yen"])-int(row["credit_yen"])
    return {"収益":revenue,"費用":expense,"利益":revenue-expense}


def _trial_as_of(store,lines):
    # Existing Store.trial() is all-time; only reuse its account metadata.
    trial=[{"code":r["code"],"name":r["name"],"type":r["type"],
            "debit":0,"credit":0} for r in store.trial()]
    lookup={r["code"]:r for r in trial}
    for line in lines:
        row=lookup.get(line["code"])
        if row is None:
            raise ValueError("過去の仕訳に無効な勘定科目があります。帳簿を確認してください")
        row["debit"]+=int(line["debit_yen"])
        row["credit"]+=int(line["credit_yen"])
    return trial


def _balance_sheet(trial,year_to_date_profit,prior_unclosed_profit):
    assets=liabilities=equity=0
    for row in trial:
        net=row["debit"]-row["credit"]
        if row["type"]=="資産":assets+=net
        elif row["type"]=="負債":liabilities-=net
        elif row["type"]=="純資産":equity-=net
    return {"資産":assets,"負債":liabilities,"純資産":equity,
            "当期利益":year_to_date_profit,
            "前期以前の未振替損益":prior_unclosed_profit,
            "負債純資産合計":liabilities+equity+year_to_date_profit+prior_unclosed_profit}


def export_month_end_package(store,year,month,out_dir):
    year,month=int(year),int(month)
    if not 1<=year<=9999 or not 1<=month<=12:
        raise ValueError("対象年月を確認してください")
    last_day=calendar.monthrange(year,month)[1]
    stem=f"{year:04d}-{month:02d}"
    start=f"{stem}-01";cutoff=f"{stem}-{last_day:02d}";year_start=f"{year:04d}-01-01"
    all_lines=store.journal()
    journal=[r for r in all_lines if start<=r["entry_date"]<=cutoff]
    as_of=[r for r in all_lines if r["entry_date"]<=cutoff]
    ytd=[r for r in as_of if r["entry_date"]>=year_start]
    prior=[r for r in as_of if r["entry_date"]<year_start]
    trial=_trial_as_of(store,as_of)
    pnl=_pnl_from_lines(ytd)
    pnl_month=_pnl_from_lines(journal)
    bs=_balance_sheet(trial,pnl["利益"],_pnl_from_lines(prior)["利益"])
    debits=sum(r["debit"] for r in trial);credits=sum(r["credit"] for r in trial)
    month_debits=sum(int(r["debit_yen"]) for r in journal)
    month_credits=sum(int(r["credit_yen"]) for r in journal)
    balance={"debits":debits,"credits":credits,"balanced":debits==credits,
             "difference":debits-credits,"bs_balanced":bs["資産"]==bs["負債純資産合計"]}
    month_balance={"debits":month_debits,"credits":month_credits,
                   "balanced":month_debits==month_credits,
                   "difference":month_debits-month_credits}
    pending_receipts=int(store.conn.execute(
        "SELECT COUNT(*) FROM receipt_queue WHERE status!='POSTED'").fetchone()[0])
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    csv_path=out/f"{stem}_仕訳明細.csv"
    with csv_path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f);w.writerow(["日付","摘要","科目コード","勘定科目","借方","貸方"])
        for r in sorted(journal,key=lambda x:(x["entry_date"],x["id"])):
            w.writerow([r["entry_date"],r["description"],r["code"],r["name"],r["debit_yen"],r["credit_yen"]])
    data={"year":year,"month":month,"period_start":start,"as_of_date":cutoff,
          "journal_lines":len(journal),"trial_balance_as_of":trial,
          "pnl":pnl,"pnl_year_to_date":pnl,"pnl_month":pnl_month,
          "balance_sheet":bs,"balance_check":balance,"month_balance_check":month_balance,
          "unprocessed_receipts":pending_receipts,"tax_filing_or_deduction_approved":False}
    json_path=out/f"{stem}_月次締め.json";json_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    jrows="".join(
        f"<tr><td>{html.escape(str(r['entry_date']))}</td><td>{html.escape(str(r['description']))}</td><td>{html.escape(str(r['code']))} {html.escape(str(r['name']))}</td><td class='num'>{int(r['debit_yen']):,}</td><td class='num'>{int(r['credit_yen']):,}</td></tr>"
        for r in sorted(journal,key=lambda x:(x["entry_date"],x["id"]))
    ) or "<tr><td colspan='5'>仕訳なし</td></tr>"
    trows="".join(f"<tr><td>{html.escape(str(r['code']))}</td><td>{html.escape(str(r['name']))}</td><td class='num'>{int(r['debit']):,}</td><td class='num'>{int(r['credit']):,}</td></tr>" for r in trial if r["debit"] or r["credit"])
    doc=f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{stem} 月次締め</title>
<style>@page{{size:A4;margin:12mm}}body{{font-family:"Yu Gothic","Meiryo",sans-serif;font-size:10pt}}table{{width:100%;border-collapse:collapse;margin:8px 0 18px}}th,td{{border:1px solid #999;padding:5px}}th{{background:#eee}}.num{{text-align:right}}.ok{{font-weight:bold}}</style></head><body>
<h1>{year}年{month}月 月次締めパック</h1>
<p>対象期間: {start} ～ {cutoff}。試算表・貸借対照表は {cutoff} 時点、損益は当月と当年累計を分けています。後日仕訳は含めません。</p>
<p class="ok">対象月の借貸一致: {'OK' if month_balance['balanced'] else '要確認'} / 月次差額 {month_balance['difference']:,}円</p>
<p class="ok">月末累計の借貸一致: {'OK' if balance['balanced'] else '要確認'} / 差額 {balance['difference']:,}円 / 貸借対照一致: {'OK' if balance['bs_balanced'] else '要確認'}</p>
<h2>当月損益</h2><p>収益 {pnl_month['収益']:,}円 / 費用 {pnl_month['費用']:,}円 / 利益 {pnl_month['利益']:,}円</p>
<h2>当年1月から対象月末までの累計損益</h2><p>収益 {pnl['収益']:,}円 / 費用 {pnl['費用']:,}円 / 利益 {pnl['利益']:,}円</p>
<h2>対象月末の貸借対照</h2><p>資産 {bs['資産']:,}円 / 負債 {bs['負債']:,}円 / 純資産 {bs['純資産']:,}円 / 当期利益 {bs['当期利益']:,}円 / 前期以前の未振替損益 {bs['前期以前の未振替損益']:,}円</p>
<h2>月末の確認事項</h2><p>未処理証憑 {pending_receipts}件。証憑原本・事業用途・私用按分・固定資産判定は人が確認してください。帳票は税務申告や控除可否を自動確定しません。</p>
<h2>月末時点の試算表</h2><table><tr><th>コード</th><th>科目</th><th>借方</th><th>貸方</th></tr>{trows}</table>
<h2>当月仕訳</h2><table><tr><th>日付</th><th>摘要</th><th>科目</th><th>借方</th><th>貸方</th></tr>{jrows}</table>
<p>電子取引で受領した証憑は元データも保存してください。この帳票は確認・共有用です。</p>
</body></html>"""
    html_path=out/f"{stem}_月次締め.html";html_path.write_text(doc,encoding="utf-8")
    pdf_path=out/f"{stem}_月次締め.pdf";edge=_edge_path();pdf_ok=False
    if edge:
        try:
            cp=subprocess.run([edge,"--headless","--disable-gpu","--no-pdf-header-footer",f"--print-to-pdf={pdf_path}",html_path.resolve().as_uri()],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
            pdf_ok=(cp.returncode==0 and pdf_path.exists() and pdf_path.stat().st_size>0)
        except Exception:pdf_ok=False
    return {"html":str(html_path),"csv":str(csv_path),"json":str(json_path),"pdf":str(pdf_path) if pdf_ok else None,"pdf_generated":pdf_ok}
