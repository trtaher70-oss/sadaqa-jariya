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
import queues as Q  # noqa: E402
import calendar_hijri as H  # noqa: E402
from due import slots_for  # noqa: E402

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


def write_stats():
    """Public numbers for the dashboard (followers, posts, latest reels). Never writes any secret."""
    import os
    uid, tok = os.environ.get("IG_USER_ID"), os.environ.get("IG_TOKEN")
    if not uid or not tok:
        return
    try:
        g = "https://graph.facebook.com/" + os.environ.get("GRAPH_VERSION", "v23.0")
        f = ("username,followers_count,media_count,media.limit(12){caption,media_product_type,timestamp,permalink,"
             "thumbnail_url,media_url,like_count,comments_count}")
        d = requests.get(f"{g}/{uid}", params={"fields": f, "access_token": tok}, timeout=60).json()
        if "error" in d:
            return
        media = [{"t": m.get("timestamp"), "url": m.get("permalink"), "thumb": m.get("thumbnail_url") or m.get("media_url"),
                  "cap": (m.get("caption") or "").splitlines()[0][:120] if m.get("caption") else "", "likes": m.get("like_count", 0),
                  "comments": m.get("comments_count", 0), "type": m.get("media_product_type")} for m in d.get("media", {}).get("data", [])]
        out = {"updated": dt.datetime.now(TZ).isoformat(timespec="minutes"), "username": d.get("username"),
               "followers": d.get("followers_count"), "posts": d.get("media_count"), "recent": media}
        (ROOT / "state" / "stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print("stats skipped:", e)


def due_slots(st, now):
    today = now.date().isoformat()
    return [s for s in slots_for(now.date()) if (now.hour, now.minute) >= tuple(map(int, s["time"].split(":")))
            and st["slots"].get(s["name"]) != today]


def occasion_pool(slot, day):
    """Pool that replaces this slot's content on `day` (Friday, Ramadan, Eid …), or None."""
    occ_from = json.loads((ROOT / "data" / "occasions.json").read_text(encoding="utf-8")).get("from", "")
    if day.isoformat() < occ_from:
        return None, None
    if slot.get("pool"):
        return slot["pool"], slot.get("occasion")
    hit = H.day_plan(day)["slots"].get(slot["name"])
    return hit if hit else (None, None)


def do_slot(st, slot, dry=False):
    now = dt.datetime.now(TZ)
    wd = ROOT / "work" / slot["name"]
    shutil.rmtree(wd, ignore_errors=True)
    streams = copy.deepcopy(st["streams"])
    item, used = None, None
    pool, occ = occasion_pool(slot, now.date())
    if pool:  # an occasion day: its own reel; if it cannot be made yet, the slot's normal content
        psst = streams.setdefault(f"pool:{pool}", {})
        try:
            item = Q.use_preview(slot["name"], f"pool:{pool}", psst, wd) or build.build_pool(pool, psst, wd)
            used = f"pool:{pool}"
        except Exception as e:  # noqa: BLE001
            print(f"[{slot['name']}] occasion {pool} not ready: {e}", flush=True)
            item = None
    if not item and not slot.get("stream"):  # extra occasion slot with nothing to post: skip quietly
        st["slots"][slot["name"]] = now.date().isoformat()
        print(f"[{slot['name']}] skipped (occasion reel not ready)", flush=True)
        return
    for stream in ([] if item else [slot["stream"]] + slot.get("fallback", [])):
        sst = streams.setdefault(stream, {})
        if stream in Q.QUEUES:
            item = Q.build_queue(stream, sst, wd)
        else:  # the reel prepared in advance (shown on the dashboard) if still valid, else render now
            item = Q.use_preview(slot["name"], stream, sst, wd) or build.BUILDERS[stream](sst, wd)
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
    st["log"].append({"t": now.isoformat(timespec="minutes"), "slot": slot["name"], "stream": used, "item": item["label"], "occasion": occ,
                      "results": results})
    print(json.dumps(results, ensure_ascii=False), flush=True)
    if not ok:
        raise RuntimeError(f"slot {slot['name']}: publishing failed {results}")


def previews(st, only=None):
    try:
        Q.make_previews(st, SCHED, build.BUILDERS, TZ, only, occasion=occasion_pool, extras=slots_for, pool_builder=build.build_pool)
    except Exception:  # a failed preview never blocks publishing
        traceback.print_exc()
    try:  # upcoming occasions for the dashboard
        today = dt.datetime.now(TZ).date()
        (ROOT / "state" / "calendar.json").write_text(json.dumps({"today_hijri": H.hijri_text(H.hijri(today)),
            "upcoming": H.upcoming(today, 75)}, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        traceback.print_exc()


def main():
    dry = "--dry" in sys.argv
    st = load_state()
    if "--preview" in sys.argv:
        previews(st, sys.argv[sys.argv.index("--preview") + 1] if len(sys.argv) > sys.argv.index("--preview") + 1 else None)
        return
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
            write_stats()
        sys.exit(1)
    if not dry:
        save_state(st)
        write_stats()
        previews(st)


if __name__ == "__main__":
    main()
