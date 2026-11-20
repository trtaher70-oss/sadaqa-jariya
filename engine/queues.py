"""Ready-made queues (already rendered reels hosted as GitHub release files) + the "next post" preview.

Queues (data/<name>.json, files in the release `queue`):
  morning_queue  — the hand-made dua/reminder reels (first cycle)
  podcast_queue  — podcast clips; published only when "approved": true (reviewed by a person)

Preview: after each publishing run, the NEXT reel of every slot is prepared in advance (rendered if needed),
uploaded to the release `preview`, and described in state/next.json for the dashboard. At publishing time the
prepared file is used as long as nothing changed — so what the dashboard shows is exactly what gets posted.
"""
import copy
import datetime as dt
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = os.environ.get("GITHUB_REPOSITORY", "trtaher70-oss/sadaqa-jariya")
QUEUES = {"morning_queue", "podcast_queue", "podcast"}
NEXT = ROOT / "state" / "next.json"


def qfile(stream):
    return ROOT / "data" / ("podcast_queue.json" if stream == "podcast" else f"{stream}.json")


def peek(stream, sst):
    """Next entry of a queue (no download), or None."""
    f = qfile(stream)
    if not f.is_file():
        return None
    done = set(sst.get("done", []))
    return next((x for x in json.loads(f.read_text(encoding="utf-8")) if x.get("approved", True) and x["id"] not in done), None)


def download(url, f):
    f.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=900) as r:
        r.raise_for_status()
        with open(f, "wb") as o:
            for ch in r.iter_content(1 << 16):
                o.write(ch)
    return f


def build_queue(stream, sst, wd):
    it = peek(stream, sst)
    if not it:
        return None
    ig = download(it["ig_asset"], wd / "ig.mp4")
    yt = download(it["yt_asset"], wd / "yt.mp4") if it.get("yt_asset") else ig
    sst.setdefault("done", []).append(it["id"])
    return {"mp4": ig, "mp4_yt": yt, "thumb_ms": it.get("thumb_ms", 1500), "caption": it["caption"],
            "yt_title": it.get("yt_title", it.get("title", ""))[:100], "yt_desc": it.get("yt_desc", it["caption"]),
            "tags": it.get("tags", []), "label": f"{stream} {it['id']}"}


# ------------------------------------------------------------------ release files
def _gh():
    tok = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"} if tok else None


def release(tag):
    h = _gh()
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}", headers=h, timeout=60)
    if r.status_code == 404:
        r = requests.post(f"https://api.github.com/repos/{REPO}/releases", headers=h, timeout=60,
                          json={"tag_name": tag, "name": tag, "body": "ملفات يستعملها النظام تلقائياً — لا تحذفها.", "prerelease": True})
    r.raise_for_status()
    return r.json()


def upload(tag, path, name, ctype):
    h = _gh()
    rel = release(tag)
    for a in rel.get("assets", []):
        if a["name"] == name:
            requests.delete(a["url"], headers=h, timeout=60)
    with open(path, "rb") as f:
        r = requests.post(rel["upload_url"].split("{")[0], params={"name": name}, data=f, timeout=900,
                          headers={**h, "Content-Type": ctype})
    r.raise_for_status()
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


# ------------------------------------------------------------------ preview of the next post
def light(src_url_or_path, slot, wd):
    """Small phone-friendly copy (540p) of a reel + its cover, uploaded as light-<slot>.mp4/.jpg (the dashboard
    site serves them as real video files — release files themselves are 'downloads' that phones refuse to play)."""
    import subprocess
    wd.mkdir(parents=True, exist_ok=True)
    src = Path(src_url_or_path) if not str(src_url_or_path).startswith("http") else download(src_url_or_path, wd / "src.mp4")
    out, jpg = wd / f"light-{slot}.mp4", wd / f"light-{slot}.jpg"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", "scale=540:-2", "-c:v", "libx264",
                    "-crf", "28", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.5", "-i", str(src), "-frames:v", "1",
                    "-vf", "scale=540:-2", "-q:v", "4", str(jpg)], check=True)
    upload("preview", out, out.name, "video/mp4")
    upload("preview", jpg, jpg.name, "image/jpeg")
def key(sst):
    return json.dumps(sst, sort_keys=True, ensure_ascii=False)


def next_date(slot, now):
    hh, mm = map(int, slot["time"].split(":"))
    d = now.date()
    if (now.hour, now.minute) >= (hh, mm):
        d += dt.timedelta(days=1)
    if slot.get("from") and d.isoformat() < slot["from"]:
        d = dt.date.fromisoformat(slot["from"])
    return d


