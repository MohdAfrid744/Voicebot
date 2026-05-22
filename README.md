# 🎙️ Afrid | Interactive Resume Voicebot

An interactive, high-fidelity portfolio voicebot for **Mohd Afrid** (AI/ML Engineer). Built using **Streamlit**, **Google Gemini (Gemini 1.5 Flash)** for reasoning & native multimodal audio transcription, and **Microsoft Edge Neural TTS (`edge-tts`)** for conversational voice outputs.

The system is specifically designed to run on a **Free API tier**, implementing advanced local caching and concurrent network optimizations to remain highly responsive and budget-friendly.

---

## 🌟 Key Features

*   **💬 Multimodal Conversational Interface:** Type questions or record audio directly through the UI.
*   **🎙️ Native Audio Transcription:** Utilizes Gemini's multimodal understanding to transcribe user recordings directly without requiring a separate Whisper model.
*   **⚡ Concurrent Neural Speech Synthesis:** Splits generated paragraphs into sentences and requests audio tracks concurrently from Microsoft's Edge TTS API. This results in **4x faster voice prep times (under 4s)**, bypassing WebSocket timeouts.
*   **🎛️ Premium Custom Audio Player:** Integrates a styled, dark-themed HTML/JS play-pause-seek slider bubble directly in each chat turn.
*   **🔄 Hybrid Speech Fallback:** If Microsoft's public TTS server rate-limits or drops the connection, the bot gracefully falls back to the browser's native `SpeechSynthesis` API.
*   **🧠 High-Density Persona Prompt:** Combines resume experience (applied research, AI backends, and RAG systems at Insturix) with a structured, 30-item Q&A reference guide.
*   **🧹 Smart API Disk Caching:** Caches LLM response hashes in `utils/api_cache.json` to prevent repetitive API calls and save precious free-tier quota tokens.
*   **🗑️ Clean Slate Controls:** Instant UI triggers (`🗑️` for resetting Streamlit chat history, `🧹` for programmatically clearing the local API cache file on disk).

---

## 🛠️ Free-Tier Optimization Design

To operate robustly on Gemini's and Edge-TTS's free quotas, this voicebot integrates the following architectural optimizations:
1.  **Response Caching:** Repeats of identical queries (e.g., clicking *"Tell me about yourself"* multiple times) are served instantly from `api_cache.json`, causing 0 API cost.
2.  **Sentence-Level Concurrency:** Instead of sending massive paragraphs to `edge-tts` (which frequently times out on connections under 25s), the text is parsed into sentences and retrieved concurrently. This drops latency from **15.3s to 3.8s** and preserves connection stability.
3.  **Client-Side Fallbacks:** Falls back to local browser engines for text-to-speech if the remote TTS service fails, avoiding application crashes.

---

## 📂 Project Structure

```text
Voicebot/
├── app.py                  # Streamlit application UI & session controller
├── requirements.txt        # Package dependencies
├── .env.example            # Environment variables template
├── .env                    # Local environment config (git-ignored)
├── README.md               # Repository documentation
├── voicebot.log            # System logs
└── utils/
    ├── __init__.py
    ├── prompt.py           # Combined system prompt (resume + Q&A reference guide)
    ├── llm.py              # Google GenAI client (Gemini generation & transcription)
    ├── tts.py              # Sentence-splitting Edge-TTS concurrent synthesis engine
    ├── cache.py            # API cache load/write/clear utilities
    └── logger.py           # Logger configuration
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
Ensure you have **Python 3.10+** installed on your system.

### 2. Clone the Repository
Navigate to your project directory:
```bash
git clone https://github.com/yourusername/voicebot.git
cd voicebot
```

### 3. Create a Virtual Environment
```bash
python -m venv venv
# On Windows (Command Prompt)
venv\Scripts\activate
# On Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# On macOS/Linux
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Copy the example template to create your `.env` file:
```bash
# Windows
copy .env.example .env
# macOS/Linux
cp .env.example .env
```
Open `.env` and configure your API key. (Get your free key from [Google AI Studio](https://aistudio.google.com)):
```ini
# Gemini API Key
GEMINI_API_KEY=AIzaSyYourGeminiApiKeyHere

# Gemini Model configuration (Optional, defaults to gemini-1.5-flash)
GEMINI_MODEL=gemini-1.5-flash
```

### 6. Run the Application
```bash
streamlit run app.py
```
The app will automatically open in your browser at **http://localhost:8501** (or port **8080** if configured).

---

## 🛑 Current Limitations

*   **Free Quota Limits:** Excessive rapid queries may trigger a temporary `429 Resource Exhausted` rate-limit from Google Gemini's free tier. 
*   **Browser Autoplay Blocks:** Many modern browsers block audio autoplay on initial page load until the user interacts with the document (e.g. clicking anywhere on the screen). 
*   **Browser Voice Quality:** The browser fallback TTS depends on the operating system's built-in text-to-speech voice pack, which may sound robotic compared to the Edge Neural voice.
*   **Single-Session Storage:** Streamlit's chat history is kept in session state memory and will reset if the page is reloaded.

---

## 🔮 Future Enhancements

*   **Persistent Sessions:** Save chat history and usage metrics in a lightweight database (e.g., Supabase or SQLite).
*   **Custom Voice Clone:** Train a custom voice model (using ElevenLabs or Coqui) to match Afrid's exact speaking voice.
*   **Dynamic Document RAG:** Integrate a parser to allow users to scan or upload an updated resume PDF to dynamically update the bot's factual knowledge base.
*   **Session Rate-Limiting:** Implement visual client-side cooldown timers to prevent users from spamming the free Gemini API key.
