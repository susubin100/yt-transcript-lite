from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import urllib.parse as up, re, logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, VideoUnavailable, NoTranscriptFound

app = FastAPI(title="yt-transcript-lite", version="1.1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-transcript-lite")

class TranscriptResp(BaseModel):
    video_id: str
    lang: str
    text: str
    source: str
    tried: list[str]

@app.get("/")
def root(): return {"ok": True, "service": "yt-transcript-lite", "version": "1.1.1"}

@app.get("/health")
def health(): return {"status": "healthy"}

def extract_video_id(url: str):
    p = up.urlparse(url)
    if "youtu.be" in url: return p.path.strip("/")
    if "youtube.com" in url: return (up.parse_qs(p.query).get("v") or [None])[0]
    return None

def _clean(s: str): return re.sub(r"\s+", " ", s).strip()

@app.get("/transcript", response_model=TranscriptResp)
def transcript(
    url: str,
    langs: str = "en,vi,auto,ja,es,pt,fr,de,id,ms,hi,zh-Hans,zh-Hant,ru,ko,th",
    allow_translate: bool = True
):
    vid = extract_video_id(url)
    if not vid: raise HTTPException(400, "Invalid YouTube URL")
    tried = []
    try:
        listing = YouTubeTranscriptApi.list_transcripts(vid)
        prefer = [x.strip() for x in langs.split(",") if x.strip()]

        for lang in prefer:  # manual first
            tried.append(f"manual:{lang}")
            try:
                t = listing.find_manually_created_transcript([lang])
                text = " ".join(c["text"] for c in t.fetch() if c["text"].strip())
                return {"video_id": vid, "lang": t.language_code, "text": _clean(text), "source": "manual", "tried": tried}
            except Exception: pass

        for lang in prefer:  # auto-generated
            tried.append(f"generated:{lang}")
            try:
                t = listing.find_generated_transcript([lang])
                text = " ".join(c["text"] for c in t.fetch() if c["text"].strip())
                return {"video_id": vid, "lang": t.language_code, "text": _clean(text), "source": "generated", "tried": tried}
            except Exception: pass

        if allow_translate:  # translate manual
            for target in prefer:
                tried.append(f"translate->{target}")
                for t in listing:
                    if not t.is_translatable: continue
                    try:
                        tt = t.translate(target)
                        text = " ".join(c["text"] for c in tt.fetch() if c["text"].strip())
                        return {"video_id": vid, "lang": target, "text": _clean(text), "source": "translated", "tried": tried}
                    except Exception: continue

        for t in listing:  # any remaining
            try:
                text = " ".join(c["text"] for c in t.fetch() if c["text"].strip())
                return {"video_id": vid, "lang": t.language_code, "text": _clean(text), "source": "manual" if not t.is_generated else "generated", "tried": tried}
            except Exception: continue

        raise HTTPException(404, "No transcripts available for this video.")

    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
        log.warning(f"Transcript not available: {e}")
        raise HTTPException(404, str(e))
    except Exception as e:
        log.exception("Unhandled error")
        raise HTTPException(500, f"Internal error: {e}")
