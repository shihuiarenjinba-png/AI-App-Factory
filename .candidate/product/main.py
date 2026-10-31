"""Private offline image-header inventory. No image writes or network."""
import csv, io, json, os, shutil, stat, struct, tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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
"en":{"title":"Offline Image Inventory Desk","help":"Choose PNG/JPEG/GIF/BMP files. Inspect dimensions locally; no uploads or edits.","add":"Add images","remove":"Remove selected","clear":"Clear","save":"Save session","open":"Open session","export":"Export CSV","lang":"日本語","path":"File","format":"Format","dimensions":"Dimensions","bytes":"Bytes","ready":"Select images to begin.","empty":"Add images first.","saved":"Session saved.","loaded":"Session loaded.","exported":"CSV exported.","error":"Operation failed","recover":"Session invalid. Open backup?","replace":"Overwrite existing file? A backup is kept.","result":"Images: {n}; rejected: {bad}","preflight":"MSIX screenshot check","issues":"Issues only","check_export":"Export check CSV","check":"Check","notice":"Header-only check, not Store approval. Portrait and 50 MB limits need review.","summary":"MSIX check: {issues} need attention / {n} images. Desktop listing max: 10."},
"ja":{"title":"オフライン画像一覧デスク","help":"PNG/JPEG/GIF/BMPの画像寸法を端末内で確認します。送信や編集はしません。","add":"画像を追加","remove":"選択行を削除","clear":"消去","save":"作業を保存","open":"作業を開く","export":"CSVを書き出す","lang":"English","path":"ファイル","format":"形式","dimensions":"寸法","bytes":"バイト","ready":"画像を選んでください。","empty":"画像を追加してください。","saved":"保存しました。","loaded":"読み込みました。","exported":"CSVを書き出しました。","error":"操作に失敗しました","recover":"作業ファイルが無効です。バックアップを開きますか？","replace":"上書きしますか？バックアップを残します。","result":"画像：{n}件、拒否：{bad}件","preflight":"MSIX画像チェック","issues":"要確認のみ","check_export":"検査CSVを出力","check":"検査結果","notice":"ヘッダーのみの検査です。Store承認ではありません。縦長と50 MB境界は要確認。","summary":"MSIX検査：{n}件中{issues}件が要確認。デスクトップ画像は最大10枚。"}}

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

class Desk:
    def __init__(self,root):
        self.root=root;self.language="en";self.rows=[];self.status=tk.StringVar();self.preflight=tk.BooleanVar(value=False);self.issues=tk.BooleanVar(value=False)
        root.geometry("1024x768");root.minsize(850,600)
        body=ttk.Frame(root,padding=12);body.pack(fill="both",expand=True)
        self.heading=ttk.Label(body,font=("Segoe UI",18,"bold"));self.heading.pack(anchor="w")
        self.intro=ttk.Label(body,wraplength=950);self.intro.pack(anchor="w",pady=8)
        bar=ttk.Frame(body);bar.pack(fill="x",pady=6)
        self.buttons={}
        for key,fn in (("add",self.add),("remove",self.remove),("clear",self.clear),("save",self.save),("open",self.open),("export",self.export)):
            b=ttk.Button(bar,command=fn);b.pack(side="left",padx=(0,5));self.buttons[key]=b
        self.lang=ttk.Button(bar,command=self.toggle);self.lang.pack(side="right")
        checkbar=ttk.Frame(body);checkbar.pack(fill="x",pady=(2,4))
        self.preflight_box=ttk.Checkbutton(checkbar,variable=self.preflight,command=self.toggle_preflight)
        self.preflight_box.pack(side="left",padx=(0,12))
        self.issues_box=ttk.Checkbutton(checkbar,variable=self.issues,command=self.refresh)
        self.issues_box.pack(side="left",padx=(0,12))
        self.check_export_button=ttk.Button(checkbar,command=self.export_check)
        self.check_export_button.pack(side="left")
        self.notice=ttk.Label(body,wraplength=950);self.notice.pack(anchor="w")
        frame=ttk.Frame(body);frame.pack(fill="both",expand=True,pady=6)
        self.tree=ttk.Treeview(frame,columns=("path","format","dimensions","bytes","check"),show="headings",selectmode="extended")
        for k,width in (("path",395),("format",85),("dimensions",125),("bytes",100),("check",210)):
            self.tree.column(k,width=width,stretch=k=="path")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left",fill="both",expand=True);scroll.pack(side="right",fill="y")
        ttk.Label(body,textvariable=self.status,wraplength=950).pack(anchor="w",pady=4)
        self.localize();self.status.set(self.t("ready"))
    def t(self,key):return LABELS[self.language][key]
    def localize(self):
        self.root.title(self.t("title"));self.heading.configure(text=self.t("title"))
        self.intro.configure(text=self.t("help"));self.lang.configure(text=self.t("lang"))
        for k,b in self.buttons.items():b.configure(text=self.t(k))
        self.preflight_box.configure(text=self.t("preflight"))
        self.issues_box.configure(text=self.t("issues"))
        self.check_export_button.configure(text=self.t("check_export"))
        self.notice.configure(text=self.t("notice") if self.preflight.get() else "")
        for k in ("path","format","dimensions","bytes","check"):self.tree.heading(k,text=self.t(k))
    def toggle(self):
        self.language="ja" if self.language=="en" else "en";self.localize()
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

def main():
    root=tk.Tk();Desk(root);root.mainloop()
if __name__=="__main__":main()
