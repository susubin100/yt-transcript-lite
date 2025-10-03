import time, random
from functools import lru_cache
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, VideoUnavailable, NoTranscriptFound
from fastapi import FastAPI, HTTPException

MAX_RETRIES = 5
BASE_SLEEP = 1.5  # giây

@lru_cache(maxsize=512)
def _cached_result(key: str) -> dict | None:
    # placeholder cho lru_cache; mình dùng như 1 memo wrapper
    return None

def _set_cache(key: str, value: dict):
    _cached_result.cache_clear()
    # mẹo: lưu vào global map thay vì lru_cache nếu muốn TTL, ở đây demo đơn giản
    _cached_result.__wrapped__ = lambda k: value  # NOT for prod; demo ý tưởng

def fetch_with_backoff(video_id: str, languages: list[str]):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            listing = YouTubeTranscriptApi.list_transcripts(video_id)
            # manual
            for lang in languages:
                try:
                    t = listing.find_manually_created_transcript([lang])
                    text = " ".join(x["text"] for x in t.fetch() if x["text"].strip())
                    return {"lang": t.language_code, "text": text, "source": "manual"}
                except Exception:
                    pass
            # auto
            for lang in languages:
                try:
                    t = listing.find_generated_transcript([lang])
                    text = " ".join(x["text"] for x in t.fetch() if x["text"].strip())
                    return {"lang": t.language_code, "text": text, "source": "generated"}
                except Exception:
                    pass
            # any
            for t in listing:
                try:
                    text = " ".join(x["text"] for x in t.fetch() if x["text"].strip())
                    return {"lang": t.language_code, "text": text, "source": "unknown"}
                except Exception:
                    pass

            raise NoTranscriptFound("No transcripts available.")
        except Exception as e:
            last_err = e
            # backoff có jitter để né 429
            sleep = BASE_SLEEP * (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
            time.sleep(sleep)
    raise last_err

@app.get("/transcript")
def transcript(url: str, langs: str = "en,vi,auto,ja,es,pt,fr,de,id,ms"):
    vid = extract_video_id(url)
    if not vid:
        raise HTTPException(400, "Invalid YouTube URL")

    cache_key = f"{vid}|{langs}"
    cached = _cached_result(cache_key)
    if isinstance(cached, dict):
        return {"video_id": vid, **cached, "cached": True}

    try:
        prefer = [x.strip() for x in langs.split(",") if x.strip()]
        data = fetch_with_backoff(vid, prefer)
        # ghi cache
        _set_cache(cache_key, data)
        # nới nhịp gọi để tránh 429 khi end-user spam
        time.sleep(random.uniform(1.0, 2.0))
        return {"video_id": vid, **data, "cached": False}
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        # nếu log thấy 'Too Many Requests' => 429 từ Google Sorry page
        raise HTTPException(500, f"Internal error (likely 429 rate limit): {e}")
