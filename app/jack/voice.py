"""
Sections 4 + 5 — Jack's ears and mouth.

  Speaker        Edge TTS (hi-IN-MadhurNeural) -> mp3 -> Windows MCI playback.
                 No extra player library needed. speak() is non-blocking and a
                 new speak()/stop() cuts off whatever is playing.
  record_phrase  Mic via `sounddevice`, 16 kHz mono. Starts when you speak,
                 stops after ~1.2 s of silence (simple energy VAD).
  transcribe     Groq Whisper (whisper-large-v3-turbo -> whisper-large-v3).
  WakeWordLoop   Background "Hey Jack" listener: records short phrases and
                 checks the transcript for the wake word. Every phrase is one
                 Groq Whisper request, so it is OFF by default.

All pieces fail soft: a missing package / no mic / no internet gives a
VoiceError with a Hinglish message instead of crashing the app.
"""

import asyncio
import ctypes
import io
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from typing import Callable, Optional

from app.jack.config import load_settings

SAMPLE_RATE = 16000
BLOCK = 1600                      # 100 ms per block
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_PROMPT = ("Hinglish in Roman script. Boss, Jack, phone dead hai, charging nahi ho rahi, "
              "UART, ADB, HW detect chalao, PMIC, EDL, Redmi, Samsung, Vivo, Oppo, MT6765.")

# "Jack" as Whisper tends to hear it (Roman + Devanagari)
WAKE_RE = re.compile(r"\b(hey|hi|hello|ok|okay|he|hay|ae|ai)?[\s,.!]*(jack|jak|jaik|jake|jeck|jac)\b"
                     r"|जैक|जेक|जाक", re.IGNORECASE)


class VoiceError(Exception):
    pass


def _clean_for_tts(text: str) -> str:
    text = re.sub(r"[*_`#>|\[\]{}]", " ", text or "")
    # emojis / symbols Edge TTS would read out or choke on
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]", " ", text)
    text = text.replace("→", " ").replace("•", " ").replace("—", ", ").replace("%", " percent")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]


# ── output: Edge TTS ───────────────────────────────────────────────────────

class _MCI:
    """Tiny wrapper around winmm.dll mciSendString (plays mp3 on any Windows)."""

    def __init__(self):
        self._send = ctypes.windll.winmm.mciSendStringW

    def cmd(self, command: str) -> str:
        buf = ctypes.create_unicode_buffer(256)
        err = self._send(command, buf, 255, 0)
        if err:
            raise VoiceError(f"MCI error {err} for: {command.split()[0]}")
        return buf.value


