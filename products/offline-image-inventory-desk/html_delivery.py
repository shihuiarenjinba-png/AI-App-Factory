"""Offline, bounded, self-contained customer HTML delivery evidence.

No network, scripts, image edits, source writes or claimed image modification times.
Preview tiles embed only SHA-verified small original image bytes, scaled by CSS;
the baseline snapshot itself stores hashes, never image bytes.
"""
import base64
from datetime import datetime, timezone
import hashlib
import html
import os
from pathlib import Path
import stat

import snapshot_compare as snapshots

MAX_PREVIEW_BYTES = 96 * 1024
MAX_PREVIEW_TILES = 16
MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_PREVIEW_PIXELS = 8_000_000

WORDS = {
    "en": {
        "title": "Image delivery review", "created": "Report created (UTC)",
        "saved": "Report file", "summary": "Delivery changes",
        "added": "Added", "removed": "Removed", "modified": "Changed",
        "unchanged": "Unchanged", "before": "Before", "after": "After",
        "none": "No image preview available",
        "missing": "Baseline image unavailable: the snapshot keeps metadata, not a photo",
        "limit": "Preview omitted (format, size or preview limit)",
        "sha": "SHA-256 identifies scanned file bytes; it is not a signature or independent certification.",
        "time": "The timestamp is report creation time, NOT image modification or delivery time.",
        "scope": "Read-only comparison by relative filename. Renames appear as removal plus addition. Source images are not copied, edited or uploaded.",
        "review": "Review changed filenames and previews with the recipient. Unchanged items are included in counts.",
        "nochange": "No changed images.",
        "metadata": "Before / after SHA-256 and dimensions / bytes",
        "preview": "Scaled preview of verified local file bytes, not a pixel-difference analysis.",
    },
    "ja": {
        "title": "納品画像の確認レポート", "created": "レポート作成日時（UTC）",
        "saved": "保存ファイル", "summary": "納品画像の変更",
        "added": "追加", "removed": "削除", "modified": "変更",
        "unchanged": "変更なし", "before": "変更前", "after": "変更後",
        "none": "画像のプレビューはありません",
        "missing": "変更前画像は表示できません。記録には画像本体ではなく情報のみを保存しています",
        "limit": "形式・容量・表示数の制限によりプレビューを省略しました",
        "sha": "SHA-256は読み取ったファイル内容の識別値です。電子署名や第三者認証ではありません。",
        "time": "表示日時はレポート作成時刻であり、画像の更新・納品日時を証明しません。",
        "scope": "相対ファイル名で比較します。名前変更は削除と追加として表示します。元画像はコピー・編集・送信しません。",
        "review": "変更したファイルと画像の見本を納品先と確認してください。変更なしも件数に含みます。",
        "nochange": "変更した画像はありません。",
        "metadata": "変更前／変更後 SHA-256・寸法・容量",
        "preview": "確認済みローカル画像の縮小表示です。画素差分解析ではありません。",
    },
}


def _source_file(root_text, name, sha, expected_size, required, include_preview):
    """Verify current files even when previews are omitted. Old image bytes are optional."""
    root = Path(root_text).absolute()
    if root.is_symlink() or not root.is_dir():
        if not required and not root.exists():
            return None
        raise ValueError("Unsafe or inaccessible source folder")
    path = root.joinpath(*snapshots.relative(name).split("/"))
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Linked source path rejected")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        if required:
            raise ValueError("Current image missing; compare again")
        return None
    if root.resolve() not in resolved.parents:
        raise ValueError("Source path escapes folder")
    digest, details = snapshots.full_hash(path)
    if digest != sha or details.st_size != expected_size:
        if required:
            raise ValueError("Current image changed; compare again")
        return None
    if not include_preview or details.st_size > MAX_PREVIEW_BYTES:
        return None
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                 getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise ValueError("Image changed while preparing preview")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_PREVIEW_BYTES + 1)
        if (len(data) != expected_size or
                not snapshots.same_stat(before, os.fstat(fd)) or
                hashlib.sha256(data).hexdigest() != sha):
            raise ValueError("Image changed while preparing preview")
    finally:
        os.close(fd)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif data.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
    else:
        return None  # BMP and unrecognized formats: metadata only, never invented preview.
    return mime, base64.b64encode(data).decode("ascii")


