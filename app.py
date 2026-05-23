import streamlit as st
import streamlit.components.v1 as components
import base64
import hashlib
import uuid

from utils.llm import get_response_stream, transcribe_audio, get_active_provider_name
from utils.tts import generate_tts_audio
from utils.logger import logger
from utils.cache import clear_api_cache


# ─────────────────────────────────────────────
# Helper functions (defined first to avoid NameError)
# ─────────────────────────────────────────────
def _play_tts(text: str):
    """Generate neural TTS and autoplay it; fall back to browser TTS."""
    audio_bytes = generate_tts_audio(text)
    if audio_bytes:
        b64 = base64.b64encode(audio_bytes).decode()
        play_id = uuid.uuid4().hex
        components.html(f"""
<script>
(function() {{
  const key = 'played_{play_id}';
  if (sessionStorage.getItem(key)) return;
  sessionStorage.setItem(key, '1');
  const audio = new Audio('data:audio/mp3;base64,{b64}');
  audio.play().catch(e => console.warn('Autoplay blocked:', e));
}})();
</script>
""", height=0)
    else:
        # Fallback: browser speech synthesis
        safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        play_id = uuid.uuid4().hex
        components.html(f"""
<script>
(function() {{
  const key = 'played_{play_id}';
  if (sessionStorage.getItem(key)) return;
  sessionStorage.setItem(key, '1');
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(`{safe}`);
  u.lang = 'en-US'; u.rate = 0.92; u.pitch = 1.05;
  window.speechSynthesis.speak(u);
}})();
</script>
""", height=0)


def _render_audio_player(audio_bytes: bytes, player_id: str, autoplay: bool = False) -> None:
    """Embed a compact styled play/pause + restart audio player inside a chat bubble."""
    b64 = base64.b64encode(audio_bytes).decode()
    auto_play_js = """
  setTimeout(() => {
    a.play().catch(e => console.warn('Autoplay blocked:', e));
  }, 150);
""" if autoplay else ""

    components.html(f"""
<style>
body{{margin:0;padding:2px 0;background:transparent;font-family:Inter,sans-serif;overflow:hidden;}}
.pl{{display:flex;align-items:center;gap:7px;padding:5px 10px;
  background:rgba(99,102,241,0.09);border:1px solid rgba(99,102,241,0.2);
  border-radius:20px;width:fit-content;}}
.cb{{background:rgba(99,102,241,0.18);border:none;color:#a5b4fc;
  border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:0.8rem;
  display:flex;align-items:center;justify-content:center;transition:background 0.15s;}}
.cb:hover{{background:rgba(99,102,241,0.38);color:#c7d2fe;}}
.sk{{-webkit-appearance:none;width:110px;height:3px;
  background:rgba(255,255,255,0.13);border-radius:2px;cursor:pointer;outline:none;}}
.sk::-webkit-slider-thumb{{-webkit-appearance:none;width:10px;height:10px;
  border-radius:50%;background:#6366f1;cursor:pointer;}}
.td{{color:#64748b;font-size:0.67rem;white-space:nowrap;min-width:70px;}}
</style>
<audio id="a{player_id}" src="data:audio/mp3;base64,{b64}"></audio>
<div class="pl">
  <button class="cb" id="pb{player_id}" onclick="tp_{player_id}()" title="Play / Pause">&#9654;</button>
  <input class="sk" type="range" id="sk{player_id}" value="0" step="0.1">
  <span class="td" id="td{player_id}">0:00</span>
  <button class="cb" onclick="ra_{player_id}()" title="Restart from beginning">&#8635;</button>
</div>
<script>
(function(){{
  const a=document.getElementById('a{player_id}'),
        sk=document.getElementById('sk{player_id}'),
        td=document.getElementById('td{player_id}'),
        pb=document.getElementById('pb{player_id}');
  const fmt=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
  window.tp_{player_id}=function(){{a.paused?a.play():a.pause();}};
  window.ra_{player_id}=function(){{a.currentTime=0;a.play();}};
  a.onplay=()=>{{pb.innerHTML='&#9646;&#9646;';}};
  a.onpause=()=>{{pb.innerHTML='&#9654;';}};
  a.onended=()=>{{pb.innerHTML='&#9654;';sk.value=0;td.textContent='0:00';}};
  a.ontimeupdate=()=>{{
    if(!a.duration)return;
    sk.value=a.currentTime/a.duration*100;
    td.textContent=fmt(a.currentTime)+' / '+fmt(a.duration);
  }};
  sk.oninput=()=>{{a.currentTime=sk.value/100*a.duration;}};
  {auto_play_js}
}})();
</script>
""", height=54)


