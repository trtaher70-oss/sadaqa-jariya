"""Per-word timings for any reciter: find the ayah inside the reciter's recording with faster-whisper,
then map whisper's word times onto the exact Uthmani words (character-level alignment).

Sources: mp3quran.net (whole-surah files; ayah timing used as a search window when available) or
EveryAyah (one file per ayah). Results are cached in work/downloads/ayat/aligned/<reciter>/.

verse_aligned(key, rkey, rconf, qwords, after=None) -> (mp3 path of the cut ayah, [(word, s, e)], coverage)
"""
import json
import os
import re
import site
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

import requests

for sp in site.getsitepackages():  # pip-installed CUDA libs for ctranslate2 on Windows
    for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
        q = Path(sp) / sub
        if q.is_dir():
            os.add_dll_directory(str(q))
            os.environ["PATH"] = str(q) + os.pathsep + os.environ["PATH"]

WORK = Path(__file__).resolve().parents[1]
BASE = WORK / "downloads" / "ayat"
MODEL_DIR = Path(r"C:\Users\t8646\prv60_clipper\models\faster-whisper-large-v3")
H = {"User-Agent": "Mozilla/5.0"}
_model = None
_mp3q = None


def norm(t):
    t = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]", "", t)
    t = re.sub("[ٱأإآ]", "ا", t).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")
    return re.sub(r"[^\u0621-\u064A]", "", t)


def letters(t):
    return len(norm(t))


def dur(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout)


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(str(MODEL_DIR), device="cuda", compute_type="float16")
    return _model


def whisper_words(src, t0, t1, prompt, vad=False):
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t0:.2f}", "-to", f"{t1:.2f}", "-i", str(src),
                          "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    segs, _ = model().transcribe(audio, language="ar", word_timestamps=True, beam_size=5, vad_filter=vad,
                                 condition_on_previous_text=False, initial_prompt=prompt or None,
                                 hallucination_silence_threshold=1.0)
    return [(w.word.strip(), t0 + w.start, t0 + w.end) for s in segs for w in s.words]


def mp3q(rid):
    global _mp3q
    if _mp3q is None:
        f = BASE / "mp3quran_reciters.json"
        if not f.is_file():
            f.write_text(requests.get("https://www.mp3quran.net/api/v3/reciters?language=ar", headers=H, timeout=60).text, encoding="utf-8")
        _mp3q = {r["id"]: r for r in json.loads(f.read_text(encoding="utf-8"))["reciters"]}
    return _mp3q[rid]["moshaf"][0]


