"""Private offline image-header inventory. No image writes or network."""
import csv, io, json, os, shutil, stat, struct, tempfile, webbrowser
from urllib.parse import urlsplit
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from user_preferences import load_language, save_language

MAX_BYTES=64*1024*1024
MAX_ITEMS=200
# Conservative, non-certifying MSIX desktop screenshot triage.
# Microsoft: PNG, landscape/portrait, desktop 1366x768+, up to 10, <=50 MB.
# Portrait dimension interpretation and MB byte boundary require manual review.
MSIX_PROFILE_URL="https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/screenshots-and-images"
MSIX_PROFILE_CHECKED="2026-10-31"
MSIX_DESKTOP_MAX_SCREENSHOTS=10

def check_msix_screenshot(row):
    """Return a triage code and actionable explanation; NEVER Store approval."""
    fmt,w,h,n=(row["format"],row["width"],row["height"],row["bytes"])
    if fmt!="PNG":
        return "FAIL_FORMAT","MSIX screenshots require PNG; select or export a PNG."
    if n>50*1024*1024:
        return "FAIL_SIZE","Larger than 50 MiB; exceeds either common 50 MB interpretation."
    if n>=50_000_000:
        return "REVIEW_SIZE_LIMIT","Near the 50 MB boundary; confirm Partner Center byte interpretation."
    if w<h:
        if max(w,h)<1366 or min(w,h)<768:
            return "FAIL_DIMENSIONS","Below the documented 1366 x 768 desktop minimum."
        return "REVIEW_PORTRAIT","Portrait is permitted; confirm how desktop minima apply to orientation."
    if w<1366 or h<768:
        return "FAIL_DIMENSIONS","Desktop screenshot should be at least 1366 x 768."
    return "BASIC_CANDIDATE","Header-only checks look plausible; visual content and upload still need review."

def msix_summary(rows):
    counts={}
    for row in rows:
        code,_=check_msix_screenshot(row)
        counts[code]=counts.get(code,0)+1
    return {"images":len(rows),"issues":len(rows)-counts.get("BASIC_CANDIDATE",0),
            "over_limit":len(rows)>MSIX_DESKTOP_MAX_SCREENSHOTS,"counts":counts}

LABELS={
"en":{"title":"Offline Image Inventory Desk","help":"Choose PNG/JPEG/GIF/BMP files. Inspect dimensions locally; no uploads or edits.","add":"Add images","remove":"Remove selected","clear":"Clear","save":"Save session","open":"Open session","export":"Export CSV","lang":"日本語","path":"File","format":"Format","dimensions":"Dimensions","bytes":"Bytes","ready":"Try the sample or record the original folder to begin.","empty":"Add images first.","saved":"Session saved.","loaded":"Session loaded.","exported":"CSV exported.","error":"Operation failed","recover":"Session invalid. Open backup?","replace":"Overwrite existing file? A backup is kept.","result":"Images: {n}; rejected: {bad}","preflight":"MSIX screenshot check","issues":"Issues only","check_export":"Export check CSV","check":"Check","notice":"Header-only check, not Store approval. Portrait and 50 MB limits need review.","summary":"MSIX check: {issues} need attention / {n} images. Desktop listing max: 10."},
"ja":{"title":"オフライン画像一覧デスク","help":"PNG/JPEG/GIF/BMPの画像寸法を端末内で確認します。送信や編集はしません。","add":"画像を追加","remove":"選択行を削除","clear":"消去","save":"作業を保存","open":"作業を開く","export":"CSVを書き出す","lang":"English","path":"ファイル","format":"形式","dimensions":"寸法","bytes":"バイト","ready":"見本を試すか、変更前のフォルダを記録してください。","empty":"画像を追加してください。","saved":"保存しました。","loaded":"読み込みました。","exported":"CSVを書き出しました。","error":"操作に失敗しました","recover":"作業ファイルが無効です。バックアップを開きますか？","replace":"上書きしますか？バックアップを残します。","result":"画像：{n}件、拒否：{bad}件","preflight":"MSIX画像チェック","issues":"要確認のみ","check_export":"検査CSVを出力","check":"検査結果","notice":"ヘッダーのみの検査です。Store承認ではありません。縦長と50 MB境界は要確認。","summary":"MSIX検査：{n}件中{issues}件が要確認。デスクトップ画像は最大10枚。"}}


import snapshot_compare as snapshots
import demo_samples
LABELS["en"].update({"snap_new":"1. Save folder snapshot","snap_open":"Open snapshot",
 "snap_compare":"2. Compare folder","snap_export":"3. Export evidence",
 "snap_intro":"Read-only delivery audit: save a baseline, compare later, export changes.",
 "snap_saved":"Snapshot saved outside the image folder.","snap_loaded":"Baseline loaded. Compare a folder.",
 "snap_none":"Save or open a baseline first.",
 "snap_result":"Added {ADDED} · Removed {REMOVED} · Changed {MODIFIED} · Same {UNCHANGED}",
 "snap_failed":"Some images could not be read. Comparison stopped to prevent false results.",
 "snap_report":"Image delivery changes (read-only)",
 "snap_summary":"Export delivery summary TXT","snap_summary_done":"Summary saved; images unchanged."})
