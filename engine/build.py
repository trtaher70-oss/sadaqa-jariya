"""Build one reel (no GPU): pick the content, cut the recitation, time the words, render with Remotion.

Streams
  curated — hand-written duas / reminders (data/curated.json). Endless: every cycle re-uses the list with the
            next reciter, so the same dua comes back months later in a different voice.
  khatma  — the whole Quran in order, one passage per reel (15–60 s, cut at ruku / waqf boundaries),
            reciters rotate reel by reel; when the Quran ends, the next khatma starts. Endless.
Caption of a khatma reel = the passage + التفسير الميسر (King Fahd Complex) — no AI-written religious text.
"""
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORK = ROOT / "work"
VIDEO = ROOT / "video"
Q = json.loads((DATA / "quran_words.json").read_text(encoding="utf-8"))
TAFSIR = json.loads((DATA / "tafsir_muyassar.json").read_text(encoding="utf-8"))
REC = json.loads((DATA / "reciters.json").read_text(encoding="utf-8"))
SURAS = json.loads((DATA / "suras.json").read_text(encoding="utf-8"))  # 114 Arabic names
AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
WAQF = "ۖۗۘۙۚۛۜ"
BASMALA = ["بِسْمِ", "ٱللَّهِ", "ٱلرَّحْمَـٰنِ", "ٱلرَّحِيمِ"]
FPS, LEAD, GAP, TAIL, OUTRO = 30, 0.6, 0.3, 0.6, 2.6
MAX_LETTERS = 80
MIN_COV = 0.6
NAYAT = {}
for _k in Q:
    _s, _n = map(int, _k.split(":"))
    NAYAT[_s] = max(NAYAT.get(_s, 0), _n)
H = {"User-Agent": "Mozilla/5.0"}


# ------------------------------------------------------------------ helpers
def ar(n):
    return str(n).translate(AR)


def letters(t):
    return sum(1 for c in t if not unicodedata.category(c).startswith("M") and c not in WAQF and c not in "  ")


def size_for(n):
    return 110 if n < 35 else 98 if n < 60 else 88 if n < 85 else 78 if n < 110 else 70


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def align(rk, su):
    f = DATA / "align" / rk / f"{su:03d}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def usable(rk, su, ayat):
    """Reciter rk has good timings for all these ayat of surah su."""
    if su not in REC[rk]["surahs"]:
        return False
    a = align(rk, su)
    return bool(a) and all(str(n) in a["ayat"] and a["ayat"][str(n)]["cov"] >= MIN_COV for n in ayat)


def ayah_dur(a, n):
    w = a["ayat"][str(n)]["w"]
    return w[-1][1] - w[0][0]


def surah_mp3(rk, su):
    f = WORK / "audio" / rk / f"{su:03d}.mp3"
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        url = align(rk, su)["url"]
        for k in range(4):
            try:
                with requests.get(url, headers=H, stream=True, timeout=900) as r:
                    r.raise_for_status()
                    with open(f.with_suffix(".part"), "wb") as o:
                        for ch in r.iter_content(1 << 16):
                            o.write(ch)
                f.with_suffix(".part").rename(f)
                break
            except Exception as e:  # noqa: BLE001
                print("download retry", e, flush=True)
        else:
            raise RuntimeError(f"cannot download {url}")
    return f


