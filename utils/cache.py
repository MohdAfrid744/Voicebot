import os
import json
import hashlib
import tempfile
import time
from utils.logger import logger

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_cache.json")

def get_history_hash(conversation_history: list[dict]) -> str:
    """
    Generate a deterministic SHA-256 hash of the normalized conversation history.
    Normalizes inputs by stripping spacing and converting keys and contents to lowercase.
    """
    cleaned_history = []
    for msg in conversation_history:
        cleaned_history.append({
            "role": msg["role"].strip().lower(),
            "content": msg["content"].strip().rstrip("?.!,;:").strip().lower()
        })
    serialized = json.dumps(cleaned_history, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def _read_cache_file() -> dict | None:
    """
    Read the cache file with retries to handle concurrent access / Windows file locks.
    Returns None on persistent read failure, {} if file is empty or does not exist.
    """
    if not os.path.exists(CACHE_FILE):
        return {}
    
    try:
        if os.path.getsize(CACHE_FILE) == 0:
            return {}
    except OSError:
        # File might be locked or modified in flight
        return None

    for attempt in range(5):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # If the file is temporarily empty or being written, retry.
            # Only report actual corruption on the final attempt.
            if attempt < 4:
                time.sleep(0.05 * (attempt + 1))
                continue
            logger.error(f"Cache file is corrupted (JSONDecodeError): {e}")
            return {}
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
        except Exception as e:
            logger.error(f"Error reading cache file on attempt {attempt}: {e}")
            time.sleep(0.05 * (attempt + 1))
    return None

def get_cached_response(conversation_history: list[dict]) -> str | None:
    """
    Lookup a cached response for the given conversation history.
    """
    cache = _read_cache_file()
    if cache:
        cache_key = get_history_hash(conversation_history)
        if cache_key in cache:
            logger.info(f"Cache HIT for history hash: {cache_key}")
            return cache[cache_key]
    return None

def set_cached_response(conversation_history: list[dict], response: str):
    """
    Store the response for the given conversation history in the JSON cache.
    """
    cache_key = get_history_hash(conversation_history)
    cache = _read_cache_file()
    if cache is None:
        logger.error("Failed to load cache file due to persistent read errors. Skipping write to prevent cache loss.")
        return
        
    cache[cache_key] = response
    
    # Write atomically with retries
    dir_name = os.path.dirname(CACHE_FILE)
    for attempt in range(5):
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix="cache_tmp_")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            
            # Atomic replacement of target file
            os.replace(temp_path, CACHE_FILE)
            logger.info(f"Cached response for history hash: {cache_key}")
            return
        except PermissionError:
            # File might be locked on Windows
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            time.sleep(0.05 * (attempt + 1))
        except Exception as e:
            logger.error(f"Error writing to cache on attempt {attempt}: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            time.sleep(0.05 * (attempt + 1))
            
    logger.error("Failed to write cached response after all attempts.")

def clear_api_cache() -> bool:
    """
    Clear all entries from the API cache file.
    """
    dir_name = os.path.dirname(CACHE_FILE)
    for attempt in range(5):
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix="cache_tmp_")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, CACHE_FILE)
            logger.info("API Cache cleared successfully.")
            return True
        except PermissionError:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            time.sleep(0.05 * (attempt + 1))
        except Exception as e:
            logger.error(f"Error clearing API Cache on attempt {attempt}: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            time.sleep(0.05 * (attempt + 1))
    return False


TTS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tts_cache")

def clear_tts_cache() -> bool:
    """
    Clear all cached TTS audio files in the tts_cache directory.
    """
    try:
        if os.path.exists(TTS_CACHE_DIR):
            for filename in os.listdir(TTS_CACHE_DIR):
                if filename.endswith(".mp3"):
                    try:
                        os.remove(os.path.join(TTS_CACHE_DIR, filename))
                    except Exception as e:
                        logger.warning(f"Could not remove cached audio file {filename}: {e}")
            logger.info("TTS audio cache cleared.")
            return True
    except Exception as e:
        logger.error(f"Error clearing TTS audio cache: {e}")
    return False