def handle_query(user_query: str, source: str):
    """Display user message, stream LLM reply, generate+cache TTS, update history."""
    logger.info(f"Handling {source} query: '{user_query}'")

    st.session_state.messages.append({"role": "user", "content": user_query})

    with st.chat_message("user", avatar="🙋"):
        st.markdown(user_query)

    with st.chat_message("assistant", avatar="🧑‍💻"):
        reply = st.write_stream(
            get_response_stream(st.session_state.messages)
        )

    st.session_state.messages.append({"role": "assistant", "content": reply})

    # Generate TTS once and cache by message index.
    # Stored in auto_tts_id for auto-play via the inline player after rerun,
    # and in tts_cache[msg_idx] so the player can replay from memory.
    msg_idx = len(st.session_state.messages) - 1
    with st.spinner("Preparing voice…"):
        audio_bytes = generate_tts_audio(reply)
    st.session_state.tts_cache[msg_idx] = audio_bytes  # may be None
    if audio_bytes:
        st.session_state.auto_tts_id       = msg_idx
        st.session_state.auto_tts_fallback = None
    else:
        st.session_state.auto_tts_id       = None
        st.session_state.auto_tts_fallback = reply

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Afrid | Interview Bot",
    page_icon="🎙️",
    layout="centered",
)

# ─────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.stApp {
    background: linear-gradient(135deg, #0d0f14 0%, #111827 50%, #0d0f14 100%);
    min-height: 100vh;
}

/* ── Header ── */
.bot-header {
    text-align: center;
    padding: 2.5rem 0 1.2rem;
}
.bot-avatar {
    width: 76px; height: 76px;
    border-radius: 50%;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.9rem;
    margin: 0 auto 0.9rem;
    box-shadow: 0 0 32px rgba(99,102,241,0.45);
}
.bot-name { font-size: 1.6rem; font-weight: 700; color: #f1f5f9; margin: 0; letter-spacing: -0.5px; }
.bot-subtitle { font-size: 0.84rem; color: #64748b; margin-top: 0.25rem; }
.status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: #22c55e; margin-right: 6px;
    animation: pulse 2s infinite;
}
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.35; } }

/* ── Divider ── */
.thin-hr { border: none; border-top: 1px solid rgba(255,255,255,0.07); margin: 0.8rem 0 1rem; }

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    border-radius: 16px !important;
    padding: 0.8rem 1rem !important;
    margin-bottom: 0.5rem !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    background: rgba(255,255,255,0.03) !important;
    backdrop-filter: blur(10px);
}

/* ── Suggestion chip buttons — key override ── */
.st-key-suggestion_chips button {
    background: rgba(99,102,241,0.1) !important;
    border: 1px solid rgba(99,102,241,0.25) !important;
    color: #a5b4fc !important;
    border-radius: 20px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 0.35rem 0.6rem !important;
    white-space: nowrap !important;
    transition: all 0.2s ease !important;
    font-family: 'Inter', sans-serif !important;
    min-height: unset !important;
    height: auto !important;
    line-height: 1.4 !important;
}
.st-key-suggestion_chips button:hover {
    background: rgba(99,102,241,0.2) !important;
    border-color: rgba(99,102,241,0.5) !important;
    color: #c7d2fe !important;
    transform: translateY(-1px);
}

/* ── Audio input styling ── */
[data-testid="stAudioInput"] {
    background: rgba(99,102,241,0.07) !important;
    border: 1px solid rgba(99,102,241,0.2) !important;
    border-radius: 14px !important;
}