def pages_for(timed):
    """Group (word, s, e) into pages, cutting after waqf marks (<= MAX_LETTERS per page)."""
    phrases, cur = [], []
    for w in timed:
        cur.append(w)
        if any(m in w[0] for m in WAQF):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    pages, cur = [], []
    for ph in phrases:
        if cur and letters(" ".join(w[0] for w in cur + ph)) > MAX_LETTERS:
            pages.append(cur)
            cur = list(ph)
        else:
            cur += ph
    pages.append(cur)
    out = []
    for pg in pages:
        n = -(-letters(" ".join(w[0] for w in pg)) // MAX_LETTERS)
        if n == 1:
            out.append(pg)
            continue
        target, part = letters(" ".join(w[0] for w in pg)) / n, []
        for w in pg:
            part.append(w)
            if letters(" ".join(x[0] for x in part)) >= target:
                out.append(part)
                part = []
        if part:
            out.append(part)
    return out


# ------------------------------------------------------------------ props (video description)
def props_for(rk, su, ayat, hook, kind, wd):
    """Describe the reel for Remotion. The recitation of the consecutive `ayat` is cut as ONE continuous piece,
    from where the voice really starts to where it really stops (audio energy, see edges.py) — never in between
    ayat, so nothing of the reciter's madd or pauses is lost."""
    from edges import voice_end, voice_start
    a = align(rk, su)
    src = surah_mp3(rk, su)
    pub = VIDEO / "public" / "clip"
    pub.mkdir(parents=True, exist_ok=True)
    for old in pub.glob("*.mp3"):
        old.unlink()
    units = []
    if ayat[0] == 1 and su not in (1, 9) and a.get("basmala"):
        units.append((BASMALA, a["basmala"], "", None))
    for n in ayat:
        units.append((Q[f"{su}:{n}"]["w"], a["ayat"][str(n)]["w"], f"سورة {SURAS[su - 1]} — الآية {ar(n)}", n))
    first_t, last_t = units[0][1][0][0], units[-1][1][-1][1]
    prev = a["ayat"].get(str(ayat[0] - 1)) if units[0][3] else None
    nxt = a["ayat"].get(str(ayat[-1] + 1))
    cut0 = voice_start(src, first_t, limit=prev["w"][-1][1] if prev else None)
    cut1 = voice_end(src, last_t, limit=nxt["w"][0][1] if nxt else None)
    mp3 = pub / "recitation.mp3"
    dur = cut1 - cut0
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{cut0:.3f}", "-to", f"{cut1 + 0.25:.3f}", "-i", str(src),
         "-af", f"afade=t=in:d=0.05,afade=t=out:st={max(0.0, dur):.3f}:d=0.25", "-ar", "44100", "-b:a", "192k", str(mp3)])
    audio = [{"src": f"clip/{mp3.name}", "at": LEAD}]
    pages = []
    for ui, (words, spans, ref, no) in enumerate(units):
        timed = [(w, LEAD + s - cut0, LEAD + e - cut0) for w, (s, e) in zip(words, spans)]
        if ui == len(units) - 1:  # the last word lasts until the voice stops
            w, s, e = timed[-1]
            timed[-1] = (w, s, max(e, LEAD + dur))
        groups = pages_for(timed)
        for gi, g in enumerate(groups):
            ws = [{"t": w, "s": round(s, 3), "e": round(e, 3)} for w, s, e in g]
            if no and gi == len(groups) - 1:
                ws[-1]["t"] += " " + f"﴿{ar(no)}﴾"
            text = " ".join(w["t"] for w in ws)
            pages.append({"s": round(max(0.05, ws[0]["s"] - 0.3), 3), "e": 0, "text": text, "words": ws, "ref": ref,
                          "size": size_for(letters(text))})
    end = LEAD + dur + TAIL
    for i in range(len(pages) - 1):
        pages[i]["e"] = pages[i + 1]["s"]
    pages[-1]["e"] = round(end, 3)
    return {"hook": hook, "kind": kind, "audio": audio, "pages": pages, "total": round(end + OUTRO, 3),
            "outroDur": OUTRO, "reciter": REC[rk]["name"]}


def render(props, wd):
    wd.mkdir(parents=True, exist_ok=True)
    pf = wd / "props.json"
    pf.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    p0 = props["pages"][0]
    cover_t = min(p0["e"] - 0.2, p0["words"][-1]["e"] + 0.2)
    run(["node", "render_one.mjs", str(pf), str(wd / "video.mp4"), str(wd / "cover.jpg"), str(round(cover_t * FPS))], cwd=VIDEO)
    return wd / "video.mp4", round(cover_t * 1000)


# ------------------------------------------------------------------ streams
def tafsir_for(su, ayat):
    seen, parts = set(), []
    for n in ayat:
        k = n
        while k > 0 and f"{su}:{k}" not in TAFSIR:  # grouped verses: the explanation sits on the first verse
            k -= 1
        t = re.sub(r"<[^>]+>", "", TAFSIR.get(f"{su}:{k}", "")).strip()
        if t and t not in seen:
            seen.add(t)
            parts.append(t)
    return "\n".join(parts)


def next_khatma(st):
    """Next passage of the running khatma + a reciter that has it. Advances st (khatma pointer, rotation)."""
    su, n = st.get("su", 1), st.get("n", 1)
    order = list(REC)
    if not any(align(rk, su) for rk in order):  # timings for this surah not uploaded yet: wait, never skip
        raise RuntimeError(f"khatma: no timings yet for surah {su}")
    for _ in range(len(order)):
        rk = order[st.get("rot", 0) % len(order)]
        st["rot"] = st.get("rot", 0) + 1
        if not usable(rk, su, [n]):
            continue
        a = align(rk, su)
        ayat, total = [n], ayah_dur(a, n)
        ruku = Q[f"{su}:{n}"]["ruku"]
        while ayat[-1] < NAYAT[su] and total < 15:  # at least ~15 s
            m = ayat[-1] + 1
            if not usable(rk, su, [m]):
                break
            ayat.append(m)
            total += ayah_dur(a, m)
        while ayat[-1] < NAYAT[su]:  # then grow up to ~50 s inside the same ruku
            m = ayat[-1] + 1
            if Q[f"{su}:{m}"]["ruku"] != ruku or total + ayah_dur(a, m) > 50 or not usable(rk, su, [m]):
                break
            ayat.append(m)
            total += ayah_dur(a, m)
        last = ayat[-1]
        if last < NAYAT[su]:
            st["su"], st["n"] = su, last + 1
        elif su < 114:
            st["su"], st["n"] = su + 1, 1
        else:  # khatma complete — start the next one
            st["su"], st["n"], st["khatma"] = 1, 1, st.get("khatma", 1) + 1
        return rk, su, ayat
    # nobody has this ayah with good timings: skip it
    if n < NAYAT[su]:
        st["n"] = n + 1
    else:
        st["su"], st["n"] = (su % 114) + 1, 1
    return next_khatma(st)