LABELS["ja"].update({"snap_new":"1. フォルダを記録","snap_open":"記録を開く",
 "snap_compare":"2. フォルダを比較","snap_export":"3. 証跡を保存",
 "snap_intro":"画像納品の変更確認：最初の状態を記録し、後から比較します。画像は変更しません。",
 "snap_saved":"画像フォルダの外に記録を保存しました。","snap_loaded":"記録を読み込みました。比較するフォルダを選んでください。",
 "snap_none":"先にフォルダを記録するか、記録を開いてください。",
 "snap_result":"追加 {ADDED} · 削除 {REMOVED} · 変更 {MODIFIED} · 同じ {UNCHANGED}",
 "snap_failed":"読み取れない画像があります。誤った比較結果を防ぐため中止しました。",
 "snap_report":"納品画像の変更結果（読み取り専用）",
 "snap_summary":"納品用サマリーTXTを保存","snap_summary_done":"サマリーを保存しました。画像は変更していません。"})

LABELS["en"].update({
 "snap_demo":"Try a sample (4 changes)",
 "snap_demo_done":"SAMPLE ONLY: 1 added, 1 removed, 1 changed, 1 unchanged. Review the table, then export CSV/JSON or TXT. To use your own photos, start at step 1.",
 "snap_intro":"1. Save a BEFORE folder snapshot. 2. Compare the AFTER folder. 3. Export a client-readable CSV/JSON/TXT. Try the synthetic example first; no photos are uploaded or edited.",
 "snap_demo_title":"SAMPLE — image delivery changes (not your files)"
})
LABELS["ja"].update({
 "snap_demo":"見本で試す（4件の変更）",
 "snap_demo_done":"見本データです：追加1・削除1・変更1・同一1。表を確認し、CSV/JSON/TXTを保存できます。実際の画像は手順1から始めてください。",
 "snap_intro":"1. 変更前フォルダを記録 → 2. 変更後フォルダを比較 → 3. CSV/JSON/TXTの証跡を保存。見本から試せます。画像の送信・編集はしません。",
 "snap_demo_title":"見本 — 画像の変更結果（お客様の画像ではありません）"
})

LABELS["en"].update({
 "delivery_tab":"Delivery report", "inventory_tab":"Image list & advanced checks",
 "step_record":"Step 1 — Record the original folder",
 "step_compare":"Step 2 — Compare the delivered folder",
 "step_deliver":"Step 3 — Save the customer report",
 "snap_hint":"New here? Try the sample first. For a real delivery, save the original folder record, then compare the revised folder.",
 "delivery_note":"Images stay unchanged. Save a self-contained HTML report with verified image previews for your client. TXT/CSV/JSON remain available.",
 "snap_html":"Save client HTML with previews", "snap_html_done":"Client HTML saved at:", "snap_html_failed":"HTML was not saved. Compare the folder again.",
 "open_saved_html":"Open saved report", "saved_html_location":"Saved report:",
 "saved_html_missing":"The saved report is missing or unsafe. Save it again after comparing.",
 "saved_html_open_failed":"Could not open the local report. Check the file and try again."
})
LABELS["ja"].update({
 "delivery_tab":"納品レポート", "inventory_tab":"画像一覧・詳細検査",
 "step_record":"手順1 — 変更前のフォルダを記録",
 "step_compare":"手順2 — 納品後のフォルダを比較",
 "step_deliver":"手順3 — お客様向けレポートを保存",
 "snap_hint":"初めての方は見本から試せます。実際の納品では変更前を記録し、変更後のフォルダと比較してください。",
 "delivery_note":"元画像は変更しません。画像見本付きHTMLを納品先へ保存できます。TXT/CSV/JSONも引き続き利用できます。",
 "snap_html":"画像付きHTML納品書を保存", "snap_html_done":"HTMLを保存しました：", "snap_html_failed":"HTMLは保存できませんでした。フォルダを再比較してください。",
 "open_saved_html":"保存したレポートを開く", "saved_html_location":"保存先：",
 "saved_html_missing":"保存したレポートが見つからないか、安全に開けません。再比較して保存し直してください。",
 "saved_html_open_failed":"ローカルのレポートを開けませんでした。ファイルを確認してください。"
})

def local_report_uri(path):
    """Only open an existing regular local HTML file; reject UNC/network and links."""
    p = Path(path).absolute()
    if p.suffix.lower() != ".html" or p.is_symlink() or not p.is_file():
        raise ValueError("Missing or unsafe local HTML report")
    resolved = p.resolve(strict=True)
    uri = resolved.as_uri()
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc or not uri.startswith("file:///"):
        raise ValueError("Only local file URLs are allowed")
    return uri


