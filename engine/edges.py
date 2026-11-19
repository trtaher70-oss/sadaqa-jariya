"""Where the reciter's voice really starts / ends, from the audio energy (not from whisper's word times,
which end before the final madd — e.g. «ٱلضَّآلِّينَ» goes on for seconds after whisper's last timestamp).

Silence = 50 ms frames quieter than (local noise floor + 7 dB) for at least 0.3 s. Works with reverb-heavy
recordings where a fixed -35 dB threshold never triggers.
"""
import subprocess

import numpy as np

FR = 0.05  # frame length (s)
RUN = 6  # frames of quiet = 0.3 s


def _env(src, t0, t1):
    pcm = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t0):.3f}", "-to", f"{t1:.3f}", "-i", str(src),
                          "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    n = int(16000 * FR)
    if len(a) < n * 4:
        return None, None
    a = a[: len(a) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((a ** 2).mean(axis=1)) + 1e-9)
    return db, np.percentile(db, 5) + 7.0


def voice_end(src, t, limit=None):
    """First real silence after time t (the last word's whisper end). Never past `limit`."""
    t0 = max(0.0, t - 20)
    t1 = t + 12 if limit is None else min(t + 12, limit + 0.5)
    db, thr = _env(src, t0, t1)
    if db is None:
        return t + 0.5
    i = int((t - t0) / FR)
    run = 0
    for k in range(max(0, i), len(db)):
        run = run + 1 if db[k] < thr else 0
        if run >= RUN:
            end = t0 + (k - RUN + 1) * FR + 0.12
            return end if limit is None else min(end, limit)
    if limit is not None:
        b = _breath(db, i + int(0.3 / FR), int((limit - t0) / FR))
        if b is not None:
            return t0 + b * FR + 0.05
    end = t + 2.0
    return end if limit is None else min(end, limit)


def _breath(db, i0, i1):
    """Index of the quietest moment (5-frame average) between frames i0..i1 — the reciter's breath."""
    i0, i1 = max(0, i0), min(len(db) - 1, i1)
    if i1 - i0 < 3:
        return None
    sm = np.convolve(db, np.ones(5) / 5, mode="same")
    return i0 + int(np.argmin(sm[i0:i1 + 1]))


def voice_start(src, t, limit=None):
    """Where the ayah's voice begins around time t (the first word's whisper start, which can sit inside the
    previous ayah's madd). Real silence just before t if there is one, else the quietest moment (the breath)
    in t-2 s … t+1.2 s. Never before `limit`."""
    lo = t - 2.0 if limit is None else max(t - 2.0, limit)
    t0 = max(0.0, lo - 20)
    db, thr = _env(src, t0, t + 2)
    if db is None:
        return max(0.0, t - 0.4)
    i, ilo = min(len(db) - 1, int((t - t0) / FR)), int((lo - t0) / FR)
    run = 0
    for k in range(i, ilo - 1, -1):  # real silence right before t
        run = run + 1 if db[k] < thr else 0
        if run >= RUN:
            return max(lo, t0 + (k + RUN) * FR - 0.08)
    b = _breath(db, ilo, i + int(1.2 / FR))
    return max(lo, 0.0, t0 + b * FR - 0.05) if b is not None else max(lo, t - 0.4, 0.0)