def render_html_delivery(report, language="en", destination=None, generated_at=None):
    """Validate the existing evidence, reverify AFTER bytes, and render safe local HTML."""
    if language not in WORDS:
        raise ValueError("Unsupported language")
    # Reuse the strict report/count/hash/path validation from the TXT evidence.
    snapshots.render_delivery_summary(report, language, generated_at)
    words = WORDS[language]
    escape = lambda value: html.escape(str(value), quote=True)
    moment = generated_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("Timezone required")
    stamp = moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    counts = report["summary"]
    preview_count = 0
    sections = []
    for row in report["changes"]:
        status = row["status"]
        name = row["relative_path"]
        dimensions = row["new_dimensions"] or row["old_dimensions"]
        # Dimension bounds limit browser decode work; the preview is optional.
        try:
            width, height = map(int, dimensions.split("x"))
            pixels_ok = 0 < width * height <= MAX_PREVIEW_PIXELS
        except (ValueError, AttributeError):
            pixels_ok = False
        tiles = []
        for side in ("old", "new"):
            sha = row[side + "_sha256"]
            if not sha:
                continue
            required = side == "new"
            can_preview = (status != "UNCHANGED" and pixels_ok and
                           preview_count < MAX_PREVIEW_TILES)
            preview = _source_file(report["old_root"] if side == "old" else report["new_root"],
                                   name, sha, row[side + "_bytes"], required, can_preview)
            if preview is not None:
                mime, payload = preview
                preview_count += 1
                body = ('<img alt="' + escape(name) + '" src="data:' + mime +
                        ';base64,' + payload + '">')
            else:
                body = '<p class="muted">' + escape(
                    words["missing"] if side == "old" and can_preview else words["limit"]) + '</p>'
            tiles.append('<div class="tile"><strong>' + escape(words["before"] if side == "old" else words["after"]) +
                         '</strong>' + body + '</div>')
        label = words[{"ADDED": "added", "REMOVED": "removed", "MODIFIED": "modified",
                       "UNCHANGED": "unchanged"}[status]]
        detail = (escape(words["metadata"]) + ': ' +
                  escape(row["old_sha256"] or "—") + ' / ' +
                  escape(row["new_sha256"] or "—") + '<div class="muted">' +
                  escape(row["old_dimensions"] or "—") + ' / ' +
                  escape(row["new_dimensions"] or "—") + ' · ' +
                  escape(row["old_bytes"] if row["old_bytes"] != "" else "—") + ' / ' +
                  escape(row["new_bytes"] if row["new_bytes"] != "" else "—") + ' bytes</div>')
        sections.append('<article><div class="heading"><span class="pill ' + status.lower() +
                        '">' + escape(label) + '</span><h2>' + escape(name) +
                        '</h2></div><div class="previews">' + "".join(tiles) +
                        '</div><details><summary>' + escape(words["metadata"]) +
                        '</summary><p class="hash">' + detail + '</p></details></article>')
    totals = " · ".join(escape(words[k]) + " " + str(counts[s]) for k, s in (
        ("added", "ADDED"), ("removed", "REMOVED"), ("modified", "MODIFIED"),
        ("unchanged", "UNCHANGED")))
    filename = Path(destination).name if destination else "report.html"
    page = ('''<!doctype html><html lang="''' + language + '''"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'">
<title>''' + escape(words["title"]) + '''</title><style>
body{font:16px/1.5 system-ui,"Segoe UI",sans-serif;margin:0;background:#f4f6fa;color:#172338}
main{max-width:960px;margin:auto;padding:20px}
header,article{background:white;border:1px solid #dce2ea;border-radius:12px;padding:18px;margin:0 0 14px}
h1{font-size:1.65rem;margin:0 0 8px}h2{font-size:1.05rem;margin:0;overflow-wrap:anywhere}
.heading{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.pill{border-radius:20px;padding:3px 10px;background:#dce8ff;font-weight:650}
.removed{background:#ffe1e1}.modified{background:#ffedc2}.unchanged{background:#e4ebec}
.previews{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:12px;margin-top:12px}
.tile{border:1px solid #dce2ea;padding:10px;border-radius:8px;min-width:0}
img{display:block;max-width:100%;width:auto;height:auto;max-height:160px;object-fit:contain;margin-top:8px}
.muted{color:#526277;font-size:.9rem}.hash{overflow-wrap:anywhere;font-size:.85rem}
summary{cursor:pointer}details{margin-top:12px}
@media(max-width:520px){main{padding:9px}header,article{padding:12px}}
@media print{body{background:white}header,article{break-inside:avoid}}
</style></head><body><main><header><h1>''' + escape(words["title"]) + '''</h1><p><strong>''' + escape(words["summary"]) + ''':</strong> ''' + totals + '''</p>
<p>''' + escape(words["created"]) + ''': ''' + escape(stamp) + '''</p>
<p>''' + escape(words["saved"]) + ''': ''' + escape(filename) + '''</p>
<p>''' + escape(words["review"]) + '''</p><p class="muted">''' +
        escape(words["scope"]) + ' ' + escape(words["time"]) + ' ' +
        escape(words["sha"]) + ' ' + escape(words["preview"]) +
        '''</p></header>''' + ("".join(sections) if sections else
                             '<article>' + escape(words["nochange"]) + '</article>') +
        '''</main></body></html>''')
    if len(page.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("HTML report exceeds safe size limit")
    return page