def jpeg_dimensions(data):
    if not data.startswith(b"\xff\xd8"): raise ValueError("Invalid JPEG")
    i=2
    while i<len(data):
        if data[i]!=255: raise ValueError("Invalid JPEG marker")
        while i<len(data) and data[i]==255:i+=1
        if i>=len(data):break
        marker=data[i];i+=1
        if marker in (0xd8,0x01) or 0xd0<=marker<=0xd7:continue
        if marker in (0xd9,0xda):break
        if i+2>len(data):break
        length=int.from_bytes(data[i:i+2],"big")
        if length<2 or i+length>len(data):raise ValueError("Truncated JPEG")
        if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
            if length<7:raise ValueError("Invalid JPEG frame")
            return int.from_bytes(data[i+5:i+7],"big"),int.from_bytes(data[i+3:i+5],"big")
        i+=length
    raise ValueError("JPEG frame not found in first MiB")

def inspect_image(path):
    p=Path(path).absolute()
    if p.is_symlink():raise ValueError("Symlink rejected")
    st=p.stat()
    if not stat.S_ISREG(st.st_mode) or not 0<st.st_size<=MAX_BYTES:
        raise ValueError("Not a regular image within 64 MiB")
    with p.open("rb") as f:data=f.read(min(st.st_size,1048576))
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data)<24 or data[12:16]!=b"IHDR" or int.from_bytes(data[8:12],"big")!=13:
            raise ValueError("Invalid PNG")
        w,h=struct.unpack(">II",data[16:24]);fmt="PNG"
    elif data[:6] in (b"GIF87a",b"GIF89a"):
        if len(data)<10:raise ValueError("Invalid GIF")
        w,h=struct.unpack("<HH",data[6:10]);fmt="GIF"
    elif data.startswith(b"BM"):
        if len(data)<26 or int.from_bytes(data[14:18],"little")<40:raise ValueError("Invalid BMP")
        w,h=struct.unpack("<ii",data[18:26]);h=abs(h);fmt="BMP"
    elif data.startswith(b"\xff\xd8"):
        w,h=jpeg_dimensions(data);fmt="JPEG"
    else:raise ValueError("Unsupported image")
    if not 1<=w<=100000 or not 1<=h<=100000:raise ValueError("Invalid dimensions")
    return {"path":str(p),"format":fmt,"width":w,"height":h,"bytes":st.st_size}

def scan(paths):
    if not isinstance(paths,(tuple,list)) or len(paths)>MAX_ITEMS:raise ValueError("Too many images")
    rows=[];errors=[];seen=set()
    for item in paths:
        try:
            if not isinstance(item,(str,Path)):raise ValueError("Invalid path")
            p=Path(item).absolute()
            if len(str(p))>4096 or str(p) in seen:raise ValueError("Duplicate or oversized path")
            seen.add(str(p));rows.append(inspect_image(p))
        except (OSError,ValueError,struct.error) as exc:errors.append((str(item),str(exc)))
    return rows,errors

def append_images(existing, paths):
    """Append new files without rescanning or silently dropping saved inventory rows."""
    if not isinstance(existing, list) or not isinstance(paths, (list, tuple)):
        raise ValueError("Invalid inventory")
    if len(existing) + len(paths) > MAX_ITEMS:
        raise ValueError("Too many images")
    rows = list(existing)
    errors = []
    seen = {row["path"] for row in existing}
    for item in paths:
        try:
            if not isinstance(item, (str, Path)):
                raise ValueError("Invalid path")
            path = Path(item).absolute()
            if len(str(path)) > 4096 or str(path) in seen:
                raise ValueError("Duplicate or oversized path")
            seen.add(str(path))
            rows.append(inspect_image(path))
        except (OSError, ValueError, struct.error) as exc:
            errors.append((str(item), str(exc)))
    return rows, errors


def validate_session(value):
    if not isinstance(value,dict) or set(value)!={"schema","paths"} or type(value["schema"]) is not int or value["schema"]!=1:
        raise ValueError("Invalid session schema")
    paths=value["paths"]
    if not isinstance(paths,list) or len(paths)>MAX_ITEMS or any(not isinstance(p,str) or not p or len(p)>4096 or not Path(p).is_absolute() for p in paths) or len(set(paths))!=len(paths):
        raise ValueError("Invalid session paths")
    return value