def build_khatma(st, wd):
    rk, su, ayat = next_khatma(st)
    rng = f"{ar(ayat[0])}" + (f"–{ar(ayat[-1])}" if len(ayat) > 1 else "")
    juz = Q[f"{su}:{ayat[0]}"]["juz"]
    hook = f"سورة {SURAS[su - 1]}"
    kind = f"ختمة — الجزء {ar(juz)}"
    props = props_for(rk, su, ayat, hook, kind, wd)
    mp4, thumb = render(props, wd)
    taf = tafsir_for(su, ayat)
    if len(taf) > 1500:
        taf = taf[:1500].rsplit(" ", 1)[0] + "…"
    cap = (f"﴿ سورة {SURAS[su - 1]} — الآيات {rng} ﴾ · الجزء {ar(juz)}\n"
           f"ختمة صدقة جارية رقم {ar(st.get('khatma', 1))} — آيات كل يوم حتى نختم القرآن معاً\n\n"
           f"التفسير الميسر:\n{taf}\n\n"
           f"شاركها… لعلها تكون صدقة جارية لك 🤍\n"
           f"التلاوة: {REC[rk]['name']}\n\n"
           f"#قرآن #تلاوة #{REC[rk]['tag']} #صدقة_جارية #تذكير")
    yt_title = f"سورة {SURAS[su - 1]} {rng} | {REC[rk]['name'].replace('القارئ ', '').replace('الشيخ ', '')} | تلاوة خاشعة"
    return {"mp4": mp4, "thumb_ms": thumb, "caption": cap, "yt_title": yt_title[:100], "yt_desc": cap,
            "label": f"khatma {su}:{ayat[0]}-{ayat[-1]} {rk}"}


def build_item(it, cyc, wd, start=0):
    """Render one verse-based reel (curated dua / occasion): cycle `cyc` uses the cyc-th next reciter."""
    su, rng = it["aya"].split(":")
    lo, hi = (rng.split("-") + [rng])[:2]
    ayat = list(range(int(lo), int(hi) + 1))
    su = int(su)
    order = list(REC)
    for k in range(len(order)):
        rk = order[(start + cyc + k) % len(order)]
        if usable(rk, su, ayat):
            break
    else:
        raise RuntimeError(f"no reciter with timings for {it['aya']} yet")
    props = props_for(rk, su, ayat, it["hook"], it["kind"], wd)
    mp4, thumb = render(props, wd)
    ref = f"سورة {SURAS[su - 1]} — الآية {ar(rng.replace('-', '–'))}"
    tags = [t for t in it["tags"] if t != "قرآن"][:2] + [REC[rk]["tag"], "صدقة_جارية", "تذكير"]
    cap = (f"{it['hook']}\n\n{it['caption']}\n\nشاركها… لعلها تكون صدقة جارية لك 🤍\n\n"
           f"التلاوة: {REC[rk]['name']} · {ref}\n\n" + " ".join("#" + t for t in tags))
    return {"mp4": mp4, "thumb_ms": thumb, "caption": cap, "yt_title": f"{it['hook']} | {REC[rk]['name']}"[:100],
            "yt_desc": cap, "label": f"{it.get('_label', 'curated')} {it['id']} {rk}"}


def build_curated(st, wd):
    items = json.loads((DATA / "curated.json").read_text(encoding="utf-8"))
    i = st.get("i", 0)
    it = items[i % len(items)]
    order = list(REC)
    start = order.index(it["reciter"]) if it.get("reciter") in order else 0
    out = build_item(it, i // len(items), wd, start)
    st["i"] = i + 1
    return out


POOLS = json.loads((DATA / "pools.json").read_text(encoding="utf-8"))


def build_pool(pool, st, wd):
    """Next reel of an occasion pool (Friday, Ramadan, Eid …). Each new cycle uses another reciter."""
    items = POOLS[pool]
    i = st.get("i", 0)
    it = dict(items[i % len(items)], _label=f"occasion:{pool}")
    out = build_item(it, i // len(items), wd, start=(sum(map(ord, it["id"])) % len(REC)))
    st["i"] = i + 1
    return out


BUILDERS = {"khatma": build_khatma, "curated": build_curated}
