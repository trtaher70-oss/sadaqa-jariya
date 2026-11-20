"""Refresh the public account numbers for the dashboard (followers, posts, latest reels + likes/comments).
Standard library only, so it runs on every check without installing anything. Prints changed=yes|no.
Writes state/stats.json only when a number or the list of reels changed (thumbnail URLs alone don't count)."""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "state" / "stats.json"
TZ = dt.timezone(dt.timedelta(hours=3))


def fingerprint(d):
    return json.dumps([d.get("followers"), d.get("posts"),
                       [(m.get("url"), m.get("likes"), m.get("comments")) for m in d.get("recent", [])]])


def main():
    uid, tok = os.environ.get("IG_USER_ID"), os.environ.get("IG_TOKEN")
    if not uid or not tok:
        print("changed=no")
        return
    fields = ("username,followers_count,media_count,media.limit(12){caption,media_product_type,timestamp,permalink,"
              "thumbnail_url,media_url,like_count,comments_count}")
    url = f"https://graph.facebook.com/v23.0/{uid}?" + urllib.parse.urlencode({"fields": fields, "access_token": tok})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — numbers are optional, never fail the run
        print("changed=no")
        print("stats error:", str(e)[:200], file=__import__("sys").stderr)
        return
    media = [{"t": m.get("timestamp"), "url": m.get("permalink"), "thumb": m.get("thumbnail_url") or m.get("media_url"),
              "cap": (m.get("caption") or "").splitlines()[0][:120] if m.get("caption") else "",
              "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0), "type": m.get("media_product_type")}
             for m in d.get("media", {}).get("data", [])]
    new = {"updated": dt.datetime.now(TZ).isoformat(timespec="minutes"), "username": d.get("username"),
           "followers": d.get("followers_count"), "posts": d.get("media_count"), "recent": media}
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    if fingerprint(old) == fingerprint(new):
        print("changed=no")
        return
    OUT.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    print("changed=yes")


if __name__ == "__main__":
    main()
