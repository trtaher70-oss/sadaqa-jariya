# sadaqa-jariya

Perpetual, unattended publisher for the Instagram account **@sadaqa.tr** (a *sadaqa jariya* — ongoing charity).
- Guardian (non-technical) instructions: **[GUARDIAN.md](GUARDIAN.md)** (Arabic)
- Live dashboard: https://trtaher70-oss.github.io/sadaqa-jariya/

## How it works
- `.github/workflows/publish.yml` runs twice an hour. `engine/due.py` (stdlib + node) decides if a slot is due;
  `engine/run.py` publishes every slot of `data/schedule.json` (plus occasion extras) whose time — Turkey/Mecca,
  UTC+3 — has passed today and is not done yet. State is committed to `state/state.json` (keeps the repo active).
- Streams (`engine/build.py`, `engine/queues.py`):
  - `morning_queue` / `podcast_queue` — ready-made reels hosted as files of the release `queue` (podcasts only when `"approved": true`).
  - `curated` — duas/reminder verses (`data/curated.json`), endlessly cycled with the next reciter each cycle.
  - `khatma` — the whole Quran in order (15–50 s passages inside a ruku), reciters rotating; caption = passage
    reference + *al-Tafsir al-Muyassar* (King Fahd Complex, `data/tafsir_muyassar.json`). Waits (never skips) when
    a surah's timings are missing.
  - occasions — `data/occasions.json` rules (Umm al-Qura Hijri via Node ICU, `engine/calendar_hijri.py`,
    adjustable in `data/hijri_adjust.json`) replace a slot's content with a pool from `data/pools.json`
    (Friday, Ramadan, last ten nights, Eids, Arafah, Dhul-Hijja, Ashura, Hijri new year, sacred months, white days).
- Recitation audio: whole-surah files from mp3quran.net. Per-word timings were computed once, offline, with
  faster-whisper + a word-level DP aligner (`tools/align_quran.py`, `tools/aligncore.py`) → `data/align/<reciter>/<surah>.json`.
  The cloud only cuts audio — one continuous piece per reel, edges found from audio energy (`engine/edges.py`) — and renders (`video/`, Remotion 4.0.300 pinned).
- Next posts are prepared in advance (`state/next.json`, release `preview`) and reused at publish time; phone-friendly
  540p copies are published with the dashboard (`docs/`) to GitHub Pages (`site` job / `site.yml`, syntax-checked first).
- Public account numbers for the dashboard: `state/stats.json`; upcoming occasions: `state/calendar.json`.

## Secrets (repo Settings → Secrets → Actions)
`IG_USER_ID`, `IG_TOKEN` (Meta system-user token, never expires), optional `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

## Manual runs (Actions → publish → Run workflow)
- `preview: true` — only prepare the next posts / refresh the dashboard
- `slot: afternoon` + `dry: true` — render a test reel without publishing (attached to the run)

## Local test
```
pip install -r requirements.txt && (cd video && npm install)
python engine/run.py --slot afternoon --dry
```