class Speaker:
    def __init__(self, on_start: Callable[[], None] = None, on_end: Callable[[], None] = None):
        self.on_start = on_start or (lambda: None)
        self.on_end = on_end or (lambda: None)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._gen = 0
        self.speaking = False

    def speak(self, text: str) -> None:
        text = _clean_for_tts(text)
        if not text:
            return
        self.stop()
        self._gen += 1
        gen = self._gen
        threading.Thread(target=self._run, args=(text, gen), daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def prewarm(self) -> None:
        """Do one tiny throwaway synthesis so the FIRST real reply speaks fast.

        The initial Edge TTS call pays for DNS + TLS + websocket setup; doing it
        once in the background at startup hides that cost from the user.
        """
        def go():
            try:
                p = self._synthesize("ok")
                try:
                    os.remove(p)
                except OSError:
                    pass
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()

    def _run(self, text: str, gen: int) -> None:
        with self._lock:                       # one playback at a time
            if gen != self._gen:               # a newer speak() already replaced this one
                return
            self._stop.clear()
            path = None
            try:
                path = self._synthesize(text)
                if self._stop.is_set() or gen != self._gen:
                    return
                self.speaking = True
                self.on_start()
                self._play(path)
            except Exception as e:
                print(f"[Jack voice] speak failed: {e}")
            finally:
                if self.speaking:
                    self.speaking = False
                    try:
                        self.on_end()
                    except Exception:
                        pass
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    @staticmethod
    def _synthesize(text: str) -> str:
        try:
            import edge_tts
        except ImportError:
            raise VoiceError("edge-tts install nahi hai (pip install edge-tts)")
        s = load_settings()
        path = os.path.join(tempfile.gettempdir(), f"jack_tts_{uuid.uuid4().hex[:8]}.mp3")

        async def go():
            comm = edge_tts.Communicate(text, s.get("tts_voice", "hi-IN-MadhurNeural"),
                                        rate=s.get("tts_rate", "+0%"))
            await comm.save(path)

        asyncio.run(go())
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise VoiceError("Edge TTS ne audio nahi diya (internet check karo)")
        return path

    def _play(self, path: str) -> None:
        mci = _MCI()
        alias = f"jack{uuid.uuid4().hex[:6]}"
        try:
            mci.cmd(f'open "{path}" type mpegvideo alias {alias}')
        except VoiceError:
            self._play_powershell(path)        # fallback: Windows' own media player
            return
        try:
            mci.cmd(f"play {alias}")
            while not self._stop.is_set():
                if mci.cmd(f"status {alias} mode") != "playing":
                    break
                time.sleep(0.05)
        finally:
            try:
                mci.cmd(f"stop {alias}")
            except VoiceError:
                pass
            mci.cmd(f"close {alias}")

    def _play_powershell(self, path: str) -> None:
        import subprocess
        script = ("Add-Type -AssemblyName PresentationCore; $p = New-Object System.Windows.Media.MediaPlayer; "
                  f"$p.Open([Uri]'{path}'); Start-Sleep -Milliseconds 300; $p.Play(); "
                  "$n = 0; while (-not $p.NaturalDuration.HasTimeSpan) { Start-Sleep -Milliseconds 100; "
                  "$n++; if ($n -gt 50) { exit 1 } }; "
                  "$left = $p.NaturalDuration.TimeSpan.TotalMilliseconds - $p.Position.TotalMilliseconds; "
                  "Start-Sleep -Milliseconds ([int]$left + 200)")
        proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        t0 = time.time()
        while proc.poll() is None:
            if self._stop.is_set() or time.time() - t0 > 90:
                proc.kill()
                break
            time.sleep(0.05)
        if proc.returncode not in (0, None) and not self._stop.is_set():
            raise VoiceError("Audio play nahi ho paya — speaker/headphone check karo")


# ── input: microphone ─────────────────────────────────────────────────────

def mic_available() -> str:
    """'' if a mic is usable, else a Hinglish reason."""
    try:
        import sounddevice as sd
    except ImportError:
        return "sounddevice install nahi hai (pip install sounddevice numpy)"
    try:
        dev = sd.query_devices(kind="input")
        if not dev or dev.get("max_input_channels", 0) < 1:
            return "Koi mic nahi mila"
    except Exception:
        return "Koi mic nahi mila — mic laga ke Windows sound settings check karo"
    return ""


def record_phrase(stop_event: Optional[threading.Event] = None, start_timeout: float = 7.0,
                  max_seconds: float = 15.0, silence_seconds: float = 1.2,
                  on_level: Callable[[float], None] = None) -> Optional[bytes]:
    """Record one spoken phrase and return it as WAV bytes (None = nothing said).

    Waits up to `start_timeout` s for speech, then records until
    `silence_seconds` of quiet or `max_seconds`.
    """
    reason = mic_available()
    if reason:
        raise VoiceError(reason)
    import numpy as np
    import sounddevice as sd

    frames, started, quiet_blocks, speech_blocks = [], False, 0, 0
    pre_roll = []                                     # keep 0.3 s before speech starts
    noise, threshold = None, 500.0
    t0 = time.time()
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK) as stream:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                block, _ = stream.read(BLOCK)
                block = block.reshape(-1)
                rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))
                if on_level:
                    on_level(min(1.0, rms / 4000.0))
                if noise is None:
                    noise = rms
                if not started:
                    noise = 0.9 * noise + 0.1 * rms          # track room noise
                    threshold = max(450.0, noise * 3.0)
                    pre_roll = (pre_roll + [block])[-3:]
                    if rms > threshold:
                        started = True
                        frames.extend(pre_roll)
                    elif time.time() - t0 > start_timeout:
                        return None
                    continue
                frames.append(block)
                if rms > threshold * 0.6:
                    quiet_blocks, speech_blocks = 0, speech_blocks + 1
                else:
                    quiet_blocks += 1
                if quiet_blocks * BLOCK / SAMPLE_RATE >= silence_seconds:
                    break
                if len(frames) * BLOCK / SAMPLE_RATE >= max_seconds:
                    break
    except VoiceError:
        raise
    except Exception as e:
        raise VoiceError(f"Mic se record nahi ho paya: {e}")

    if not started or speech_blocks < 3:              # < 0.3 s of real speech = noise click
        return None
    audio = np.concatenate(frames).astype("int16")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return buf.getvalue()


# Hinglish-style (kya, raha, nahi — not kyaa/rahaa/naheen)
_DEV_CONS = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
                     "k kh g gh n ch chh j jh n t th d dh n t th d dh n p ph b bh m y r l v sh sh s h".split()))
