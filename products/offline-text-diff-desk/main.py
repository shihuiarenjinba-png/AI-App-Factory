"""Offline Text Diff Desk: original private text comparison tool."""
import difflib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

LIMIT = 1048576
LINES = 10000
LABELS = {
"en": {"title":"Offline Text Diff Desk","help":"Compare two local UTF-8 documents. Nothing is uploaded or changed.",
"left":"Open left","right":"Open right","compare":"Compare","save":"Save session","open":"Open session",
"export":"Export diff","lang":"日本語","ignore":"Ignore whitespace","ready":"Choose two files to begin.",
"missing":"Choose both documents first.","same":"No differences with these options.","done":"Changed groups: {n}",
"saved":"Session saved.","loaded":"Session loaded.","exported":"Diff exported.","error":"Operation failed",
"recover":"Session damaged. Try backup?","replace":"Replace output? A backup will be kept.",
"leftlabel":"Left document","rightlabel":"Right document","diff":"Unified diff"},
"ja": {"title":"オフライン文章比較デスク","help":"ローカルのUTF-8文書を比較します。送信や元ファイルの変更はありません。",
"left":"左を開く","right":"右を開く","compare":"比較","save":"作業を保存","open":"作業を開く",
"export":"差分を書き出す","lang":"English","ignore":"空白の差を無視","ready":"左右のファイルを選択してください。",
"missing":"左右の文書を選択してください。","same":"差分はありません。","done":"変更グループ数：{n}",
"saved":"作業を保存しました。","loaded":"作業を読み込みました。","exported":"差分を書き出しました。","error":"操作に失敗しました",
"recover":"作業ファイルが破損しています。バックアップを開きますか？","replace":"上書きしますか？バックアップを残します。",
"leftlabel":"左の文書","rightlabel":"右の文書","diff":"統一差分"}}

def read_text(path):
    p = Path(path).absolute()
    if p.is_symlink():
        raise ValueError("Symbolic links are not allowed")
    st = p.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > LIMIT:
        raise ValueError("Not a regular UTF-8 text file of at most 1 MiB")
    raw = p.read_bytes()
    if len(raw) > LIMIT or b"\x00" in raw:
        raise ValueError("Oversized or binary file")
    result = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if len(result.splitlines()) > LINES:
        raise ValueError("Too many lines")
    return result

def compare(a, b, ignore=False, context=3):
    if type(ignore) is not bool or type(context) is not int or not 0 <= context <= 10:
        raise ValueError("Invalid comparison options")
    if not isinstance(a,str) or not isinstance(b,str):
        raise ValueError("Text required")
    left, right = a.splitlines(keepends=True), b.splitlines(keepends=True)
    if max(len(left),len(right)) > LINES:
        raise ValueError("Too many lines")
    if ignore:
        left = [" ".join(x.split())+"\n" for x in left]
        right = [" ".join(x.split())+"\n" for x in right]
    matcher = difflib.SequenceMatcher(None,left,right,autojunk=False)
    changes = sum(tag != "equal" for tag,*_ in matcher.get_opcodes())
    diff = "".join(difflib.unified_diff(left,right,fromfile="left",tofile="right",n=context))
    if len(diff) > 450000:
        raise ValueError("Diff too large")
    return {"diff":diff,"changes":changes,"same":changes==0}

def validate_session(value):
    if not isinstance(value,dict) or set(value)!={"schema","left","right","ignore","context"}:
        raise ValueError("Invalid session schema")
    if value["schema"]!=1 or type(value["ignore"]) is not bool:
        raise ValueError("Invalid session values")
    if type(value["context"]) is not int or not 0<=value["context"]<=10:
        raise ValueError("Invalid context")
    for key in ("left","right"):
        p=value[key]
        if not isinstance(p,str) or not p or len(p)>4096 or not Path(p).is_absolute():
            raise ValueError("Invalid path")
    return value

def make_session(left,right,ignore=False,context=3):
    return validate_session({"schema":1,"left":str(Path(left).absolute()),
                             "right":str(Path(right).absolute()),"ignore":ignore,"context":context})

