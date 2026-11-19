"""Upload the ready-made reels from the local project to the release `queue` and write the queue files.

  make_queues.py podcast   → data/podcast_queue.json (Instagram + YouTube versions, in the posting-plan order)
  make_queues.py morning   → data/morning_queue.json (the dua/reminder reels, in order)
Already uploaded files are skipped (resumable). Needs GITHUB_TOKEN in the environment.
"""
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import queues as Q  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(r"C:\Users\t8646\OneDrive\Desktop\سوشيال")
LOCAL_CONF = PROJECT / "work" / "publisher" / "config.json"


def sec(txt, name):
    m = re.search(rf"=== {re.escape(name)} ===\n(.*?)(?=\n=== |\Z)", txt, re.S)
    return m.group(1).strip() if m else ""


def folder(base, cid):
    return next(d for d in sorted(base.iterdir()) if d.is_dir() and d.name.startswith(f"{cid} - "))


def existing():
    rel = Q.release("queue")
    return {a["name"] for a in rel.get("assets", [])}


def up(have, path, name, ctype):
    url = f"https://github.com/{Q.REPO}/releases/download/queue/{name}"
    if name in have:
        return url
    print("upload", name, f"{path.stat().st_size / 1e6:.0f} MB", flush=True)
    return Q.upload("queue", path, name, ctype)


def podcast():
    conf = json.loads(LOCAL_CONF.read_text(encoding="utf-8"))
    ig_base = PROJECT / conf["queues"]["instagram"]["folder"]
    yt_base = PROJECT / conf["queues"]["youtube"]["folder"]
    have, out = existing(), []
    qf = ROOT / "data" / "podcast_queue.json"
    for cid in conf["order"]:
        ig, yt = folder(ig_base, cid), folder(yt_base, cid)
        ig_txt = (ig / "نشر.txt").read_text(encoding="utf-8-sig")
        yt_txt = (yt / "نشر.txt").read_text(encoding="utf-8-sig")
        desc = sec(yt_txt, "الوصف")
        item = {"id": cid, "approved": True, "title": ig.name.split(" - ", 1)[1],
                "ig_asset": up(have, next(ig.glob("*.mp4")), f"podcast-{cid}-ig.mp4", "video/mp4"),
                "yt_asset": up(have, next(yt.glob("*.mp4")), f"podcast-{cid}-yt.mp4", "video/mp4"),
                "cover": up(have, ig / "غلاف.jpg", f"podcast-{cid}.jpg", "image/jpeg"),
                "caption": sec(ig_txt, "الكابشن"), "yt_title": sec(yt_txt, "العنوان")[:100], "yt_desc": desc[:4900],
                "tags": [t.lstrip("#") for t in re.findall(r"#\S+", desc)], "thumb_ms": 1500}
        out.append(item)
        qf.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")  # progress saved as we go
    print("podcast queue:", len(out))


def morning():
    spec = json.loads((PROJECT / "work" / "ayat_sadaqa.json").read_text(encoding="utf-8"))
    base = PROJECT / spec["out"]
    have, out = existing(), []
    for it in spec["items"]:
        d = folder(base, it["id"])
        txt = (d / "نشر.txt").read_text(encoding="utf-8-sig")
        thumb = (d / "thumb_ms.txt").read_text().strip() if (d / "thumb_ms.txt").is_file() else "1500"
        out.append({"id": it["id"], "approved": True, "title": it["hook"],
                    "ig_asset": up(have, next(d.glob("*.mp4")), f"morning-{it['id']}.mp4", "video/mp4"),
                    "cover": up(have, d / "غلاف.jpg", f"morning-{it['id']}.jpg", "image/jpeg"),
                    "caption": sec(txt, "الكابشن"), "thumb_ms": int(thumb)})
        (ROOT / "data" / "morning_queue.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("morning queue:", len(out))


if __name__ == "__main__":
    {"podcast": podcast, "morning": morning}[sys.argv[1]]()
