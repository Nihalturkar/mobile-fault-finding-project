"""
Fallback Chain Analyzer — Intelligent multi-backend AI analysis.

Tries each backend in order of capability:
  1. Groq (cloud LLM) — Best quality, needs internet + API key
  2. Ollama (local LLM) — Good quality, needs Ollama installed, works offline
  3. Local Classifier (rule engine) — Always works, pattern-based, no AI needed

The chain automatically falls through to the next backend if the current one
fails. Results are returned in a uniform format regardless of which backend
produced them, so the GUI doesn't need to know or care.
"""

from dataclasses import dataclass
from typing import Optional, Callable
from app.hardware.ai_analyzer import AILogAnalyzer, OllamaAnalyzer, AIAnalysisResult, load_api_key
from app.hardware.local_classifier import LocalClassifier


@dataclass
class BackendStatus:
    """Status of each analysis backend."""
    name: str = ""
    available: bool = False
    reason: str = ""
    icon: str = ""


class FallbackAnalyzer:
    """Multi-backend analyzer with automatic fallback.

    Usage:
        analyzer = FallbackAnalyzer()
        result = analyzer.analyze(log_text, mode="boot", callback=print)

        # Or force a specific backend:
        result = analyzer.analyze(log_text, backend="ollama")

        # Check what's available:
        statuses = analyzer.check_backends()
    """

    def __init__(self, groq_api_key: str = "", ollama_model: str = ""):
        self.groq = AILogAnalyzer(api_key=groq_api_key)
        self.ollama = OllamaAnalyzer(model=ollama_model)
        self.local = LocalClassifier()

    def check_backends(self) -> list:
        """Check availability of all backends. Returns list of BackendStatus."""
        statuses = []

        # Groq
        groq_configured = self.groq.is_configured()
        if groq_configured:
            statuses.append(BackendStatus(
                name="Groq Cloud AI",
                available=True,
                reason="API key configured (gpt-oss-120b)",
                icon="☁️",
            ))
        else:
            statuses.append(BackendStatus(
                name="Groq Cloud AI",
                available=False,
                reason="No API key — add key in config/groq_api_key.txt",
                icon="☁️",
            ))

        # Ollama
        ollama_available = self.ollama.is_available()
        if ollama_available:
            models = self.ollama.get_available_models()
            model_list = ", ".join(models[:5]) if models else "no models"
            statuses.append(BackendStatus(
                name="Ollama Local AI",
                available=True,
                reason=f"Running locally ({model_list})",
                icon="🏠",
            ))
        else:
            statuses.append(BackendStatus(
                name="Ollama Local AI",
                available=False,
                reason="Not running — install from ollama.com, run: ollama pull llama3",
                icon="🏠",
            ))

        # Local classifier (always available)
        statuses.append(BackendStatus(
            name="Local Rule Engine",
            available=True,
            reason="Always available — 200+ fault patterns, works offline",
            icon="⚙️",
        ))

        return statuses

    def get_best_backend(self) -> str:
        """Return the name of the best available backend."""
        if self.groq.is_configured():
            return "groq"
        if self.ollama.is_available():
            return "ollama"
        return "local"

    def analyze(self, log_text: str, mode: str = "boot",
                callback: Optional[Callable] = None,
                detected_context: str = "",
                backend: str = "auto") -> AIAnalysisResult:
        """Analyze log with automatic fallback through backends.

        Args:
            log_text: The log content to analyze.
            mode: Log type - 'boot', 'apple', 'android', 'dmesg', or 'auto'.
            callback: Optional progress callback function.
            detected_context: Pre-detected context from tool's own analysis.
            backend: Force a specific backend: 'groq', 'ollama', 'local', or 'auto'.

        Returns:
            AIAnalysisResult with parsed JSON output.
        """
        if not log_text or not log_text.strip():
            result = AIAnalysisResult(mode=mode)
            result.error = "No log content to analyze."
            return result

        # If specific backend requested, try only that one
        if backend != "auto":
            return self._run_backend(backend, log_text, mode, callback, detected_context)

        # Auto fallback chain: Groq → Ollama → Local
        backends = []

        if self.groq.is_configured():
            backends.append(("groq", "Groq Cloud AI (gpt-oss-120b)"))
        if self.ollama.is_available():
            backends.append(("ollama", f"Ollama Local ({self.ollama.model})"))
        backends.append(("local", "Local Rule Engine (offline)"))

        last_error = ""
        for i, (name, display_name) in enumerate(backends):
            if callback:
                if i == 0:
                    callback(f"Trying {display_name}...")
                else:
                    callback(f"Falling back to {display_name}...")

            result = self._run_backend(name, log_text, mode, callback, detected_context)

            if result.success:
                # Tag which backend was used
                if result.parsed:
                    result.parsed["_backend"] = name
                    result.parsed["_backend_display"] = display_name
                return result
            else:
                last_error = result.error
                if callback:
                    callback(f"{display_name} failed: {result.error[:80]}. Trying next...")

        # All backends failed — return last error
        result = AIAnalysisResult(mode=mode)
        result.error = f"All backends failed. Last error: {last_error}"
        return result

    def _run_backend(self, name: str, log_text: str, mode: str,
                     callback, detected_context: str) -> AIAnalysisResult:
        """Run a specific backend."""
        try:
            if name == "groq":
                return self.groq.analyze(log_text, mode, callback, detected_context)
            elif name == "ollama":
                return self.ollama.analyze(log_text, mode, callback, detected_context)
            elif name == "local":
                return self.local.analyze(log_text, mode, callback, detected_context)
            else:
                result = AIAnalysisResult(mode=mode)
                result.error = f"Unknown backend: {name}"
                return result
        except Exception as e:
            result = AIAnalysisResult(mode=mode)
            result.error = f"{name} error: {str(e)}"
            return result

    def analyze_with_status(self, log_text: str, mode: str = "boot",
                            callback: Optional[Callable] = None,
                            detected_context: str = "",
                            backend: str = "auto") -> tuple:
        """Like analyze(), but also returns which backend was used.

        Returns:
            (AIAnalysisResult, backend_name: str, backend_display: str)
        """
        result = self.analyze(log_text, mode, callback, detected_context, backend)

        if result.success and result.parsed:
            backend_name = result.parsed.get("_backend", "unknown")
            backend_display = result.parsed.get("_backend_display", "Unknown")
        elif backend != "auto":
            backend_name = backend
            backend_display = {"groq": "Groq Cloud AI", "ollama": "Ollama Local",
                              "local": "Local Rule Engine"}.get(backend, backend)
        else:
            backend_name = "none"
            backend_display = "All backends failed"

        return result, backend_name, backend_display