/* ── Text input area ── */
[data-testid="stChatInput"] textarea {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(99,102,241,0.3) !important;
    border-radius: 12px !important;
    color: #f1f5f9 !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: rgba(99,102,241,0.7) !important;
    box-shadow: 0 0 0 2px rgba(99,102,241,0.2) !important;
}

/* ── Footer ── */
.footer {
    text-align: center; color: #374151;
    font-size: 0.74rem; padding: 2rem 0 1rem;
}

/* ── Replay button — ghost, icon-only ── */
.replay-btn-wrap { margin-top: 0.45rem; }
.replay-btn-wrap .stButton > button {
    background: transparent !important;
    border: 1px solid rgba(99,102,241,0.25) !important;
    color: #64748b !important;
    border-radius: 20px !important;
    font-size: 0.75rem !important;
    padding: 0.2rem 0.65rem !important;
    min-height: unset !important;
    height: auto !important;
    line-height: 1.3 !important;
    transition: all 0.2s !important;
}
.replay-btn-wrap .stButton > button:hover {
    background: rgba(99,102,241,0.12) !important;
    border-color: rgba(99,102,241,0.5) !important;
    color: #a5b4fc !important;
    transform: none !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
    logger.info("New session — conversation initialized.")

if "pending_input" not in st.session_state:
    st.session_state.pending_input = None   # {"text": str, "source": str}

if "last_audio_hash" not in st.session_state:
    st.session_state.last_audio_hash = None

if "replay_text" not in st.session_state:
    st.session_state.replay_text = None    # text to re-speak on next render

if "auto_tts_id" not in st.session_state:
    st.session_state.auto_tts_id = None    # msg index to auto-play after rerun

if "auto_tts_fallback" not in st.session_state:
    st.session_state.auto_tts_fallback = None  # fallback text for browser TTS

if "tts_cache" not in st.session_state:
    st.session_state.tts_cache = {}  # {msg_idx: bytes | None} — never regenerates

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown("""
<div class="bot-header">
  <div class="bot-avatar">🧑‍💻</div>
  <p class="bot-name">Mohd Afrid</p>
  <p class="bot-subtitle">
    <span class="status-dot"></span>AI/ML Engineer · Interactive Resume Bot
  </p>
</div>
""", unsafe_allow_html=True)

# Clear chat and cache buttons — right-aligned ghost pills
_c1, _c2, _c3 = st.columns([8, 1, 1])
with _c2:
    if st.button("🗑️", key="clear_chat", help="Clear conversation"):
        st.session_state.messages       = []
        st.session_state.tts_cache      = {}
        st.session_state.auto_tts_id       = None
        st.session_state.auto_tts_fallback = None
        st.session_state.pending_input  = None
        st.session_state.last_audio_hash   = None
        logger.info("Chat cleared by user.")
        st.rerun()
with _c3:
    if st.button("🧹", key="clear_cache", help="Clear API response cache & chat history"):
        clear_api_cache()
        from utils.cache import clear_tts_cache
        clear_tts_cache()
        st.session_state.messages       = []
        st.session_state.tts_cache      = {}
        st.session_state.auto_tts_id       = None
        st.session_state.auto_tts_fallback = None
        st.session_state.pending_input  = None
        st.session_state.last_audio_hash   = None
        logger.info("API Cache and chat cleared by user.")
        st.toast("🧹 Cache & history cleared!")
        st.rerun()

# ─────────────────────────────────────────────
# Suggestion chips — 2 rows so text never overlaps
# ─────────────────────────────────────────────
SUGGESTIONS = [
    "Tell me about yourself",
    "What's your superpower?",
    "Top 3 growth areas?",
    "Why 100x?",
    "How do you push limits?",
]

# Wrap suggestion chips in a keyed container so their custom CSS styles don't leak into st.audio_input
with st.container(key="suggestion_chips"):
    # Row 1 — first 3
    row1 = st.columns(3)
    for col, s in zip(row1, SUGGESTIONS[:3]):
        with col:
            if st.button(s, key=f"chip_{s}", use_container_width=True):
                logger.info(f"Chip → '{s}'")
                st.session_state.pending_input = {"text": s, "source": "chip"}

    # Row 2 — last 2, centred with padding columns
    _, c1, c2, _ = st.columns([0.5, 2, 2, 0.5])
    for col, s in zip([c1, c2], SUGGESTIONS[3:]):
        with col:
            if st.button(s, key=f"chip_{s}", use_container_width=True):
                logger.info(f"Chip → '{s}'")
                st.session_state.pending_input = {"text": s, "source": "chip"}

st.markdown('<hr class="thin-hr">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Voice input — st.audio_input + Groq Whisper Audio
# ─────────────────────────────────────────────
audio_value = st.audio_input(
    "🎙️ Record your question — click the mic, speak, then click stop",
    key="voice_recorder",
)

if audio_value is not None:
    raw = audio_value.getvalue()
    audio_hash = hashlib.md5(raw).hexdigest()
    if audio_hash != st.session_state.last_audio_hash:
        st.session_state.last_audio_hash = audio_hash
        with st.spinner("Transcribing your question…"):
            # Detect format from content type if available
            ext = "webm"
            if hasattr(audio_value, "type") and audio_value.type:
                ext = audio_value.type.split("/")[-1].split(";")[0]
            transcript = transcribe_audio(raw, f"audio.{ext}")
        if transcript:
            logger.info(f"Voice → '{transcript}'")
            st.session_state.pending_input = {"text": transcript, "source": "voice"}
            st.rerun()
        else:
            st.warning("Couldn't hear anything clearly. Please try again.")

st.markdown('<hr class="thin-hr">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Chat history
# ─────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    avatar = "🧑‍💻" if msg["role"] == "assistant" else "🙋"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            cached_audio = st.session_state.tts_cache.get(i)
            if cached_audio:
                should_autoplay = (st.session_state.auto_tts_id == i)
                _render_audio_player(cached_audio, player_id=str(i), autoplay=should_autoplay)
                if should_autoplay:
                    st.session_state.auto_tts_id = None
            else:
                _, btn_col = st.columns([7, 3])
                with btn_col:
                    if st.button("🎙️ Retry Voice", key=f"retry_tts_{i}", use_container_width=True):
                        logger.info(f"Retry voice requested for message index {i}")
                        with st.spinner("Generating voice…"):
                            audio_bytes = generate_tts_audio(msg["content"])
                        if audio_bytes:
                            st.session_state.tts_cache[i] = audio_bytes
                            st.session_state.auto_tts_id = i
                            st.session_state.auto_tts_fallback = None
                            st.rerun()
                        else:
                            st.error("Failed to generate voice. Please check logs.")

# ─────────────────────────────────────────────
# Auto-TTS Fallback: play queued fallback browser speech synthesis if needed
# ─────────────────────────────────────────────
if st.session_state.auto_tts_fallback:
    _txt  = st.session_state.auto_tts_fallback
    _safe = _txt.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    st.session_state.auto_tts_fallback = None
    components.html(f"""
<script>
(function() {{
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(`{_safe}`);
  u.lang = 'en-US'; u.rate = 0.92; u.pitch = 1.05;
  window.speechSynthesis.speak(u);
}})();
</script>
""", height=0)

# ─────────────────────────────────────────────
# Process pending input (chip or voice)
# ─────────────────────────────────────────────
if st.session_state.pending_input:
    pending = st.session_state.pending_input
    st.session_state.pending_input = None
    if pending["text"].strip():
        handle_query(pending["text"].strip(), pending["source"])
        st.rerun()

# ─────────────────────────────────────────────
# Text chat input
# ─────────────────────────────────────────────
if user_input := st.chat_input("Type your question or record with the mic above…"):
    logger.info(f"Text → '{user_input}'")
    handle_query(user_input.strip(), "text")
    st.rerun()

# ─────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────
st.markdown(f"""
<div class="footer">
  Built for 100x · Powered by {get_active_provider_name()} · edge-tts · Mohd Afrid © 2026
</div>
""", unsafe_allow_html=True)
