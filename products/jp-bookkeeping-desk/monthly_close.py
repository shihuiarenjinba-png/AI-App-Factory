from __future__ import annotations
import csv, html, json, shutil, subprocess
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

def export_month_end_package(store,year,month,out_dir):
    year,month=int(year),int(month);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);stem=f"{year:04d}-{month:02d}"
    journal=_month_journal(store,year,month);trial=store.trial();pnl=store.pnl();bs=store.bs();balance=store.balance_check()
    csv_path=out/f"{stem}_仕訳明細.csv"
    with csv_path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f);w.writerow(["日付","摘要","科目コード","勘定科目","借方","貸方"])
        for r in sorted(journal,key=lambda x:(x["entry_date"],x["id"])):
            w.writerow([r["entry_date"],r["description"],r["code"],r["name"],r["debit_yen"],r["credit_yen"]])
    data={"year":year,"month":month,"journal_lines":len(journal),"pnl":pnl,"balance_sheet":bs,"balance_check":balance}
    json_path=out/f"{stem}_月次締め.json";json_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    jrows="".join(
        f"<tr><td>{html.escape(str(r['entry_date']))}</td><td>{html.escape(str(r['description']))}</td><td>{html.escape(str(r['code']))} {html.escape(str(r['name']))}</td><td class='num'>{int(r['debit_yen']):,}</td><td class='num'>{int(r['credit_yen']):,}</td></tr>"
        for r in sorted(journal,key=lambda x:(x["entry_date"],x["id"]))
    ) or "<tr><td colspan='5'>仕訳なし</td></tr>"
    trows="".join(f"<tr><td>{html.escape(str(r['code']))}</td><td>{html.escape(str(r['name']))}</td><td class='num'>{int(r['debit']):,}</td><td class='num'>{int(r['credit']):,}</td></tr>" for r in trial if r["debit"] or r["credit"])
    doc=f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{stem} 月次締め</title>
<style>@page{{size:A4;margin:12mm}}body{{font-family:"Yu Gothic","Meiryo",sans-serif;font-size:10pt}}table{{width:100%;border-collapse:collapse;margin:8px 0 18px}}th,td{{border:1px solid #999;padding:5px}}th{{background:#eee}}.num{{text-align:right}}.ok{{font-weight:bold}}</style></head><body>
<h1>{year}年{month}月 月次締めパック</h1>
<p class="ok">借貸一致: {'OK' if balance['balanced'] else '要確認'} / 差額 {balance['difference']:,}円</p>
<h2>損益</h2><p>収益 {pnl['収益']:,}円 / 費用 {pnl['費用']:,}円 / 利益 {pnl['利益']:,}円</p>
<h2>貸借対照</h2><p>資産 {bs['資産']:,}円 / 負債 {bs['負債']:,}円 / 純資産 {bs['純資産']:,}円 / 当期利益 {bs['当期利益']:,}円</p>
<h2>試算表</h2><table><tr><th>コード</th><th>科目</th><th>借方</th><th>貸方</th></tr>{trows}</table>
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
