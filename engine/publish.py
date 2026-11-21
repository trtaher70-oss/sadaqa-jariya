"""Publish a finished reel. Secrets come from environment variables (GitHub Actions secrets):
  IG_USER_ID, IG_TOKEN            Instagram professional account id + (system-user) access token
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   YouTube (optional)
"""
import os
import time

import requests

GRAPH = "https://graph.facebook.com/" + os.environ.get("GRAPH_VERSION", "v23.0")


def _ig_prepare(mp4, caption, thumb_ms, uid, tok):
    """Container → upload → wait until Instagram has processed the video. Returns the container id."""
    c = requests.post(f"{GRAPH}/{uid}/media", data={"media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
                                                    "share_to_feed": "true", "thumb_offset": str(thumb_ms), "access_token": tok},
                      timeout=120).json()
    if "id" not in c:
        raise RuntimeError(f"instagram container: {c}")
    size = os.path.getsize(mp4)
    with open(mp4, "rb") as f:
        up = requests.post(f"https://rupload.facebook.com/ig-api-upload/{os.environ.get('GRAPH_VERSION', 'v23.0')}/{c['id']}",
                           headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)}, data=f, timeout=900).json()
    if not up.get("success"):
        raise RuntimeError(f"instagram upload: {up}")
    for _ in range(90):  # wait for Instagram to process the video (up to 15 min)
        st = requests.get(f"{GRAPH}/{c['id']}", params={"fields": "status_code,status", "access_token": tok}, timeout=60).json()
        if st.get("status_code") == "FINISHED":
            return c["id"]
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"instagram processing: {st}")
        time.sleep(10)
    raise RuntimeError("instagram processing: not finished after 15 min")


def instagram(mp4, caption, thumb_ms=1500):
    uid, tok = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
    # Instagram sometimes fails to process an upload ("Request processing failed"): start over with a new
    # container, up to 5 times. Nothing is visible before media_publish, so these retries can never double-post.
    last = None
    for attempt in range(5):
        try:
            cid = _ig_prepare(mp4, caption, thumb_ms, uid, tok)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"instagram attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(60 * (attempt + 1))
    else:
        raise RuntimeError(f"{last} (after 5 attempts)")
    pub = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=120).json()
    if "id" not in pub:
        raise RuntimeError(f"instagram publish: {pub}")
    link = requests.get(f"{GRAPH}/{pub['id']}", params={"fields": "permalink", "access_token": tok}, timeout=60).json()
    return {"id": pub["id"], "url": link.get("permalink", "")}


def youtube(mp4, title, description, tags=None, category="27"):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"], client_id=os.environ["YT_CLIENT_ID"],
                        client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"])
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": (tags or [])[:30], "categoryId": category,
                        "defaultLanguage": "ar"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(mp4), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return {"id": resp["id"], "url": f"https://youtube.com/shorts/{resp['id']}"}


def enabled(name):
    return {"instagram": bool(os.environ.get("IG_TOKEN")), "youtube": bool(os.environ.get("YT_REFRESH_TOKEN"))}[name]
