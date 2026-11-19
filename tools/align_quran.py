"""One-time (local GPU) job: per-word timings of the whole Quran for every reciter in data/reciters.json.

For each surah: download the reciter's surah mp3 (mp3quran.net), transcribe it once with faster-whisper
(word timestamps), then place each ayah in order with the word-level aligner (aligncore.match).
Output (committed to the repo, used by the cloud renderer — no GPU needed there):
  data/align/<reciter>/<sss>.json = {"url", "dur", "basmala": [[s,e]..]|null, "ayat": {"n": {"w": [[s,e]..], "cov": c}}}
Times are absolute seconds inside the surah file.

usage: align_quran.py [reciter ...] [--surah N]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import aligncore as C  # noqa: E402  (also sets up the CUDA dll paths)

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(r"C:\Users\t8646\prv60_clipper\quran_audio_cache")
Q = json.loads((ROOT / "data" / "quran_words.json").read_text(encoding="utf-8"))
REC = json.loads((ROOT / "data" / "reciters.json").read_text(encoding="utf-8"))
BASMALA = ["بِسْمِ", "ٱللَّهِ", "ٱلرَّحْمَـٰنِ", "ٱلرَّحِيمِ"]
AYAT = {}
for k in Q:
    s, n = map(int, k.split(":"))
    AYAT[s] = max(AYAT.get(s, 0), n)


def download(url, f):
    if f.is_file():
        return f
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".part")
    for k in range(4):
        try:
            with requests.get(url, headers=C.H, stream=True, timeout=900) as r:
                r.raise_for_status()
                with open(tmp, "wb") as o:
                    for ch in r.iter_content(1 << 16):
                        o.write(ch)
            tmp.rename(f)
            return f
        except Exception as e:
            print("   retry download", e, flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError(url)


def transcribe(src, cache_json):
    if cache_json.is_file():
        return [tuple(x) for x in json.loads(cache_json.read_text(encoding="utf-8"))]
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    segs, _ = C.model().transcribe(audio, language="ar", word_timestamps=True, beam_size=5, vad_filter=True,
                                   initial_prompt="بسم الله الرحمن الرحيم", hallucination_silence_threshold=1.0)
    ww = [(w.word.strip(), round(w.start, 3), round(w.end, 3)) for s in segs for w in s.words]
    cache_json.write_text(json.dumps(ww, ensure_ascii=False), encoding="utf-8")
    return ww


def place(qwords, ww, start_i):
    """Align one ayah in the words after index start_i. Returns (spans, cov, next index)."""
    span = len(qwords) * 3 + 40
    win = ww[start_i:start_i + span]
    spans, cov = C.match(qwords, win)
    if not spans:
        return None, cov, start_i
    end_t = spans[-1][1]
    nxt = start_i
    while nxt < len(ww) and ww[nxt][1] < end_t - 0.12:
        nxt += 1
    return spans, cov, nxt


def do_surah(rk, su):
    out = ROOT / "data" / "align" / rk / f"{su:03d}.json"
    if out.is_file():
        return None
    url = REC[rk]["server"] + f"{su:03d}.mp3"
    src = download(url, CACHE / rk / f"{su:03d}.mp3")
    dur = C.dur(src)
    t0 = time.time()
    ww = transcribe(src, CACHE / rk / f"{su:03d}.words.json")
    res = {"url": url, "dur": round(dur, 3), "basmala": None, "ayat": {}}
    i = 0
    if su not in (1, 9):
        sp, cov, i2 = place(BASMALA, ww[:40], 0)
        if sp and cov > 0.6:
            res["basmala"] = [[round(s, 2), round(e, 2)] for s, e in sp]
            i = i2
    low = []
    for n in range(1, AYAT[su] + 1):
        qw = Q[f"{su}:{n}"]["w"]
        sp, cov, i2 = place(qw, ww, i)
        if not sp:  # not found right after the previous ayah: search a bit wider before giving up
            sp, cov, i2 = place(qw, ww, max(0, i - 10))
        if not sp or cov < 0.6:  # whisper skipped / hallucinated here: re-listen to just this stretch with the ayah as prompt
            t_from = ww[i][1] - 1.0 if i < len(ww) else max(0, dur - 120)
            est = max(20.0, C.letters(" ".join(qw)) * 0.12)
            loc = C.whisper_words(src, max(0, t_from), min(dur, t_from + est * 3 + 20), " ".join(C.norm(w) for w in qw))
            sp2, cov2 = C.match(qw, loc)
            if sp2 and cov2 > cov:
                sp, cov = sp2, cov2
                i2 = i
                while i2 < len(ww) and ww[i2][1] < sp[-1][1] - 0.12:
                    i2 += 1
        if sp:
            res["ayat"][str(n)] = {"w": [[round(s, 2), round(e, 2)] for s, e in sp], "cov": round(cov, 2)}
            i = i2
        if not sp or cov < 0.6:
            low.append(n)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    covs = [a["cov"] for a in res["ayat"].values()]
    print(f"{rk} {su:03d}: {len(res['ayat'])}/{AYAT[su]} ayat, mean cov {sum(covs) / max(1, len(covs)):.2f}, "
          f"low {low[:12]}{'…' if len(low) > 12 else ''}, {dur / 60:.1f} min audio in {time.time() - t0:.0f}s", flush=True)
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only_s = int(sys.argv[sys.argv.index("--surah") + 1]) if "--surah" in sys.argv else None
    if only_s:
        args = [a for a in args if a != str(only_s)]
    # surah-major order: every reciter gets surah 1, then surah 2 … so the khatma can start early
    for su in ([only_s] if only_s else range(1, 115)):
        for rk in args or list(REC):
            if su not in REC[rk]["surahs"]:
                continue
            try:
                do_surah(rk, su)
            except Exception as e:
                print(f"{rk} {su:03d}: ERROR {e}", flush=True)


if __name__ == "__main__":
    main()
