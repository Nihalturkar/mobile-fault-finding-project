"""
OpenAI-compatible chat client with tool calling.

Works with:
  * Groq   — https://api.groq.com/openai/v1  (key from config/groq_api_key.txt)
  * Ollama — http://localhost:11434/v1       (offline, needs a tool-capable model e.g. llama3.1)

Uses urllib only (same as the existing ai_analyzer) so no new dependency.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.hardware.ai_analyzer import load_api_key


MAX_RATE_LIMIT_WAIT = 8  # seconds — wait this long at most before giving up on a model


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = False, rate_limited: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.rate_limited = rate_limited


class ChatClient:
    def __init__(self, provider: str, base_url: str, model: str, api_key: str = "", timeout: int = 90):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    # ── factories ──
    @classmethod
    def groq(cls, model: str) -> Optional["ChatClient"]:
        key = load_api_key()
        if not key.startswith("gsk_"):
            return None
        return cls("groq", "https://api.groq.com/openai/v1", model, key)

    @classmethod
    def ollama(cls, model: str) -> Optional["ChatClient"]:
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
                pass
        except Exception:
            return None
        return cls("ollama", "http://localhost:11434/v1", model, timeout=180)

    # ── request ──
    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None,
             temperature: float = 0.3, max_tokens: int = 1500) -> Dict[str, Any]:
        """Return the assistant message dict: {'content': str|None, 'tool_calls': [...]}.

        On a short rate limit (Retry-After <= MAX_RATE_LIMIT_WAIT) waits once and retries."""
        try:
            return self._chat_once(messages, tools, temperature, max_tokens)
        except LLMError as e:
            wait = getattr(e, "retry_after", None)
            if e.rate_limited and wait is not None and wait <= MAX_RATE_LIMIT_WAIT:
                time.sleep(wait + 0.5)
                return self._chat_once(messages, tools, temperature, max_tokens)
            raise

    def _chat_once(self, messages, tools, temperature, max_tokens) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "MooxyAI-Jack/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(f"{self.base_url}/chat/completions",
                                     data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
            except Exception:
                pass
            if e.code == 401:
                raise LLMError("Groq API key galat hai. config/groq_api_key.txt check karo.")
            if e.code == 429 or (e.code == 413 and "rate" in detail.lower()):
                err = LLMError(f"{self.model} ki rate limit hit ho gayi.", rate_limited=True)
                try:
                    err.retry_after = float(e.headers.get("retry-after", ""))
                except (TypeError, ValueError):
                    err.retry_after = None
                raise err
            if e.code == 400 and "tool" in detail.lower():
                # Model produced a malformed tool call — caller may retry
                raise LLMError(f"Tool call failed: {detail}", retryable=True)
            raise LLMError(f"{self.provider} API error {e.code}: {detail or e.reason}")
        except urllib.error.URLError as e:
            raise LLMError(f"{self.provider} se connect nahi ho paya: {e.reason}")
        except TimeoutError:
            raise LLMError(f"{self.provider} ne time pe jawab nahi diya.")

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("AI ne khaali jawab diya.", retryable=True)
        msg = choices[0].get("message", {}) or {}
        return {"content": msg.get("content"), "tool_calls": msg.get("tool_calls") or [],
                "usage": data.get("usage", {})}
