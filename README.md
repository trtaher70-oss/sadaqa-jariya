# sadaqa-jariya

Perpetual, unattended publisher for the Instagram account **@sadaqa.tr** (a *sadaqa jariya* — ongoing charity).
Guardian (non-technical) instructions: **[GUARDIAN.md](GUARDIAN.md)** (Arabic).

## How it works
- `.github/workflows/publish.yml` runs every hour. `engine/run.py` publishes each slot of `data/schedule.json`
  whose time (Turkey/Mecca, UTC+3) has passed today and is not done yet; state is committed to `state/state.json`.
- Streams (`engine/build.py`):
  - `curated` — duas/reminder verses from `data/curated.json`, endlessly cycled with the next reciter each cycle.
  - `khatma` — the whole Quran in order (15–50 s passages, cut inside a ruku), reciters rotating; caption = the
    passage reference + *al-Tafsir al-Muyassar* (King Fahd Complex, `data/tafsir_muyassar.json`). Endless.
  - `podcast` — human-approved clips listed in `data/podcast_queue.json` (assets hosted as release files).
- Recitation audio: whole-surah files from mp3quran.net (URLs in `data/align/*/*.json`).
  Per-word timings were computed once, offline, with faster-whisper + a word-level aligner (`tools/align_quran.py`);
  the cloud renderer only cuts audio and renders (`video/`, Remotion 4, pinned versions).
- Text: Uthmani words with waqf marks (`data/quran_words.json`, from Quran.com API v4).

## Secrets (repo Settings → Secrets → Actions)
`IG_USER_ID`, `IG_TOKEN` (Meta system-user token, never expires), optional `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

## Local test
```
pip install -r requirements.txt && (cd video && npm install)
python engine/run.py --slot afternoon --dry
```
