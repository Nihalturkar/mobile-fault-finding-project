"""
Section 7 — Proactive Jack.

Jack bina pooche khud react karta hai:
  • Phone connect / disconnect hote hi ek toast (+ voice) aata hai.
  • Scan khatam hote hi faults ka chhota summary aata hai.

Everything is driven by events the app ALREADY produces (the 5-second
connection check, and scan completions) — no extra hardware polling. The whole
thing is gated by a single toggle, persisted as `proactive_enabled` in
jack_settings.json, and it de-dupes so it never nags.
"""

import threading
import time

import customtkinter as ctk

from app.jack.config import load_settings, save_settings


class ProactiveManager:
    """Owns the toast widget + decides when Jack should speak up on its own."""

    def __init__(self, app):
        self.app = app
        s = load_settings()
        self.enabled = bool(s.get("proactive_enabled", True))
        self._last_conn = None          # (uart_ok, adb_ok) — None = first check
        self._toast = None
        self._toast_job = None
        self._seen = {}                 # dedupe key -> timestamp
        self._speaker = None

    # ── settings ──
    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        try:
            s = load_settings()
            s["proactive_enabled"] = self.enabled
            save_settings(s)
        except Exception:
            pass
        if not on:
            self._dismiss()

    # ── event: connection changed (called from main_window every 5s) ──
    def on_connection(self, uart_ok: bool, adb_ok: bool) -> None:
        prev, self._last_conn = self._last_conn, (uart_ok, adb_ok)
        if not self.enabled or prev is None:    # first check: just remember, don't announce
            return
        if prev == (uart_ok, adb_ok):
            return
        newly_adb = adb_ok and not prev[1]
        newly_uart = uart_ok and not prev[0]
        if newly_adb or newly_uart:
            threading.Thread(target=self._announce_connect, args=(newly_adb,), daemon=True).start()
        elif not uart_ok and not adb_ok and (prev[0] or prev[1]):
            self._ui(lambda: self._toast_show("🔌  Device disconnect ho gaya.",
                                              speak="Device disconnect ho gaya", kind="dim"))

    def _announce_connect(self, is_adb: bool) -> None:
        summary = ""
        try:
            from app.jack.actions import check_connected_devices
            summary = check_connected_devices().get("summary", "") or ""
        except Exception:
            summary = ""
        if is_adb:
            msg = f"📱  {summary}" if summary else "📱  ADB phone connect hua."
            action = ("Jack me scan karo", self._open_jack)
            speak = summary or "Phone connect hua. Scan karoon?"
        else:
            msg = "🔌  UART adapter laga — phone boot karke HW Detect chalao."
            action = ("Jack kholo", self._open_jack)
            speak = "UART adapter laga. Phone boot karo, main sun raha hoon."
        if self._dup(msg):
            return
        self._ui(lambda: self._toast_show(msg, action=action, speak=speak, kind="info"))

    # ── event: a scan finished (called from scan pages) ──
    def on_scan_done(self, scan_type: str, device_name: str = "", faults_count: int = 0) -> None:
        if not self.enabled:
            return
        dev = device_name or "Device"
        if faults_count > 0:
            msg = f"⚠️  {dev}: {faults_count} fault mile ({scan_type}). Jack se samjho?"
            speak = f"{dev} me {faults_count} fault mile. Main samjhaoon?"
            kind = "warn"
        else:
            msg = f"✅  {dev}: koi fault nahi ({scan_type}). Phone theek lagta hai."
            speak = f"{dev} me koi fault nahi mila."
            kind = "ok"
        if self._dup(msg):
            return
        self._ui(lambda: self._toast_show(msg, action=("Jack me kholo", self._open_jack_lastscan),
                                          speak=speak, kind=kind))

    # ── helpers ──
    def _dup(self, key: str, window: float = 25.0) -> bool:
        now = time.time()
        self._seen = {k: t for k, t in self._seen.items() if now - t < 120}
        if key in self._seen and now - self._seen[key] < window:
            return True
        self._seen[key] = now
        return False

    def _ui(self, fn):
        try:
            self.app.after(0, fn)
        except Exception:
            pass

    def _open_jack(self):
        self._dismiss()
        try:
            self.app.show_jack()
        except Exception:
            pass

    def _open_jack_lastscan(self):
        self._open_jack()

        def go():
            try:
                st = getattr(self.app, "jack_state", None)
                ask = st["ui"].get("ask") if st and st.get("ui") else None
                if ask and not st.get("busy"):
                    ask("Last scan ka result detail me samjhao")
            except Exception:
                pass
        self.app.after(900, go)

    def _speak(self, text: str):
        if not text:
            return
        try:
            st = getattr(self.app, "jack_state", None)
            if st and not st.get("voice_on", False):
                return                      # Jack voice is OFF → stay quiet
            spk = (st or {}).get("speaker") if st else None
            if spk is None:
                if not load_settings().get("voice_reply", True):
                    return
                from app.jack.voice import Speaker
                self._speaker = self._speaker or Speaker()
                spk = self._speaker
            spk.speak(text)
        except Exception:
            pass

    # ── toast widget ──
    def _toast_show(self, text, action=None, speak="", kind="info"):
        try:
            if not self.app.winfo_exists():
                return
        except Exception:
            return
        self._dismiss()
        C = self.app.colors
        accent = {"info": C["info"], "warn": C["warning"], "ok": C["success"],
                  "dim": C["text_dim"]}.get(kind, C["info"])
        f = ctk.CTkFrame(self.app, corner_radius=14, fg_color=C["bg_medium"],
                         border_width=2, border_color=accent)
        f.place(relx=1.0, x=-24, y=72, anchor="ne")
        bar = ctk.CTkFrame(f, width=4, fg_color=accent, corner_radius=2)
        bar.pack(side="left", fill="y", padx=(8, 0), pady=10)
        body = ctk.CTkFrame(f, fg_color="transparent")
        body.pack(side="left", padx=(10, 12), pady=10)
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="💠 Jack", font=("Segoe UI", 12, "bold"),
                     text_color=accent).pack(side="left")
        ctk.CTkButton(head, text="✕", width=22, height=22, font=("Segoe UI", 11),
                      fg_color="transparent", hover_color=C["bg_light"],
                      text_color=C["text_dim"], command=self._dismiss).pack(side="right")
        ctk.CTkLabel(body, text=text, font=("Segoe UI", 13), text_color=C["text"],
                     justify="left", wraplength=300).pack(anchor="w", pady=(2, 0))
        if action:
            label, cmd = action
            ctk.CTkButton(body, text=label, height=28, font=("Segoe UI", 12, "bold"),
                          fg_color=accent, hover_color=C["accent_hover"], text_color="#0b0d1a",
                          command=cmd).pack(anchor="w", pady=(8, 0))
        self._toast = f
        self._speak(speak)
        try:
            self._toast_job = self.app.after(8000, self._dismiss)
        except Exception:
            pass

    def _dismiss(self):
        if self._toast_job:
            try:
                self.app.after_cancel(self._toast_job)
            except Exception:
                pass
            self._toast_job = None
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
            self._toast = None
