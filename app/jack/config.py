"""Jack settings — stored in config/jack_settings.json."""

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
SETTINGS_FILE = CONFIG_DIR / "jack_settings.json"

ASSISTANT_NAME = "Jack"

DEFAULTS = {
    "name": ASSISTANT_NAME,
    "language": "hinglish",
    # Order in which LLM backends are tried. "local" = no-AI database answer.
    "provider_order": ["groq", "ollama", "local"],
    # Tried in order — each Groq model has its own free-tier rate limit,
    # so when one is rate-limited Jack moves to the next.
    "groq_models": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
    "ollama_model": "llama3.1",
    # Voice (used by Sections 4/5)
    "tts_voice": "hi-IN-MadhurNeural",
    "tts_rate": "+5%",
    "voice_reply": True,            # speak Jack's replies out loud
    "wake_word_enabled": False,     # always-listening "Hey Jack" (uses Groq Whisper per phrase)
    "wake_word": "hey jack",
    "stt_models": ["whisper-large-v3-turbo", "whisper-large-v3"],
    "hotkey": "<Control-space>",
    # How many past messages Jack remembers in one session
    "max_history_messages": 16,
}


def load_settings() -> dict:
    settings = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            settings.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"[Jack] Could not read settings, using defaults: {e}")
    return settings


def save_settings(settings: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
