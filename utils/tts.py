import asyncio
import concurrent.futures
import re
import hashlib
import os
from utils.logger import logger

# Microsoft Edge neural TTS voices — naturally human-sounding
# Jenny = warm, conversational American female
# Andrew = calm, natural American male
VOICE_FEMALE = "en-US-JennyNeural"
VOICE_MALE   = "en-US-AndrewNeural"

# Pick which voice to use for Afrid
ACTIVE_VOICE = VOICE_MALE

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts_cache")

def get_tts_cache_path(text: str) -> str:
    """Generate a deterministic cache file path based on the text hash and voice settings."""
    key = f"{text}_{ACTIVE_VOICE}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.mp3")


def generate_tts_audio(text: str) -> bytes | None:
    """
    Generate speech audio bytes (MP3) using Microsoft Edge's neural TTS via edge-tts.
    Checks the local disk cache first.
    Splits long text into sentences and fetches them sequentially to prevent WebSocket timeout errors.
    Falls back to None (caller should use browser TTS) if anything goes wrong.
    """
    try:
        # Create cache directory if it doesn't exist
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Check local disk cache
        cache_path = get_tts_cache_path(text)
        if os.path.exists(cache_path):
            logger.info("TTS Cache HIT! Loading audio from disk.")
            with open(cache_path, "rb") as f:
                return f.read()

        import edge_tts

        async def _generate_with_retry() -> bytes:
            # If text is short, handle it in one request to minimize connections
            if len(text) < 400:
                sentences = [text]
            else:
                # Split text by sentence boundaries (periods, question marks, exclamation marks)
                raw_sentences = re.split(r'(?<=[.!?])\s+', text)
                sentences = [s.strip() for s in raw_sentences if s.strip()]
            
            if not sentences:
                return b""

            async def fetch_sentence_tts(sentence: str) -> bytes:
                max_retries = 3
                timeout_per_try = 12.0
                for attempt in range(max_retries):
                    try:
                        logger.info(f"edge-tts fetching sentence ({len(sentence)} chars), attempt {attempt + 1}/{max_retries}...")
                        communicate = edge_tts.Communicate(sentence, ACTIVE_VOICE, rate="+5%", pitch="+0Hz")
                        chunks: list[bytes] = []
                        async def stream_collect():
                            async for chunk in communicate.stream():
                                if chunk["type"] == "audio":
                                    chunks.append(chunk["data"])
                            return b"".join(chunks)
                        
                        audio_data = await asyncio.wait_for(stream_collect(), timeout=timeout_per_try)
                        if audio_data:
                            return audio_data
                    except Exception as ex:
                        logger.warning(f"edge-tts attempt {attempt + 1} failed for: '{sentence[:30]}...': {ex}")
                        if attempt == max_retries - 1:
                            raise ex
                        await asyncio.sleep(0.5)
                raise Exception("Failed to generate TTS for sentence.")

            # Sequentially fetch sentences to prevent concurrent connection rate limits / resets
            results = []
            for s in sentences:
                audio_data = await fetch_sentence_tts(s)
                results.append(audio_data)
            return b"".join(results)

        # Run async in a separate thread so we don't conflict with Streamlit's event loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _generate_with_retry())
            audio_bytes = future.result(timeout=45)

        if audio_bytes:
            # Save generated audio to local disk cache
            try:
                with open(cache_path, "wb") as f:
                    f.write(audio_bytes)
                logger.info(f"TTS audio saved to cache at {cache_path}")
            except Exception as cache_err:
                logger.warning(f"Could not save TTS audio to cache: {cache_err}")

            logger.info(f"edge-tts generated {len(audio_bytes):,} bytes | voice: {ACTIVE_VOICE}")
            return audio_bytes
        
        return None

    except ImportError:
        logger.warning("edge-tts not installed — will use browser TTS fallback.")
        return None
    except Exception as e:
        import traceback
        logger.error(f"edge-tts error: {e}\n{traceback.format_exc()}")
        return None


