import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from utils.prompt import SYSTEM_PROMPT
from utils.logger import logger
from utils.cache import get_cached_response, set_cached_response

load_dotenv()

# Initialize Gemini client
# The SDK automatically uses GEMINI_API_KEY from environment variables
client = genai.Client()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")


def get_response(conversation_history: list[dict]) -> str:
    """
    Non-streaming call. Returns the complete response string.
    Checks cache first; caches new responses.
    """
    cached = get_cached_response(conversation_history)
    if cached is not None:
        return cached

    # Map conversation history roles from 'assistant' to Gemini's expected 'model' role
    contents = []
    for msg in conversation_history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])]
            )
        )

    logger.info(f"LLM request | model={MODEL} | context={len(conversation_history)} msgs")

    start = time.time()
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.6,
                max_output_tokens=512,
            )
        )
        reply = response.text.strip() if response.text else ""
        elapsed = time.time() - start
        logger.info(f"LLM done | {elapsed:.2f}s | {len(reply)} chars")
        if reply:
            set_cached_response(conversation_history, reply)
        return reply
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"LLM error after {elapsed:.2f}s: {e}")
        return f"[Error reaching AI: {e}]"


def get_response_stream(conversation_history: list[dict]):
    """
    Streaming generator — yields text chunks for use with st.write_stream().
    Cache hit → yields full cached response as a single chunk (instant).
    Cache miss → streams tokens from Gemini, then caches the full reply.
    """
    cached = get_cached_response(conversation_history)
    if cached is not None:
        logger.info("Cache HIT — returning instantly via stream.")
        yield cached
        return

    # Map conversation history roles from 'assistant' to Gemini's expected 'model' role
    contents = []
    for msg in conversation_history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])]
            )
        )

    logger.info(f"Streaming LLM request | model={MODEL} | context={len(conversation_history)} msgs")

    start = time.time()
    full_reply = ""
    try:
        response_stream = client.models.generate_content_stream(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.6,
                max_output_tokens=512,
            )
        )
        for chunk in response_stream:
            content = chunk.text
            if content:
                full_reply += content
                yield content

        elapsed = time.time() - start
        logger.info(f"Streaming done | {elapsed:.2f}s | {len(full_reply)} chars")
        if full_reply:
            set_cached_response(conversation_history, full_reply)

    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"Streaming error after {elapsed:.2f}s: {e}")
        yield f"[Error reaching AI: {e}]"


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Transcribe audio bytes to text using Gemini's native multimodal audio capabilities.
    Returns the transcript string, or "" on failure.
    """
    logger.info(f"Transcribing {len(audio_bytes):,} bytes of audio ({filename})…")
    
    # Map extensions to supported audio mime-types
    mime_type = "audio/webm"
    if filename.endswith(".mp3"):
        mime_type = "audio/mp3"
    elif filename.endswith(".wav"):
        mime_type = "audio/wav"
    elif filename.endswith(".ogg"):
        mime_type = "audio/ogg"
    elif filename.endswith(".m4a"):
        mime_type = "audio/m4a"

    try:
        start = time.time()
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=mime_type,
                ),
                "Transcribe the spoken audio exactly. Do not add metadata, comments, or explanations. If there is no speech, return an empty string."
            ]
        )
        text = response.text.strip() if response.text else ""
        elapsed = time.time() - start
        logger.info(f"Transcription succeeded in {elapsed:.2f}s: '{text}'")
        return text
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""
