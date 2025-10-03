from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import urllib.parse as up, re
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI(title="yt-transcript-lite", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class TranscriptResp(BaseModel):
    video_id: str
    lang: str
    text: str

def extract_video_id(url: str) -> str | None:
    p = up.urlparse(url)
    if "youtu.be" in url:
        return p.path.strip("/")
    if "youtube.com" in url:
        q = up.parse_qs(p.query)
        return (q.get("v") or [None])[0]
    return None

@app.get("/transcript", response_model=TranscriptResp)
def transcript(url: str = Query(..., description="YouTube URL"), langs: str = "en,vi"):
    vid = extract_video_id(url)
    if not vid:
        raise HTTPException(400, "Invalid YouTube URL")
    for lang in [x.strip() for x in langs.split(",") if x.strip()]:
        try:
            chunks = YouTubeTranscriptApi.get_transcript(vid, languages=[lang])
            text = " ".join(c["text"] for c in chunks if c["text"].strip())
            text = re.sub(r"\s+", " ", text).strip()
            return {"video_id": vid, "lang": lang, "text": text}
        except Exception:
            continue
    raise HTTPException(404, "Transcript not found for requested languages")