def write_atomic(path, content, protected=()):
    p=Path(path).absolute()
    if p.is_symlink() or p in {Path(x).absolute() for x in protected}:
        raise ValueError("Unsafe output path")
    if p.exists() and not p.is_file():
        raise ValueError("Output must be a regular file")
    backup=p.with_name(p.name+".bak")
    if backup.is_symlink() or (backup.exists() and not backup.is_file()):
        raise ValueError("Unsafe backup")
    if not p.parent.is_dir():
        raise ValueError("Output folder missing")
    if p.exists():
        shutil.copyfile(p,backup)
    fd,tmp=tempfile.mkstemp(prefix=".text-diff-",dir=p.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def save_session(path,session):
    validate_session(session)
    write_atomic(path,json.dumps(session,ensure_ascii=False,indent=2)+"\n",
                 protected=(session["left"],session["right"]))

def load_session(path):
    p=Path(path).absolute()
    if p.is_symlink() or p.stat().st_size>LIMIT:
        raise ValueError("Invalid session file")
    return validate_session(json.loads(p.read_text(encoding="utf-8")))

def recover_session(path):
    p=Path(path).absolute()
    return load_session(p.with_name(p.name+".bak"))

def export_diff(path,result,left,right):
    if not isinstance(result,dict) or not isinstance(result.get("diff"),str):
        raise ValueError("Compare first")
    write_atomic(path,result["diff"] or "(no differences)\n",protected=(left,right))

class Desk:
    def __init__(self,root):
        self.root=root
        self.language="en"
        self.paths={"left":"","right":""}
        self.contents={"left":"","right":""}
        self.result=None
        self.ignore=tk.BooleanVar(value=False)
        self.status=tk.StringVar()
        root.geometry("1024x768")
        root.minsize(850,620)
        body=ttk.Frame(root,padding=12)
        body.pack(fill="both",expand=True)
        self.heading=ttk.Label(body,font=("Segoe UI",18,"bold"))
        self.heading.pack(anchor="w")
        self.intro=ttk.Label(body,wraplength=920)
        self.intro.pack(anchor="w",pady=(4,9))
        controls=ttk.Frame(body)
        controls.pack(fill="x")
        self.buttons={}
        for key,fn in (("left",lambda:self.choose("left")),("right",lambda:self.choose("right")),
                       ("compare",self.run_compare),("save",self.save),("open",self.open),
                       ("export",self.export)):
            btn=ttk.Button(controls,command=fn)
            btn.pack(side="left",padx=(0,5))
            self.buttons[key]=btn
        self.lang_button=ttk.Button(controls,command=self.toggle_language)
        self.lang_button.pack(side="right")
        self.ignore_button=ttk.Checkbutton(body,variable=self.ignore,command=self.invalidate)
        self.ignore_button.pack(anchor="w",pady=6)
        self.path_labels={}
        for key in ("left","right"):
            lbl=ttk.Label(body,wraplength=900)
            lbl.pack(anchor="w")
            self.path_labels[key]=lbl
        split=ttk.Panedwindow(body,orient="vertical")
        split.pack(fill="both",expand=True,pady=8)
        top=ttk.Frame(split)
        split.add(top,weight=2)
        self.views={}
        self.view_labels={}
        for key in ("left","right"):
            frame=ttk.Frame(top)
            frame.pack(side="left",fill="both",expand=True,padx=(0,5))
            label=ttk.Label(frame)
            label.pack(anchor="w")
            view=scrolledtext.ScrolledText(frame,wrap="none",font=("Consolas",10),height=8,state="disabled")
            view.pack(fill="both",expand=True)
            self.views[key]=view
            self.view_labels[key]=label
        bottom=ttk.Frame(split)
        split.add(bottom,weight=2)
        self.diff_label=ttk.Label(bottom)
        self.diff_label.pack(anchor="w")
        self.diff_view=scrolledtext.ScrolledText(bottom,wrap="none",font=("Consolas",10),height=10,state="disabled")
        self.diff_view.pack(fill="both",expand=True)
        ttk.Label(body,textvariable=self.status,wraplength=900).pack(anchor="w")
        root.bind("<Control-r>",lambda _:self.run_compare())
        root.bind("<Control-s>",lambda _:self.save())
        self.localize()
        self.status.set(self.t("ready"))

    def t(self,key):
        return LABELS[self.language][key]

    def localize(self):
        self.root.title(self.t("title"))
        self.heading.configure(text=self.t("title"))
        self.intro.configure(text=self.t("help"))
        for key,button in self.buttons.items():
            button.configure(text=self.t(key))
        self.lang_button.configure(text=self.t("lang"))
        self.ignore_button.configure(text=self.t("ignore"))
        for key in ("left","right"):
            self.view_labels[key].configure(text=self.t(key+"label"))
            self.path_labels[key].configure(text=self.paths[key] or self.t(key+"label")+": —")
        self.diff_label.configure(text=self.t("diff"))

    def toggle_language(self):
        self.language="ja" if self.language=="en" else "en"
        self.localize()

    def show(self,view,text):
        view.configure(state="normal")
        view.delete("1.0","end")
        view.insert("1.0",text)
        view.configure(state="disabled")

    def invalidate(self):
        self.result=None
        self.show(self.diff_view,"")

    def error(self,exc):
        messagebox.showerror(self.t("error"),str(exc),parent=self.root)

    def choose(self,key):
        path=filedialog.askopenfilename(parent=self.root,title=self.t(key))
        if not path:
            return
        try:
            content=read_text(path)
            self.paths[key]=str(Path(path).absolute())
            self.contents[key]=content
            self.show(self.views[key],content)
            self.invalidate()
            self.localize()
        except (OSError,ValueError,UnicodeError) as exc:
            self.error(exc)

    def run_compare(self):
        if not all(self.paths.values()):
            self.status.set(self.t("missing"))
            return
        try:
            self.result=compare(self.contents["left"],self.contents["right"],self.ignore.get())
            self.show(self.diff_view,self.result["diff"] or self.t("same"))
            self.status.set(self.t("done").format(n=self.result["changes"]))
        except (OSError,ValueError) as exc:
            self.error(exc)

    def save(self):
        if not all(self.paths.values()):
            self.status.set(self.t("missing"))
            return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension=".json",filetypes=[("JSON","*.json")])
        if not path:
            return
        if Path(path).exists() and not messagebox.askyesno(self.t("save"),self.t("replace"),parent=self.root):
            return
        try:
            save_session(path,make_session(self.paths["left"],self.paths["right"],self.ignore.get()))
            self.status.set(self.t("saved"))
        except (OSError,ValueError) as exc:
            self.error(exc)

    def open(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[("JSON","*.json")])
        if not path:
            return
        try:
            try:
                data=load_session(path)
            except (OSError,ValueError,UnicodeError,json.JSONDecodeError):
                if not messagebox.askyesno(self.t("error"),self.t("recover"),parent=self.root):
                    return
                data=recover_session(path)
            left=read_text(data["left"])
            right=read_text(data["right"])
            self.paths={"left":data["left"],"right":data["right"]}
            self.contents={"left":left,"right":right}
            self.ignore.set(data["ignore"])
            for key in ("left","right"):
                self.show(self.views[key],self.contents[key])
            self.invalidate()
            self.localize()
            self.status.set(self.t("loaded"))
        except (OSError,ValueError,UnicodeError,json.JSONDecodeError) as exc:
            self.error(exc)

    def export(self):
        if self.result is None:
            self.status.set(self.t("missing"))
            return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension=".diff",filetypes=[("Diff","*.diff")])
        if not path:
            return
        if Path(path).exists() and not messagebox.askyesno(self.t("export"),self.t("replace"),parent=self.root):
            return
        try:
            export_diff(path,self.result,self.paths["left"],self.paths["right"])
            self.status.set(self.t("exported"))
        except (OSError,ValueError) as exc:
            self.error(exc)

def main():
    root=tk.Tk()
    Desk(root)
    root.mainloop()

if __name__=="__main__":
    main()