_DEV_CONS.update({"क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d",
                  "ढ़": "rh", "फ़": "f", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z",
                  "ड़": "d", "ढ़": "rh", "फ़": "f"})
_DEV_VOW = dict(zip("अआइईउऊऋएऐओऔ", "a a i i u u ri e ai o au".split()))
_DEV_MATRA = dict(zip("ािीुूृेैोौ", "a i i u u ri e ai o au".split()))
_DEV_RE = re.compile(r"[ऀ-ॿ]+")


def _dev_word(word: str) -> str:
    out, i = [], 0
    while i < len(word):
        ch = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if nxt == "़" and ch + nxt in _DEV_CONS:          # nukta letters
            ch, i = ch + nxt, i + 1
            nxt = word[i + 1] if i + 1 < len(word) else ""
        if ch in _DEV_CONS:
            out.append(_DEV_CONS[ch])
            if nxt in _DEV_MATRA:
                out.append(_DEV_MATRA[nxt]); i += 1
            elif nxt == "्":                              # virama: no vowel
                i += 1
            elif i + 1 < len(word) and nxt not in "ंँः":
                out.append("a")
        elif ch in _DEV_VOW:
            out.append(_DEV_VOW[ch])
        elif ch in "ंँ":
            out.append("n")
        elif ch == "।":
            out.append(".")
        i += 1
    return "".join(out)          # final consonant gets no inherent 'a' (kaam, not kaama)


def to_roman(text: str) -> str:
    """Whisper sometimes writes Hindi words in Devanagari — convert them to Roman Hinglish."""
    return _DEV_RE.sub(lambda m: _dev_word(m.group(0)), text or "")


def transcribe(wav: bytes, prompt: str = STT_PROMPT) -> str:
    """Speech -> text with Groq Whisper. Tries each model in settings['stt_models']."""
    from app.hardware.ai_analyzer import load_api_key
    key = load_api_key()
    if not key:
        raise VoiceError("Groq key nahi mili — voice ke liye bhi wahi key chahiye")
    models = load_settings().get("stt_models") or ["whisper-large-v3-turbo"]
    last = "unknown"
    for model in models:
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in (("model", model), ("prompt", prompt), ("response_format", "json"),
                            ("language", "en"), ("temperature", "0")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                         .encode("utf-8"))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="jack.wav"\r\n'
                     f"Content-Type: audio/wav\r\n\r\n".encode("utf-8") + wav + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        req = urllib.request.Request(GROQ_STT_URL, data=b"".join(parts), method="POST", headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "MooxyJack/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return to_roman((json.loads(r.read().decode("utf-8")).get("text") or "").strip())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise VoiceError("Groq key galat hai")
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503):
                continue                               # rate-limited / busy -> next model
            raise VoiceError(f"Whisper error {last}")
        except urllib.error.URLError as e:
            raise VoiceError(f"Internet nahi hai? ({e.reason})")
    raise VoiceError(f"Whisper busy hai ({last}) — thodi der baad try karo")


def strip_wake_word(text: str) -> Optional[str]:
    """Return the command after the wake word ('' if only the wake word), None if no wake word."""
    m = WAKE_RE.search(text or "")
    if not m:
        return None
    return text[m.end():].strip(" ,.!?-—।")


# ── wake word ─────────────────────────────────────────────────────────────

class WakeWordLoop:
    """Listens in the background; calls on_wake(command_text) when 'Hey Jack' is heard.

    `is_paused()` is checked before each phrase so Jack doesn't listen while it
    is speaking, busy, or while the mic button is recording.
    """

    def __init__(self, on_wake: Callable[[str], None], is_paused: Callable[[], bool],
                 on_error: Callable[[str], None] = None):
        self.on_wake = on_wake
        self.is_paused = is_paused
        self.on_error = on_error or (lambda m: None)
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        errors = 0
        while not self._stop.is_set():
            if self.is_paused():
                time.sleep(0.3)
                continue
            try:
                wav = record_phrase(stop_event=self._stop, start_timeout=30, max_seconds=6,
                                    silence_seconds=0.8)
                if not wav or self._stop.is_set() or self.is_paused():
                    continue
                text = transcribe(wav, prompt="Hey Jack. " + STT_PROMPT)
                errors = 0
                cmd = strip_wake_word(text)
                if cmd is not None:
                    self.on_wake(cmd)
            except VoiceError as e:
                errors += 1
                self.on_error(str(e))
                if errors >= 3 or "mic" in str(e).lower() or "install" in str(e).lower():
                    self.on_error(f"Wake word band kar diya: {e}")
                    return
                time.sleep(3)
            except Exception as e:
                self.on_error(f"Wake word error: {e}")
                time.sleep(3)
