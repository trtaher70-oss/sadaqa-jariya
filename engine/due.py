"""Quick check for the workflow (standard library + node only): is any slot due now? prints due=yes|no"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import calendar_hijri as H  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TZ = dt.timezone(dt.timedelta(hours=3))


def slots_for(day):
    sched = json.loads((ROOT / "data" / "schedule.json").read_text(encoding="utf-8"))["slots"]
    occ_from = json.loads((ROOT / "data" / "occasions.json").read_text(encoding="utf-8")).get("from", "")
    out = [s for s in sched if not s.get("from") or day.isoformat() >= s["from"]]
    if day.isoformat() >= occ_from:
        out += [dict(e, stream=None) for e in H.day_plan(day)["extra"]]
    return out


if __name__ == "__main__":
    now = dt.datetime.now(TZ)
    st = json.loads((ROOT / "state" / "state.json").read_text(encoding="utf-8")) if (ROOT / "state" / "state.json").is_file() else {"slots": {}}
    due = [s for s in slots_for(now.date()) if (now.hour, now.minute) >= tuple(map(int, s["time"].split(":")))
           and st["slots"].get(s["name"]) != now.date().isoformat()]
    print("due=" + ("yes" if due or os.environ.get("FORCE") or os.environ.get("PREV") == "true" else "no"))
