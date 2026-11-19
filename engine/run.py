"""Hourly entry point (GitHub Actions). Publishes every slot whose time has come today (Turkey/Mecca time)
and that is not done yet — so a delayed or missed run is simply caught up by the next one.

  python engine/run.py            normal run (at most one slot per run)
  python engine/run.py --dry      build + render only, no publishing, state not saved
  python engine/run.py --slot X   force one slot now (testing)
"""
import copy
import datetime as dt
import json
import shutil
import sys
import traceback
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import build  # noqa: E402
import publish  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state" / "state.json"
SCHED = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))
TZ = dt.timezone(dt.timedelta(hours=3))  # Turkey = Mecca time


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {"streams": {}, "slots": {}, "log": []}


def save_state(st):
    st["log"] = st["log"][-400:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def build_podcast(sst, wd):
    """Next approved podcast clip (prepared and reviewed by a person). None when the queue is empty."""
    q = json.loads((ROOT / "data" / "podcast_queue.json").read_text(encoding="utf-8"))
    done = set(sst.setdefault("done", []))
    it = next((x for x in q if x.get("approved") and x["id"] not in done), None)
    if not it:
        return None
    wd.mkdir(parents=True, exist_ok=True)
    out = {}
    for plat in ("ig", "yt"):
        url = it.get(f"{plat}_asset")
        if url:
            f = wd / f"{plat}.mp4"
            with requests.get(url, stream=True, timeout=900) as r:
                r.raise_for_status()
                with open(f, "wb") as o:
                    for ch in r.iter_content(1 << 16):
                        o.write(ch)
            out[plat] = f
    sst["done"].append(it["id"])
    return {"mp4": out.get("ig"), "mp4_yt": out.get("yt") or out.get("ig"), "thumb_ms": it.get("thumb_ms", 1500),
            "caption": it["caption"], "yt_title": it["yt_title"], "yt_desc": it["yt_desc"], "tags": it.get("tags", []),
            "label": f"podcast {it['id']}"}


def due_slots(st, now):
    today = now.date().isoformat()
    out = []
    for s in SCHED["slots"]:
        if s.get("from") and today < s["from"]:
            continue
        hh, mm = map(int, s["time"].split(":"))
        if (now.hour, now.minute) >= (hh, mm) and st["slots"].get(s["name"]) != today:
            out.append(s)
    return out


def do_slot(st, slot, dry=False):
    now = dt.datetime.now(TZ)
    wd = ROOT / "work" / slot["name"]
    shutil.rmtree(wd, ignore_errors=True)
    streams = copy.deepcopy(st["streams"])
    item, used = None, None
    for stream in [slot["stream"]] + slot.get("fallback", []):
        sst = streams.setdefault(stream, {})
        item = build_podcast(sst, wd) if stream == "podcast" else build.BUILDERS[stream](sst, wd)
        if item:
            used = stream
            break
    if not item:
        raise RuntimeError(f"slot {slot['name']}: nothing to publish")
    print(f"[{slot['name']}] built {item['label']}", flush=True)
    if dry:
        print(item["caption"][:600])
        return
    results = {}
    for plat in slot["platforms"]:
        if not publish.enabled(plat):
            continue
        try:
            if plat == "instagram":
                results[plat] = publish.instagram(item["mp4"], item["caption"], item.get("thumb_ms", 1500))
            elif plat == "youtube":
                results[plat] = publish.youtube(item.get("mp4_yt") or item["mp4"], item["yt_title"], item["yt_desc"], item.get("tags"))
        except Exception as e:  # noqa: BLE001  — keep the other platform; never re-post the same slot
            results[plat] = {"error": str(e)[:500]}
    ok = any("id" in r for r in results.values())
    if ok:  # content pointer advances only when something was really published
        st["streams"] = streams
    st["slots"][slot["name"]] = now.date().isoformat()
    st["log"].append({"t": now.isoformat(timespec="minutes"), "slot": slot["name"], "stream": used, "item": item["label"],
                      "results": results})
    print(json.dumps(results, ensure_ascii=False), flush=True)
    if not ok:
        raise RuntimeError(f"slot {slot['name']}: publishing failed {results}")


def main():
    dry = "--dry" in sys.argv
    st = load_state()
    if "--slot" in sys.argv:
        name = sys.argv[sys.argv.index("--slot") + 1]
        slots = [s for s in SCHED["slots"] if s["name"] == name]
    else:
        slots = due_slots(st, dt.datetime.now(TZ))[:1]
    if not slots:
        print("nothing due")
        return
    try:
        do_slot(st, slots[0], dry=dry)
    except Exception:
        traceback.print_exc()
        if not dry:  # after 3 failed attempts in one day, give the slot up until tomorrow (no endless retries)
            key = f"{slots[0]['name']}:{dt.datetime.now(TZ).date().isoformat()}"
            fails = st.setdefault("fails", {})
            fails[key] = fails.get(key, 0) + 1
            if fails[key] >= 3:
                st["slots"][slots[0]["name"]] = dt.datetime.now(TZ).date().isoformat()
            st["fails"] = {k: v for k, v in fails.items() if k.split(":")[1] >= (dt.datetime.now(TZ).date() - dt.timedelta(days=7)).isoformat()}
            save_state(st)
        sys.exit(1)
    if not dry:
        save_state(st)


if __name__ == "__main__":
    main()