def make_previews(st, schedule, builders, tz, only=None, occasion=None, extras=None, pool_builder=None):
    """Prepare the next reel of every slot (incl. occasion days and their extra posts); write state/next.json."""
    now = dt.datetime.now(tz)
    nxt = json.loads(NEXT.read_text(encoding="utf-8")) if NEXT.is_file() else {}
    stamp = now.strftime("%Y%m%d%H%M")
    plan = [(s, next_date(s, now)) for s in schedule["slots"]]
    if extras:  # extra occasion posts in the next 7 days (e.g. Friday's hour of answered prayer)
        seen = set()
        for i in range(8):
            d = now.date() + dt.timedelta(days=i)
            for e in extras(d):
                if e.get("stream") is None and e["name"] not in seen:
                    hh, mm = map(int, e["time"].split(":"))
                    if i == 0 and (now.hour, now.minute) >= (hh, mm) and st["slots"].get(e["name"]) == d.isoformat():
                        continue
                    seen.add(e["name"])
                    plan.append((e, d))
    live = set()
    for slot, day in plan:
        if only and slot["name"] != only:
            continue
        live.add(slot["name"])
        streams = copy.deepcopy(st["streams"])
        when = f"{day.isoformat()} {slot['time']}"
        pool, occ = occasion(slot, day) if occasion else (None, None)
        if pool and pool_builder:
            sst = streams.setdefault(f"pool:{pool}", {})
            before = key(sst)
            prev = nxt.get(slot["name"], {})
            if prev.get("before") == before and prev.get("stream") == f"pool:{pool}" and prev.get("full"):
                prev["when"] = when
                continue
            wd = ROOT / "work" / f"preview_{slot['name']}"
            try:
                item = pool_builder(pool, sst, wd)
                v = upload("preview", item["mp4"], f"{slot['name']}.mp4", "video/mp4")
                light(item["mp4"], slot["name"], wd)
                nxt[slot["name"]] = {"when": when, "stream": f"pool:{pool}", "occasion": occ, "label": item["label"],
                                     "title": item.get("yt_title", ""), "full": f"{v}?v={stamp}",
                                     "video": f"preview/{slot['name']}.mp4?v={stamp}", "cover": f"preview/{slot['name']}.jpg?v={stamp}",
                                     "caption": item["caption"], "stamp": stamp, "yt_title": item.get("yt_title", ""),
                                     "yt_desc": item.get("yt_desc", ""), "thumb_ms": item.get("thumb_ms", 1500),
                                     "before": before, "after": sst, "queue": False, "time": slot["time"]}
                continue
            except Exception as e:  # noqa: BLE001
                print(f"preview {slot['name']}: occasion {pool} not ready ({e})", flush=True)
                if slot.get("stream") is None:
                    nxt.pop(slot["name"], None)
                    continue
        if slot.get("stream") is None:
            continue
        for stream in [slot["stream"]] + slot.get("fallback", []):
            sst = streams.setdefault(stream, {})
            before = key(sst)
            if stream in QUEUES:
                it = peek(stream, sst)
                if not it:
                    continue
                prev = nxt.get(slot["name"], {})
                if prev.get("full") != it["ig_asset"]:
                    light(it["ig_asset"], slot["name"], ROOT / "work" / f"light_{slot['name']}")
                    prev = {"stamp": stamp}
                st_ = prev.get("stamp", stamp)
                nxt[slot["name"]] = {"when": when, "stream": stream, "label": f"{stream} {it['id']}", "title": it.get("title", ""),
                                     "full": it["ig_asset"], "video": f"preview/{slot['name']}.mp4?v={st_}",
                                     "cover": f"preview/{slot['name']}.jpg?v={st_}", "caption": it["caption"], "queue": True, "stamp": st_}
                break
            prev = nxt.get(slot["name"], {})
            if prev.get("before") == before and prev.get("full"):  # already prepared, nothing changed
                prev["when"] = when
                break
            wd = ROOT / "work" / f"preview_{slot['name']}"
            try:
                item = builders[stream](sst, wd)
            except Exception as e:  # noqa: BLE001 — one slot's problem never blocks the others
                print(f"preview {slot['name']}/{stream}: {e}", flush=True)
                item = None
            if not item:
                continue
            v = upload("preview", item["mp4"], f"{slot['name']}.mp4", "video/mp4")
            light(item["mp4"], slot["name"], wd)
            nxt[slot["name"]] = {"when": when, "stream": stream, "label": item["label"], "title": item.get("yt_title", ""),
                                 "full": f"{v}?v={stamp}", "video": f"preview/{slot['name']}.mp4?v={stamp}",
                                 "cover": f"preview/{slot['name']}.jpg?v={stamp}", "caption": item["caption"], "stamp": stamp,
                                 "yt_title": item.get("yt_title", ""), "yt_desc": item.get("yt_desc", ""), "thumb_ms": item.get("thumb_ms", 1500),
                                 "before": before, "after": sst, "queue": False}
            break
        else:
            nxt.pop(slot["name"], None)
    if not only:
        for k in list(nxt):
            if k not in live:
                nxt.pop(k)
    for slot, _ in plan:
        if slot["name"] in nxt:
            nxt[slot["name"]]["time"] = slot["time"]
    NEXT.write_text(json.dumps(nxt, ensure_ascii=False, indent=1), encoding="utf-8")


def use_preview(slot_name, stream, sst, wd):
    """The prepared reel for this slot if it is still the right one (same stream state). Updates sst."""
    if not NEXT.is_file():
        return None
    p = json.loads(NEXT.read_text(encoding="utf-8")).get(slot_name)
    if not p or p.get("queue") or p.get("stream") != stream or p.get("before") != key(sst):
        return None
    try:
        mp4 = download(p["full"], wd / "video.mp4")
    except Exception as e:  # noqa: BLE001
        print("preview not usable, rendering:", e)
        return None
    sst.clear()
    sst.update(p["after"])
    return {"mp4": mp4, "thumb_ms": p.get("thumb_ms", 1500), "caption": p["caption"], "yt_title": p.get("yt_title", ""),
            "yt_desc": p.get("yt_desc", p["caption"]), "label": p["label"]}
