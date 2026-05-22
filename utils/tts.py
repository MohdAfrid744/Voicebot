import asyncio
import concurrent.futures
import re
from utils.logger import logger

# Microsoft Edge neural TTS voices — naturally human-sounding
# Jenny = warm, conversational American female
# Andrew = calm, natural American male
VOICE_FEMALE = "en-US-JennyNeural"
VOICE_MALE   = "en-US-AndrewNeural"

# Pick which voice to use for Afrid
ACTIVE_VOICE = VOICE_MALE


def generate_tts_audio(text: str) -> bytes | None:
    """
    Generate speech audio bytes (MP3) using Microsoft Edge's neural TTS via edge-tts.
    Splits long text into sentences to prevent WebSocket timeout errors.
    Falls back to None (caller should use browser TTS) if anything goes wrong.
    """
    try:
        import edge_tts

        async def _generate_with_retry() -> bytes:
            # Split text by sentence boundaries (periods, question marks, exclamation marks)
            raw_sentences = re.split(r'(?<=[.!?])\s+', text)
            sentences = [s.strip() for s in raw_sentences if s.strip()]
            if not sentences:
                return b""

            async def fetch_sentence_tts(sentence: str) -> bytes:
                max_retries = 2
                timeout_per_try = 8.0
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
                        await asyncio.sleep(0.3)
                raise Exception("Failed to generate TTS for sentence.")

            # Concurrently fetch all sentences
            tasks = [fetch_sentence_tts(s) for s in sentences]
            results = await asyncio.gather(*tasks)
            return b"".join(results)

        # Run async in a separate thread so we don't conflict with Streamlit's event loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _generate_with_retry())
            audio_bytes = future.result(timeout=30)

        logger.info(f"edge-tts generated {len(audio_bytes):,} bytes | voice: {ACTIVE_VOICE}")
        return audio_bytes

    except ImportError:
        logger.warning("edge-tts not installed — will use browser TTS fallback.")
        return None
    except Exception as e:
        import traceback
        logger.error(f"edge-tts error: {e}\n{traceback.format_exc()}")
        return None