def surah_file(rid, su):
    d = BASE / "mp3quran" / str(rid)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{su:03d}.mp3"
    if not f.is_file():
        tmp = f.with_suffix(".part")
        with requests.get(mp3q(rid)["server"] + f"{su:03d}.mp3", headers=H, stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(tmp, "wb") as o:
                for ch in r.iter_content(1 << 16):
                    o.write(ch)
        tmp.rename(f)
    return f


def ayah_timing(rid, su):
    f = BASE / "mp3quran" / str(rid) / f"timing_{su:03d}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.is_file():
        try:
            r = requests.get(f"https://www.mp3quran.net/api/v3/ayat_timing?surah={su}&read={rid}", headers=H, timeout=60)
            data = r.json() if r.ok and r.text.strip().startswith("[") else []
        except Exception:
            data = []
        f.write_text(json.dumps(data), encoding="utf-8")
    return {x["ayah"]: (x["start_time"] / 1000, x["end_time"] / 1000) for x in json.loads(f.read_text(encoding="utf-8"))}


def ref_ratio(su, n):
    """Where ayah n sits inside the surah (fraction), from Alafasy's chapter timings."""
    f = BASE / "qdc" / f"chapter_{su:03d}_7.json"
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(requests.get(f"https://api.qurancdn.com/api/qdc/audio/reciters/7/audio_files?chapter={su}&segments=true",
                                  timeout=60).text, encoding="utf-8")
    a = json.loads(f.read_text(encoding="utf-8"))["audio_files"][0]
    v = next(x for x in a["verse_timings"] if x["verse_key"] == f"{su}:{n}")
    return v["timestamp_from"] / a["duration"], v["timestamp_to"] / a["duration"]


NAMES = {"ا": "الف", "ل": "لام", "م": "ميم", "ص": "صاد", "ر": "را", "ك": "كاف", "ه": "ها", "ي": "يا", "ع": "عين",
         "ط": "طا", "س": "سين", "ح": "حا", "ق": "قاف", "ن": "نون"}
# the disconnected letters (الٓمٓ، حمٓ، يسٓ …) are recited by their names: «ألف لام ميم»
MUQATTAAT = {"الم", "المص", "الر", "المر", "كهيعص", "طه", "طسم", "طس", "يس", "ص", "حم", "عسق", "ق", "ن"}


def qnorm(w):
    n = norm(w)
    if n in MUQATTAAT and ("ٓ" in w or n in ("طه", "يس", "حم", "طس", "طسم")):
        return "".join(NAMES.get(c, c) for c in n)
    return n


def match(qwords, ww):
    """Word-level semi-global alignment of the Quran words onto whisper's words (in order).
    Allows 1 whisper word = 2 Quran words (e.g. «وذنون» = «وذا النون») and 2 whisper words = 1 Quran word.
    Returns ([(s, e)] per Quran word, mean similarity 0..1)."""
    Q = [norm(w) for w in qwords]
    ALT = {k: qnorm(w) for k, w in enumerate(qwords) if qnorm(w) != Q[k]}  # «الم» may be heard as «ألف لام ميم»
    Wn = [norm(w[0]) for w in ww]
    n, m = len(Wn), len(Q)
    if not n or not m:
        return None, 0
    _sm = lambda a, b: SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0

    def sim(a, b):
        r = _sm(a, b)
        for k, alt in ALT.items():
            if b == Q[k]:
                r = max(r, _sm(a, alt))
        return r
    INF = 1e9
    SKIP_W, SKIP_Q = 0.3, 0.9  # extra heard words inside an ayah are cheap (reciters repeat phrases)
    # D[i][j]: best cost aligning Q[:j] ending at whisper index i (free start in W)
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    B = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c = D[i][j]
            if c >= INF:
                continue
            if i < n and j < m:  # 1:1
                v = c + 1 - sim(Wn[i], Q[j])
                if v < D[i + 1][j + 1]: D[i + 1][j + 1], B[i + 1][j + 1] = v, (i, j, "11")
            if i < n and j + 1 < m:  # 1 whisper : 2 quran
                v = c + 2 * (1 - sim(Wn[i], Q[j] + Q[j + 1]))
                if v < D[i + 1][j + 2]: D[i + 1][j + 2], B[i + 1][j + 2] = v, (i, j, "12")
            if i + 1 < n and j < m:  # 2 whisper : 1 quran
                v = c + 1 - sim(Wn[i] + Wn[i + 1], Q[j]) + 0.05
                if v < D[i + 2][j + 1]: D[i + 2][j + 1], B[i + 2][j + 1] = v, (i, j, "21")
            if j < m:  # quran word not heard
                v = c + SKIP_Q
                if v < D[i][j + 1]: D[i][j + 1], B[i][j + 1] = v, (i, j, "dq")
            if i < n and 0 < j < m:  # extra whisper word inside the ayah
                v = c + SKIP_W
                if v < D[i + 1][j]: D[i + 1][j], B[i + 1][j] = v, (i, j, "dw")
    end = min(range(n + 1), key=lambda i: D[i][m])
    spans, sims = [None] * m, []
    i, j = end, m
    while j > 0:
        pi, pj, op = B[i][j]
        if op == "11":
            spans[pj] = (ww[pi][1], ww[pi][2]); sims.append(sim(Wn[pi], Q[pj]))
        elif op == "12":
            s, e = ww[pi][1], ww[pi][2]
            r = len(Q[pj]) / max(1, len(Q[pj]) + len(Q[pj + 1]))
            spans[pj], spans[pj + 1] = (s, s + (e - s) * r), (s + (e - s) * r, e)
            sims += [sim(Wn[pi], Q[pj] + Q[pj + 1])] * 2
        elif op == "21":
            spans[pj] = (ww[pi][1], ww[pi + 1][2]); sims.append(sim(Wn[pi] + Wn[pi + 1], Q[pj]))
        elif op == "dq":
            sims.append(0.0)
        i, j = pi, pj
    known = [k for k in range(m) if spans[k]]
    if len(known) < max(1, m // 3):
        return None, sum(sims) / max(1, m)
    for k in range(m):  # unheard words: share the gap between their neighbours
        if spans[k] is None:
            a = max((x for x in known if x < k), default=None)
            b = min((x for x in known if x > k), default=None)
            if a is not None and b is not None:
                g0, g1 = spans[a][1], spans[b][0]
                frac0, frac1 = (k - a) / (b - a), (k - a + 1) / (b - a)
                spans[k] = (g0 + (g1 - g0) * frac0 - 0.0, g0 + (g1 - g0) * frac1)
            elif a is not None:
                spans[k] = (spans[a][1], spans[a][1] + 0.4)
            else:
                spans[k] = (max(0, spans[b][0] - 0.4), spans[b][0])
    out = []
    for k, (s, e) in enumerate(spans):  # continuous highlight: a word starts where the previous ended
        s = s - 0.12 if k == 0 else min(s, out[-1][1] + 0.02)
        out.append((s, max(e, s + 0.15)))
    return out, sum(sims) / max(1, m)


def verse_aligned(key, rkey, rc, qwords, after=None, basmala_for=None):
    """Cut ayah `key` from reciter `rkey` and time its words. `after` = (file, t) — search after this time
    in the same file (for consecutive ayat)."""
    su, n = map(int, key.split(":"))
    cache = BASE / "aligned_v2" / rkey
    cache.mkdir(parents=True, exist_ok=True)
    stem = f"basmala_{basmala_for:03d}" if basmala_for else f"{su:03d}{n:03d}"
    jf, mp3 = cache / f"{stem}.json", cache / f"{stem}.mp3"
    if jf.is_file() and mp3.is_file() and json.loads(jf.read_text(encoding="utf-8"))["coverage"] >= 0.6:
        d = json.loads(jf.read_text(encoding="utf-8"))
        return mp3, [tuple(x) for x in d["words"]], d["coverage"], (d["src"], d["src_end"])
    prompt = " ".join(norm(w) for w in qwords)
    if rc["src"] == "everyayah":
        src = cache / f"src_{su:03d}{n:03d}.mp3"
        if not src.is_file():
            src.write_bytes(requests.get(f"https://everyayah.com/data/{rc['dir']}/{su:03d}{n:03d}.mp3", timeout=120).content)
        t0, t1 = 0.0, dur(src)
    else:
        src = surah_file(rc["id"], basmala_for or su)
        D = dur(src)
        tm = ayah_timing(rc["id"], su) if not basmala_for else {}
        if basmala_for:  # basmala = start of that surah's own recording
            t0, t1 = 0.0, min(D, 45.0)
        elif n in tm:  # the site's ayah timing: search tightly around it (similar ayat nearby can't be picked)
            t0, t1 = max(0, tm[n][0] - 1.5), min(D, tm[n][1] + 1.5)
        else:
            ra, rb = ref_ratio(su, n)
            pad = max(75, 0.05 * D)
            t0, t1 = max(0, ra * D - pad), min(D, rb * D + pad)
        if after and after[0] == str(src):
            t0 = max(t0, after[1] - 1.0)
            t1 = max(t1, t0 + (8 if n in tm else 60))
    ww = whisper_words(src, t0, t1, prompt)
    if after and after[0] == str(src):
        ww = [w for w in ww if w[1] >= after[1] - 0.12]
    spans, cov = match(qwords, ww)
    if (not spans or cov < 0.6) and rc["src"] != "everyayah":  # whisper skipped/hallucinated: re-listen differently
        tries = [(t0, t1, True, prompt)]
        if not basmala_for and n in tm:
            tries.append((max(0, tm[n][0] - 15), min(D, tm[n][1] + 15), True, prompt))
        if not basmala_for:
            ra, rb = ref_ratio(su, n)
            pad = max(90, 0.06 * D)
            tries.append((max(0, ra * D - pad), min(D, rb * D + pad), True, ""))
        for a0, a1, vad, pr in tries:
            if after and after[0] == str(src):
                a0 = max(a0, after[1] - 1.0)
            w2 = whisper_words(src, a0, a1, pr, vad=vad)
            if after and after[0] == str(src):
                w2 = [w for w in w2 if w[1] >= after[1] - 0.12]
            s2, c2 = match(qwords, w2)
            if s2 and c2 > cov:
                spans, cov, ww = s2, c2, w2
            if cov >= 0.75:
                break
    if (not spans or cov < 0.5) and rc["src"] != "everyayah" and not basmala_for and n in tm:
        # last resort: the site's own ayah timing, words spread by their length
        s0, e0 = tm[n]
        if after and after[0] == str(src):
            s0 = max(s0, after[1] + 0.05)
        L = [max(1, len(norm(w))) for w in qwords]
        tot, acc, spans = sum(L), 0, []
        for l in L:
            spans.append((s0 + (e0 - s0) * acc / tot, s0 + (e0 - s0) * (acc + l) / tot))
            acc += l
        cov = 0.5
        print(f"   (timing fallback {rkey} {key})", flush=True)
    if not spans:
        raise RuntimeError(f"{rkey} {key}: ayah not found (coverage {cov:.2f})")
    if after and after[0] == str(src) and spans[-1][1] <= after[1] + 0.3:
        raise RuntimeError(f"{rkey} {key}: ayah placed before the previous one — check")
    true_end = spans[-1][1]
    a, b = spans[0][0] - 0.3, true_end + 0.35
    if after and after[0] == str(src):
        a = max(a, after[1] + 0.02)
    a = max(a, 0)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
                    "-af", "afade=t=in:d=0.08,areverse,afade=t=in:d=0.25,areverse", "-ar", "44100", "-b:a", "192k", str(mp3)], check=True)
    words = [(w, round(s - a, 3), round(e - a, 3)) for w, (s, e) in zip(qwords, spans)]
    jf.write_text(json.dumps({"words": words, "coverage": round(cov, 3), "src": str(src), "src_end": true_end,
                              "whisper": " ".join(w[0] for w in ww)}, ensure_ascii=False), encoding="utf-8")
    return mp3, words, cov, (str(src), true_end)
