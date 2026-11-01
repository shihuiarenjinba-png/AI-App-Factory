"""Read-only, self-contained sample folders for first-run guided practice.

All writes occur under a newly created TemporaryDirectory owned by the GUI.
Never uses or modifies the user's source images or buyer response records.
"""
from pathlib import Path
import shutil
from buyer_validation_evidence import EXPECTED, make_png, image_hashes


def populate_demo(root):
    root=Path(root)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError("Demo root must be an empty new temporary directory")
    before,after=root/"baseline",root/"delivery"
    before.mkdir()
    after.mkdir()
    for name,rgb in (("same.png",(5,10,15)),
                     ("modified.png",(20,40,60)),
                     ("removed.png",(80,100,120))):
        make_png(before/name,rgb)
        shutil.copyfile(before/name,after/name)
    make_png(after/"modified.png",(200,10,20))
    (after/"removed.png").unlink()
    make_png(after/"added.png",(10,210,30))
    return before,after


def hashes(folder):
    return image_hashes(Path(folder))