def atomic_write(path,content,protected=()):
    p=Path(path).absolute();guard={Path(x).absolute() for x in protected}
    backup=p.with_name(p.name+".bak")
    if p in guard or backup in guard or p.is_symlink() or backup.is_symlink() or not p.parent.is_dir() or (p.exists() and not p.is_file()) or (backup.exists() and not backup.is_file()):
        raise ValueError("Unsafe output path")
    if p.exists():shutil.copyfile(p,backup)
    fd,tmp=tempfile.mkstemp(prefix=".image-inventory-",dir=p.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def save_session(path,rows):
    value=validate_session({"schema":1,"paths":[r["path"] for r in rows]})
    content=json.dumps(value,ensure_ascii=False,indent=2)+"\n"
    if len(content.encode("utf-8"))>1048576:raise ValueError("Session too large")
    atomic_write(path,content,[r["path"] for r in rows])

def load_session(path):
    p=Path(path).absolute()
    if p.is_symlink() or p.stat().st_size>1048576:raise ValueError("Unsafe session")
    return validate_session(json.loads(p.read_text(encoding="utf-8")))

def recover_session(path):
    p=Path(path).absolute()
    return load_session(p.with_name(p.name+".bak"))

def export_csv(path,rows):
    if not rows:raise ValueError("No images")
    output=io.StringIO(newline="");writer=csv.writer(output,lineterminator="\n")
    writer.writerow(["path","format","width","height","bytes"])
    for row in rows:writer.writerow([row[k] for k in ("path","format","width","height","bytes")])
    atomic_write(path,output.getvalue(),[r["path"] for r in rows])

def export_msix_csv(path,rows):
    """Export reproducible per-file triage without changing source images."""
    if not rows:raise ValueError("No images")
    output=io.StringIO(newline="");writer=csv.writer(output,lineterminator="\n")
    writer.writerow(["path","format","width","height","bytes","msix_check","action",
                     "profile_checked","profile_source","batch_count","desktop_limit"])
    for row in rows:
        code,reason=check_msix_screenshot(row)
        writer.writerow([row[k] for k in ("path","format","width","height","bytes")]+
                        [code,reason,MSIX_PROFILE_CHECKED,MSIX_PROFILE_URL,
                         len(rows),MSIX_DESKTOP_MAX_SCREENSHOTS])
    atomic_write(path,output.getvalue(),[r["path"] for r in rows])

CHANGE_LABELS = {
    "en": {"ADDED": "Added", "REMOVED": "Removed", "MODIFIED": "Changed", "UNCHANGED": "Unchanged"},
    "ja": {"ADDED": "追加", "REMOVED": "削除", "MODIFIED": "変更", "UNCHANGED": "変更なし"},
}

def comparison_view_rows(report, language, changes_only=False):
    """Customer-facing labels. Exported evidence retains full SHA-256 and exact codes."""
    if language not in CHANGE_LABELS:
        raise ValueError("Unsupported language")
    labels = CHANGE_LABELS[language]
    return [(row["relative_path"], labels[row["status"]],
             row["old_sha256"][:16] or "—", row["new_sha256"][:16] or "—")
            for row in report["changes"]
            if not changes_only or row["status"] != "UNCHANGED"]

LABELS["en"]["lang_save_failed"] = "Language changed for this session, but the preference could not be saved."
LABELS["ja"]["lang_save_failed"] = "この画面では言語を変更しましたが、次回起動用の設定を保存できませんでした。"

class Desk:
    def __init__(self,root):
        self.root=root;self.language=load_language();self.rows=[];self.status=tk.StringVar();self.preflight=tk.BooleanVar(value=False);self.issues=tk.BooleanVar(value=False);self.baseline=None;self.comparison=None;self.demo_temp=None;self.demo_mode=False;self.comparison_window=None;self.last_html_report_path=None;self.comparison_open_report_button=None;self.comparison_report_path_label=None
        root.geometry("1024x768");root.minsize(850,600)
        body=ttk.Frame(root,padding=10);body.pack(fill="both",expand=True)
        header=ttk.Frame(body);header.pack(fill="x")
        self.heading=ttk.Label(header,font=("Segoe UI",18,"bold"))
        self.heading.pack(side="left",anchor="w")
        self.lang=ttk.Button(header,command=self.toggle)
        self.lang.pack(side="right",padx=(8,0))
        self.intro=ttk.Label(body,wraplength=720,justify="left")
        self.intro.pack(anchor="w",fill="x",pady=(7,8))

        # First-run delivery workflow stays on the first tab; the legacy image
        # inventory and technical screenshot checks remain available separately.
        self.notebook=ttk.Notebook(body)
        self.notebook.pack(fill="both",expand=True)
        self.delivery_tab=ttk.Frame(self.notebook,padding=12)
        self.inventory_tab=ttk.Frame(self.notebook,padding=10)
        self.notebook.add(self.delivery_tab,text="Delivery report")
        self.notebook.add(self.inventory_tab,text="Image inventory")

        self.snapshot_intro=ttk.Label(self.delivery_tab,wraplength=680,justify="left")
        self.snapshot_intro.pack(anchor="w",fill="x",pady=(0,10))
        demo_row=ttk.Frame(self.delivery_tab);demo_row.pack(fill="x",pady=(0,10))
        self.demo_button=ttk.Button(demo_row,command=self.try_demo)
        self.demo_button.pack(side="left")

        self.snapshot_buttons={}
        step1=ttk.LabelFrame(self.delivery_tab,padding=10)
        step1.pack(fill="x",pady=(0,9))
        self.step1=step1
        for key,fn in (("snap_new",self.new_snapshot),("snap_open",self.open_snapshot)):
            button=ttk.Button(step1,command=fn)
            button.pack(side="left",padx=(0,8))
            self.snapshot_buttons[key]=button

        step2=ttk.LabelFrame(self.delivery_tab,padding=10)
        step2.pack(fill="x",pady=(0,9))
        self.step2=step2
        button=ttk.Button(step2,command=self.compare_folder)
        button.pack(side="left")
        self.snapshot_buttons["snap_compare"]=button

        step3=ttk.LabelFrame(self.delivery_tab,padding=10)
        step3.pack(fill="x",pady=(0,9))
        self.step3=step3
        step3_primary=ttk.Frame(step3);step3_primary.pack(fill="x",pady=(0,7))
        self.html_button=ttk.Button(step3_primary,command=self.export_delivery_html)
        self.html_button.pack(side="left",padx=(0,8))
        self.open_report_button=ttk.Button(step3_primary,command=self.open_saved_report,state="disabled")
        self.open_report_button.pack(side="left")
        self.report_path_label=ttk.Label(step3,wraplength=650,justify="left")
        self.report_path_label.pack(anchor="w",fill="x")
        step3_details=ttk.Frame(step3);step3_details.pack(fill="x")
        self.summary_button=ttk.Button(step3_details,command=self.export_delivery_summary)
        self.summary_button.pack(side="left",padx=(0,8))
        button=ttk.Button(step3_details,command=self.export_evidence)
        button.pack(side="left")
        self.snapshot_buttons["snap_export"]=button
        self.delivery_note=ttk.Label(self.delivery_tab,wraplength=680,justify="left")
        self.delivery_note.pack(anchor="w",fill="x",pady=(4,0))

        self.inventory_intro=ttk.Label(self.inventory_tab,wraplength=700,justify="left")
        self.inventory_intro.pack(anchor="w",fill="x",pady=(0,8))
        self.buttons={}
        # Two short rows replace the former six-button horizontal toolbar.
        for group in (("add","remove","clear"),("save","open","export")):
            bar=ttk.Frame(self.inventory_tab)
            bar.pack(fill="x",pady=(0,5))
            actions={"add":self.add,"remove":self.remove,"clear":self.clear,
                     "save":self.save,"open":self.open,"export":self.export}
            for key in group:
                b=ttk.Button(bar,command=actions[key])
                b.pack(side="left",padx=(0,6))
                self.buttons[key]=b
        checkbar=ttk.Frame(self.inventory_tab);checkbar.pack(fill="x",pady=(2,4))
        self.preflight_box=ttk.Checkbutton(checkbar,variable=self.preflight,command=self.toggle_preflight)
        self.preflight_box.pack(side="left",padx=(0,12))
        self.issues_box=ttk.Checkbutton(checkbar,variable=self.issues,command=self.refresh)
        self.issues_box.pack(side="left",padx=(0,12))
        self.check_export_button=ttk.Button(checkbar,command=self.export_check)
        self.check_export_button.pack(side="left")
        self.notice=ttk.Label(self.inventory_tab,wraplength=700,justify="left")
        self.notice.pack(anchor="w",fill="x")
        frame=ttk.Frame(self.inventory_tab)
        frame.pack(fill="both",expand=True,pady=6)
        self.tree=ttk.Treeview(frame,columns=("path","format","dimensions","bytes","check"),show="headings",selectmode="extended")
        for k,width in (("path",395),("format",85),("dimensions",125),("bytes",100),("check",210)):
            self.tree.column(k,width=width,stretch=k=="path")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left",fill="both",expand=True);scroll.pack(side="right",fill="y")
        self.status_label=ttk.Label(body,textvariable=self.status,wraplength=720,justify="left")
        self.status_label.pack(anchor="w",fill="x",pady=(7,0))
        body.bind("<Configure>",self._fit_labels,add="+")
        self.localize();self.status.set(self.t("ready"))
        root.bind("<Destroy>",self._cleanup_demo,add="+")

    def _fit_labels(self,event=None):
        # Adapt line wrapping to a 1024x768 viewport at 100/125/150% DPI.
        width=max(240,self.root.winfo_width()-90)
        for label in (self.intro,self.snapshot_intro,self.delivery_note,
                      self.inventory_intro,self.notice,self.status_label,self.report_path_label):
            label.configure(wraplength=width)

    def t(self,key):return LABELS[self.language][key]
    def localize(self):
        self.root.title(self.t("title"));self.heading.configure(text=self.t("title"))
        self.intro.configure(text=self.t("snap_intro"));self.lang.configure(text=self.t("lang"))
        self.notebook.tab(self.delivery_tab,text=self.t("delivery_tab"))
        self.notebook.tab(self.inventory_tab,text=self.t("inventory_tab"))
        self.step1.configure(text=self.t("step_record"))
        self.step2.configure(text=self.t("step_compare"))
        self.step3.configure(text=self.t("step_deliver"))
        self.snapshot_intro.configure(text=self.t("snap_hint"))
        self.delivery_note.configure(text=self.t("delivery_note"))
        self.inventory_intro.configure(text=self.t("help"))
        for k,b in self.buttons.items():b.configure(text=self.t(k))
        for k,b in self.snapshot_buttons.items():b.configure(text=self.t(k))
        self.html_button.configure(text=self.t("snap_html"))
        self.open_report_button.configure(text=self.t("open_saved_html"))
        self._update_saved_report_ui()
        self.summary_button.configure(text=self.t("snap_summary"))
        self.demo_button.configure(text=self.t("snap_demo"))
        self.preflight_box.configure(text=self.t("preflight"))
        self.issues_box.configure(text=self.t("issues"))
        self.check_export_button.configure(text=self.t("check_export"))
        self.notice.configure(text=self.t("notice") if self.preflight.get() else "")
        for k in ("path","format","dimensions","bytes","check"):self.tree.heading(k,text=self.t(k))

    def _update_saved_report_ui(self):
        path=getattr(self,"last_html_report_path",None)
        text=(self.t("saved_html_location")+" "+path.name+" — "+str(path.parent)) if path else ""
        for button_name in ("open_report_button","comparison_open_report_button"):
            button=getattr(self,button_name,None)
            if button is not None:
                try:
                    if button.winfo_exists():
                        button.configure(state="normal" if path is not None else "disabled")
                except (AttributeError,tk.TclError):
                    # Unit-test stubs and already-destroyed comparison windows are harmless.
                    button.configure(state="normal" if path is not None else "disabled")
        for label_name in ("report_path_label","comparison_report_path_label"):
            label=getattr(self,label_name,None)
            if label is not None:
                try:
                    if label.winfo_exists():
                        label.configure(text=text)
                except (AttributeError,tk.TclError):
                    label.configure(text=text)

    def _clear_saved_report(self):
        self.last_html_report_path=None
        self._update_saved_report_ui()

    def open_saved_report(self):
        path=self.last_html_report_path
        if path is None:
            return
        try:
            uri=local_report_uri(path)
        except (OSError,ValueError) as exc:
            self._clear_saved_report()
            self.status.set(self.t("saved_html_missing"))
            self.error(exc)
            return
        try:
            if not webbrowser.open(uri,new=2):
                raise OSError(self.t("saved_html_open_failed"))
        except (OSError,ValueError) as exc:
            self.status.set(self.t("saved_html_open_failed"))
            self.error(exc)

    def toggle(self):
        self.language="ja" if self.language=="en" else "en"
        self.localize()
        try:
            save_language(self.language)
        except OSError:
            self.status.set(self.t("lang_save_failed"))
            return
        if self.demo_mode:
            self.status.set(self.t("snap_demo_done"))
    def toggle_preflight(self):
        if not self.preflight.get():self.issues.set(False)
        self.localize();self.refresh()
    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        for i,r in enumerate(self.rows):
            code,_=check_msix_screenshot(r) if self.preflight.get() else ("NOT_CHECKED","")
            if self.preflight.get() and self.issues.get() and code=="BASIC_CANDIDATE":
                continue
            self.tree.insert("","end",iid=str(i),values=(
                r["path"],r["format"],str(r["width"])+" × "+str(r["height"]),
                str(r["bytes"]),code if self.preflight.get() else "—"))
        if self.preflight.get():
            summary=msix_summary(self.rows)
            self.status.set(self.t("summary").format(n=summary["images"],issues=summary["issues"]))
    def error(self,exc):messagebox.showerror(self.t("error"),str(exc),parent=self.root)
    def add(self):
        paths=filedialog.askopenfilenames(parent=self.root,title=self.t("add"),filetypes=[("Images","*.png *.jpg *.jpeg *.gif *.bmp"),("All","*.*")])
        if not paths:return
        try:rows,errors=append_images(self.rows,list(paths))
        except ValueError as exc:self.error(exc);return
        self.rows=rows;self.refresh();self.status.set(self.t("result").format(n=len(rows),bad=len(errors)))
        if errors:self.error("\n".join(f"{Path(p).name}: {e}" for p,e in errors[:8]))
    def remove(self):
        chosen={int(i) for i in self.tree.selection()}
        self.rows=[r for i,r in enumerate(self.rows) if i not in chosen];self.refresh()
        self.status.set(self.t("result").format(n=len(self.rows),bad=0))
    def clear(self):
        self.rows=[];self.refresh();self.status.set(self.t("empty"))
    def output(self,ext):
        return filedialog.asksaveasfilename(parent=self.root,defaultextension=ext,filetypes=[(ext.upper(),"*"+ext)])
    def confirm(self,path):
        return not Path(path).exists() or messagebox.askyesno(self.t("title"),self.t("replace"),parent=self.root)
    def save(self):
        if not self.rows:self.status.set(self.t("empty"));return
        path=self.output(".json")
        if not path or not self.confirm(path):return
        try:save_session(path,self.rows);self.status.set(self.t("saved"))
        except (OSError,ValueError,UnicodeError) as exc:self.error(exc)
    def open(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[("JSON","*.json")])
        if not path:return
        try:
            try:value=load_session(path)
            except (OSError,ValueError,UnicodeError,RecursionError):
                if not messagebox.askyesno(self.t("error"),self.t("recover"),parent=self.root):return
                value=recover_session(path)
            self.rows,errors=scan(value["paths"]);self.refresh()
            self.status.set(self.t("loaded")+" "+self.t("result").format(n=len(self.rows),bad=len(errors)))
            if errors:self.error("\n".join(f"{Path(p).name}: {e}" for p,e in errors[:8]))
        except (OSError,ValueError,UnicodeError,RecursionError) as exc:self.error(exc)
    def export_check(self):
        if not self.rows:self.status.set(self.t("empty"));return
        path=self.output(".csv")
        if not path or not self.confirm(path):return
        try:export_msix_csv(path,self.rows);self.status.set(self.t("exported"))
        except (OSError,ValueError,UnicodeError) as exc:self.error(exc)
    def export(self):
        if not self.rows:self.status.set(self.t("empty"));return
        path=self.output(".csv")
        if not path or not self.confirm(path):return
        try:export_csv(path,self.rows);self.status.set(self.t("exported"))
        except (OSError,ValueError,UnicodeError) as exc:self.error(exc)


    def _cleanup_demo(self,event):
        if event.widget is self.root and self.demo_temp is not None:
            self.demo_temp.cleanup()
            self.demo_temp=None

    def try_demo(self):
        """Demonstrate the exact three-step flow with synthetic temporary files."""
        self.close_comparison_window()
        self._clear_saved_report()
        self.comparison=None  # Never allow export of a stale real comparison.
        temp=tempfile.TemporaryDirectory(prefix="offline-image-demo-")
        try:
            before,after=demo_samples.populate_demo(Path(temp.name))
            original=(demo_samples.hashes(before),demo_samples.hashes(after))
            baseline=snapshots.capture_folder(before,inspect_image)
            current=snapshots.capture_folder(after,inspect_image)
            if baseline["errors"] or current["errors"]:
                raise ValueError(self.t("snap_failed"))
            report=snapshots.compare_snapshots(baseline,current)
            if report["summary"]!={"ADDED":1,"REMOVED":1,"MODIFIED":1,"UNCHANGED":1}:
                raise ValueError("Sample comparison mismatch")
            if original!=(demo_samples.hashes(before),demo_samples.hashes(after)):
                raise ValueError("Sample image SHA-256 changed")
        except (OSError,ValueError,UnicodeError,TypeError) as exc:
            temp.cleanup()
            self.error(exc)
            return
        if self.demo_temp is not None:
            self.demo_temp.cleanup()
        self.demo_temp=temp
        self.demo_mode=True
        self.baseline=baseline
        self.comparison=report
        self.status.set(self.t("snap_demo_done"))
        self.show_comparison(report)

    def new_snapshot(self):
        folder=filedialog.askdirectory(parent=self.root,title=self.t("snap_new"))
        if not folder:return
        self.close_comparison_window()
        self._clear_saved_report()
        self.comparison=None
        try:
            baseline=snapshots.capture_folder(folder,inspect_image)
            if baseline["errors"]:
                self.error(self.t("snap_failed")+"\n"+snapshots.describe_scan_errors(baseline["errors"],self.language));return
            path=filedialog.asksaveasfilename(parent=self.root,defaultextension=".json",
                filetypes=[("JSON","*.json")],title=self.t("snap_new"))
            if not path or not self.confirm(path):return
            snapshots.write_snapshot(path,baseline,atomic_write)
            self.baseline=baseline;self.comparison=None;self.demo_mode=False;self.status.set(self.t("snap_saved"))
        except (OSError,ValueError,UnicodeError,TypeError) as exc:self.error(exc)

    def open_snapshot(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[("JSON","*.json")],title=self.t("snap_open"))
        if not path:return
        self.close_comparison_window()
        self._clear_saved_report()
        self.comparison=None
        try:
            baseline=snapshots.load_snapshot(path)
            if baseline["errors"]:
                self.error(self.t("snap_failed"));return
            self.baseline=baseline;self.comparison=None;self.demo_mode=False;self.status.set(self.t("snap_loaded"))
        except (OSError,ValueError,UnicodeError,TypeError) as exc:self.error(exc)

    def compare_folder(self):
        if self.baseline is None:self.status.set(self.t("snap_none"));return
        folder=filedialog.askdirectory(parent=self.root,title=self.t("snap_compare"))
        if not folder:return
        # Never display or export a previous success after a later comparison fails.
        self.close_comparison_window()
        self._clear_saved_report()
        self.comparison=None
        try:
            current=snapshots.capture_folder(folder,inspect_image)
            if current["errors"]:
                self.status.set(self.t("snap_failed"))
                self.error(self.t("snap_failed")+"\n"+snapshots.describe_scan_errors(current["errors"],self.language));return
            report=snapshots.compare_snapshots(self.baseline,current)
            self.comparison=report
            self.status.set(self.t("snap_result").format(**report["summary"]))
            self.show_comparison(report)
        except (OSError,ValueError,UnicodeError,TypeError) as exc:self.error(exc)

    def close_comparison_window(self):
        window=self.comparison_window
        self.comparison_window=None
        self.comparison_open_report_button=None
        self.comparison_report_path_label=None
        if window is not None and window.winfo_exists():
            window.destroy()

    def show_comparison(self,report):
        self.close_comparison_window()
        window=tk.Toplevel(self.root)
        self.comparison_window=window
        window.title(self.t("snap_demo_title") if self.demo_mode else self.t("snap_report"))
        window.geometry("880x520")
        window.minsize(650,350)
        frame=ttk.Frame(window,padding=12)
        frame.pack(fill="both",expand=True)
        ttk.Label(frame,text=self.t("snap_result").format(**report["summary"]),
                  font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,6))
        guide=("Review changes and save a client-readable TXT or CSV/JSON evidence. "
               "The hashes shown are previews; exports contain full SHA-256."
               if self.language=="en" else
               "変更を確認し、納品先向けTXTまたはCSV/JSONの証跡を保存できます。"
               "画面のハッシュ値は短縮表示で、出力にはSHA-256全体が含まれます。")
        ttk.Label(frame,text=guide,wraplength=830).pack(anchor="w",pady=(0,6))
        actions=ttk.Frame(frame)
        actions.pack(fill="x",pady=(0,7))
        ttk.Button(actions,text=self.t("snap_html"),
                   command=self.export_delivery_html).pack(side="left",padx=(0,8))
        self.comparison_open_report_button=ttk.Button(
            actions,text=self.t("open_saved_html"),command=self.open_saved_report,state="disabled")
        self.comparison_open_report_button.pack(side="left",padx=(0,8))
        ttk.Button(actions,text=("Save TXT" if self.language=="en" else "TXTを保存"),
                   command=self.export_delivery_summary).pack(side="left",padx=(0,8))
        self.comparison_report_path_label=ttk.Label(frame,wraplength=830,justify="left")
        self.comparison_report_path_label.pack(anchor="w",fill="x",pady=(0,7))
        self._update_saved_report_ui()
        advanced_actions=ttk.Frame(frame);advanced_actions.pack(fill="x",pady=(0,7))
        ttk.Button(advanced_actions,text=("Export CSV / JSON" if self.language=="en" else "CSV / JSONを保存"),
                   command=self.export_evidence).pack(side="left",padx=(0,8))
        only_changes=tk.BooleanVar(value=True)
        table_frame=ttk.Frame(frame)
        table_frame.pack(fill="both",expand=True)
        table=ttk.Treeview(table_frame,columns=("file","change","before","after"),show="headings")
        for key,label,width in (("file",self.t("path"),280),
                                ("change","Change" if self.language=="en" else "変更内容",110),
                                ("before","Before SHA-256",190),("after","After SHA-256",190)):
            table.heading(key,text=label)
            table.column(key,width=width,stretch=key=="file")
        def redraw():
            for item in table.get_children():
                table.delete(item)
            for values in comparison_view_rows(report,self.language,only_changes.get()):
                table.insert("","end",values=values)
        ttk.Checkbutton(advanced_actions,text=("Changed files only" if self.language=="en" else "変更した画像のみ"),
                        variable=only_changes,command=redraw).pack(side="right")
        scroll=ttk.Scrollbar(table_frame,orient="vertical",command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side="left",fill="both",expand=True)
        scroll.pack(side="right",fill="y")
        redraw()

    def export_delivery_html(self):
        if self.comparison is None:self.status.set(self.t("snap_none"));return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension=".html",
                filetypes=[("HTML","*.html")],title=self.t("snap_html"))
        if not path or not self.confirm(path):return
        # A failed write must never leave a previous report marked as the latest.
        self._clear_saved_report()
        try:
            snapshots.write_html_delivery(path,self.comparison,atomic_write,self.language)
            local_report_uri(path)
            self.last_html_report_path=Path(path).absolute()
            self._update_saved_report_ui()
            self.status.set(self.t("snap_html_done")+" "+str(self.last_html_report_path))
        except (OSError,ValueError,UnicodeError,TypeError) as exc:
            # A changed or unreadable source invalidates the prior success.
            self.comparison=None
            self.close_comparison_window()
            self.status.set(self.t("snap_html_failed"))
            self.error(exc)

    def export_delivery_summary(self):
        if self.comparison is None:self.status.set(self.t("snap_none"));return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension=".txt",
                filetypes=[("Text","*.txt")],title=self.t("snap_summary"))
        if not path or not self.confirm(path):return
        try:
            snapshots.write_delivery_summary(path,self.comparison,atomic_write,self.language)
            self.status.set(self.t("snap_summary_done"))
        except (OSError,ValueError,UnicodeError,TypeError) as exc:self.error(exc)

    def export_evidence(self):
        if self.comparison is None:self.status.set(self.t("snap_none"));return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension=".csv",
                filetypes=[("CSV","*.csv"),("JSON","*.json")],title=self.t("snap_export"))
        if not path or not self.confirm(path):return
        try:
            snapshots.write_comparison(path,self.comparison,atomic_write)
            self.status.set(self.t("exported"))
        except (OSError,ValueError,UnicodeError,TypeError) as exc:self.error(exc)


def main():
    root=tk.Tk();Desk(root);root.mainloop()
if __name__=="__main__":main()
