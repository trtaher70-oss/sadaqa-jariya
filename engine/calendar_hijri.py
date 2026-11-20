"""Hijri calendar (Umm al-Qura, via Node's built-in ICU — no website needed) + Islamic occasions.
Standard library only (also used by the workflow's quick "is anything due?" check)."""
import datetime as dt
import json
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = json.loads((ROOT / "data" / "occasions.json").read_text(encoding="utf-8"))["rules"]
ADJ = json.loads((ROOT / "data" / "hijri_adjust.json").read_text(encoding="utf-8"))
MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال",
          "ذو القعدة", "ذو الحجة"]


@lru_cache(maxsize=8)
def _table(start_iso, days):
    out = subprocess.run(["node", str(ROOT / "engine" / "hijri.mjs"), start_iso, str(days)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def hijri(d: dt.date):
    """(year, month, day) for a Gregorian date, with the ministry adjustments applied."""
    off = int(ADJ.get("offset_days", 0))
    base = d - dt.timedelta(days=off)
    start = base - dt.timedelta(days=base.toordinal() % 200)  # cache blocks of 260 days
    y, m, day = _table(start.isoformat(), 260)[base.isoformat()]
    # explicit month start announced by the ministry: count days from it
    for key, iso in ADJ.get("month_starts", {}).items():
        ky, km = map(int, key.split("-"))
        s = dt.date.fromisoformat(iso)
        if 0 <= (d - s).days < 30:
            nxt_key = f"{ky + (km == 12)}-{km % 12 + 1:02d}"
            nxt = ADJ["month_starts"].get(nxt_key)
            if not nxt or d < dt.date.fromisoformat(nxt):
                if (d - s).days < 29 or (y, m) == (ky, km):
                    return ky, km, (d - s).days + 1
    return y, m, day


def matches(rule, d, h):
    if "weekday" in rule and d.weekday() != rule["weekday"]:
        return False
    if "hijri" in rule:
        hm = rule["hijri"]
        if "m" in hm and h[1] not in hm["m"]:
            return False
        if "d" in hm and not (hm["d"][0] <= h[2] <= hm["d"][1]):
            return False
    return True


def day_plan(d: dt.date):
    """{'slots': {slot: (pool, occasion name)}, 'extra': [slot dicts], 'names': [...], 'hijri': (y, m, d)}"""
    h = hijri(d)
    slots, extra, names = {}, [], []
    for r in RULES:
        if not matches(r, d, h):
            continue
        names.append(r["name"])
        for s, pool in r.get("slots", {}).items():
            slots.setdefault(s, (pool, r["name"]))
        for e in r.get("extra", []):
            if all(x["name"] != e["name"] for x in extra):
                extra.append({**e, "occasion": r["name"], "platforms": ["instagram"]})
    return {"slots": slots, "extra": extra, "names": names, "hijri": h}


def hijri_text(h):
    return f"{h[2]} {MONTHS[h[1] - 1]} {h[0]}هـ"


def upcoming(start: dt.date, days=60):
    out = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        p = day_plan(d)
        if p["names"]:
            out.append({"date": d.isoformat(), "hijri": hijri_text(p["hijri"]), "names": p["names"],
                        "pools": sorted({v[0] for v in p["slots"].values()} | {e["pool"] for e in p["extra"]})})
    return out
