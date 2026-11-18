"""
Section 1 — Jack's brain.

Flow for every message:
    user text ─► LLM (Groq → Ollama) ─► tool calls? ─► run tools ─► LLM ─► … ─► reply
                         │ all backends fail
                         └─► local mode: answer straight from the databases (no AI)

Usage:
    brain = JackBrain()
    reply = brain.chat("Redmi 9 dead hai, 0.00A le raha hai",
                       on_event=lambda kind, data: print(kind, data))
    reply.speech  -> short line to speak (Section 5)
    reply.text    -> full answer for the chat window
"""

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.jack.actions import build_action_tools
from app.jack.config import load_settings
from app.jack.knowledge import KnowledgeBase
from app.jack.llm import ChatClient, LLMError
from app.jack.tools import ToolRegistry, build_knowledge_tools

MAX_TOOL_ROUNDS = 6

EventCallback = Callable[[str, Any], None]   # kinds: "status", "tool", "reply", "error"


SYSTEM_PROMPT = """You are {name}, the AI assistant built into "Mooxy AI Fault Detector", a Windows tool used by \
mobile phone repair technicians in India. Personality: like J.A.R.V.I.S. — calm, sharp, confident, a little witty, \
always respectful. Address the user as "Boss".

LANGUAGE: Reply in Hinglish — Hindi written in Roman script mixed with English technical terms \
(e.g. "Boss, PMIC ka VBAT pin pe 3.8V check karo"). Never use Devanagari script.

FORMAT:
- First line: 1-2 short sentences that will be SPOKEN aloud. Plain words only — no markdown, symbols, or lists.
- Then one blank line, then details: short bullets or numbered steps. Keep it under ~180 words unless Boss asks for more.

GROUNDING (very important):
- Before naming any IC part number, voltage, test point, I2C address or repair step, CALL THE TOOLS and use the shop's data.
- Phone model mentioned → search_phone first; then get_chipset_info for its chipset/PMIC/charger IC; \
then search_fault_patterns and search_community_fixes for the symptom. Use search_repair_history for past jobs.
- Call several tools in the SAME turn whenever possible (e.g. search_phone + search_fault_patterns together) — \
fewer round trips.
- If the tools return nothing, say "Boss, ye mere database mein nahi hai" and only then give general guidance, \
clearly marked "(general knowledge — verify karna)". Use that label ONLY for facts that did not come from a tool. \
Never invent part numbers or test-point locations.
- Generic fault patterns list ICs from several chip families. Only mention ICs that belong to THIS phone's \
chipset family (never suggest MediaTek ICs like MT6370 for a Qualcomm phone, or vice versa).
- Only quote a voltage/resistance/current value if a tool gave it or you are certain of it. When unsure, \
tell Boss to compare with a working board instead of guessing a number.
- Put the "(general knowledge — verify karna)" note next to the specific line it applies to, never as a blanket footer.

CONNECTED DEVICE: You CAN see the hardware. When Boss asks what is connected / "abhi wala phone" / current \
device, call check_connected_devices — never ask Boss for the model first. Important: a UART adapter (FTDI on a \
COM port) is only the cable adapter, not the phone; the phone behind it is identified from the latest UART scan \
(get_last_scan with scan_type "UART"), and read_uart_live tells whether the phone is sending data right now. \
If a phone is on ADB you get its exact brand/model/chipset/battery — use that model for the database tools.

SCANS: run_hw_detect (UART, Boss must boot the phone while it listens) and run_adb_detect take time — run them \
only when Boss asks for a scan/detect. Use defaults; don't ask for port or baud. The live output is already shown \
to Boss, so afterwards just explain the key findings and next checks.

TOOLS ARE YOURS: Never tell Boss to run a tool or mention tool/function names — if a check would help \
(e.g. listening on UART), run it yourself in the same turn and report the result. Never state something you \
did not check ("data nahi aa raha") unless a tool result says so. Never invent confidence percentages; only \
quote % values that come from tool results.

DIAGNOSIS STYLE: most likely cause first with confidence %, then exactly what to measure (where + expected value), \
then the next step. If key info is missing (model, current draw reading, water damage, what was already replaced), \
ask ONE short clarifying question.

SAFETY: Anything that writes to a phone (firmware flash, FRP, IMEI, bootloader unlock, partition erase) must never \
be done without Boss's explicit confirmation. For now you cannot run those actions — tell Boss which page of the app to use.

Shop database right now: {stats}."""


@dataclass
class JackReply:
    text: str
    speech: str
    provider: str = ""             # groq | ollama | local
    tools_used: List[str] = field(default_factory=list)
    error: str = ""                # why AI backends were skipped, if any
    seconds: float = 0.0


def _split_speech(text: str) -> str:
    """What Jack says out loud — the first sentence or two only.

    Short on purpose: Edge TTS synthesises over the network, so a shorter line
    means Jack starts (and finishes) speaking much sooner. The full answer still
    shows on screen.
    """
    first = re.split(r"\n\s*\n", text.strip(), maxsplit=1)[0]
    first = re.sub(r"[*_`#>|\[\]]", "", first)
    first = re.sub(r"^\s*[-•\d.]+\s*", "", first, flags=re.MULTILINE)
    first = " ".join(first.split())
    # keep the first 1–2 sentences, hard-cap ~200 chars
    m = re.match(r"(.+?[.!?])(\s|$)", first)
    spoken = m.group(1) if m and len(m.group(1)) >= 20 else first
    if len(spoken) > 200:
        spoken = spoken[:200].rsplit(" ", 1)[0] + "…"
    return spoken


class JackBrain:
    def __init__(self, extra_tools: Optional[ToolRegistry] = None):
        self.settings = load_settings()
        self.kb = KnowledgeBase()
        self.tools = build_knowledge_tools(self.kb)
        for t in build_action_tools().tools.values():   # Section 3: device awareness
            self.tools.add(t)
        if extra_tools:                      # more action tools / UI-provided tools plug in here
            for t in extra_tools.tools.values():
                self.tools.add(t)
        self.history: List[Dict[str, Any]] = []

    # ── public ──
    def reset(self) -> None:
        self.history.clear()

    def run_scan(self, tool_name: str, args: Optional[Dict[str, Any]] = None,
                 on_event: Optional[EventCallback] = None) -> JackReply:
        """Button-triggered scan: run it directly (streaming lines live), then let the AI explain the result."""
        emit = on_event or (lambda kind, data: None)
        tool = self.tools.get(tool_name)
        if tool is None:
            return JackReply(text="Boss, ye scan available nahi hai.", speech="Boss, ye scan available nahi hai.")
        result_json = self._exec_tool(tool_name, args or {}, emit)
        try:
            result = json.loads(result_json)
        except json.JSONDecodeError:
            result = {}

        if result.get("stopped"):
            text = "Theek hai Boss, scan rok diya."
        elif result.get("error"):
            text = f"Boss, scan nahi ho paya.\n\n{result['error']}"
        else:
            prompt = (f"Boss ne button se '{tool.label.split(' —')[0]}' scan chalaya. Scan ka result:\n{result_json}\n\n"
                      "Boss ko samjhao: phone/chipset kya hai, kya problem mili (sirf report mein jo hai), "
                      "aur aage exactly kya check karna hai. Scan dobara mat chalao.")
            return self.chat(prompt, on_event, remember_as=f"[{tool_name} scan chalaya]", allow_scans=False)

        reply = JackReply(text=text, speech=_split_speech(text), provider="local", tools_used=[tool_name])
        self._remember(f"[{tool_name} scan chalaya]", text)
        emit("reply", reply)
        return reply

    def chat(self, user_text: str, on_event: Optional[EventCallback] = None,
             remember_as: Optional[str] = None, allow_scans: bool = True) -> JackReply:
        emit = on_event or (lambda kind, data: None)
        self._allow_scans = allow_scans
        start = time.time()
        user_text = (user_text or "").strip()
        if not user_text:
            return JackReply(text="Boss, kuch bola nahi aapne.", speech="Boss, kuch bola nahi aapne.")

        errors = []
        reply = None
        for provider in self.settings.get("provider_order", ["groq", "ollama", "local"]):
            if provider == "local":
                reply = self._local_answer(user_text)
                reply.error = " | ".join(errors)
                break
            clients = self._clients(provider)
            if not clients:
                errors.append(f"{provider}: not configured")
                continue
            for client in clients:
                try:
                    emit("status", f"Soch raha hoon... ({client.model})")
                    reply = self._agent_loop(client, user_text, emit)
                    break
                except LLMError as e:
                    errors.append(f"{client.model}: {e}")
                    emit("error", str(e))
                    if not e.rate_limited:
                        break   # key/network problem — other models of this provider will fail too
            if reply is not None:
                break
        if reply is None:
            reply = JackReply(text="Boss, koi bhi AI backend available nahi hai.",
                              speech="Boss, koi bhi AI backend available nahi hai.", error=" | ".join(errors))

        self._remember(remember_as or user_text, reply.text)
        reply.seconds = round(time.time() - start, 1)
        emit("reply", reply)
        return reply

    # ── internals ──
    def _clients(self, provider: str) -> List[ChatClient]:
        """All clients to try for a provider, in order (one per model)."""
        if provider == "groq":
            models = self.settings.get("groq_models") or [self.settings.get("groq_model", "openai/gpt-oss-120b")]
            clients = [ChatClient.groq(m) for m in models]
        elif provider == "ollama":
            clients = [ChatClient.ollama(self.settings["ollama_model"])]
        else:
            clients = []
        return [c for c in clients if c is not None]

    def _system_message(self) -> Dict[str, str]:
        stats = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in self.kb.stats().items())
        return {"role": "system", "content": SYSTEM_PROMPT.format(name=self.settings["name"], stats=stats)}

    def _remember(self, user_text: str, answer: str) -> None:
        # Only the final Q/A is kept (not raw tool output) to save tokens on follow-ups.
        self.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]
        limit = int(self.settings.get("max_history_messages", 16))
        self.history = self.history[-limit:]

    def _exec_tool(self, name: str, args: Dict[str, Any], emit: EventCallback) -> str:
        """Run one tool. Streaming tools (scans) push live lines/progress to the UI and can be stopped."""
        tool = self.tools.get(name)
        emit("tool", {"name": name, "args": args, "label": tool.label if tool else name})
        if tool is not None and tool.risky:
            return json.dumps({"error": "Confirmation required from Boss before running this action."})
        if tool is None or not tool.streams:
            return self.tools.run(name, args)

        stop = threading.Event()
        emit("scan_start", {"name": name, "label": tool.label, "stop_event": stop})
        try:
            return self.tools.run(name, args, stream_kwargs={
                "_emit": lambda line: emit("line", line),
                "_progress": lambda pct, msg: emit("progress", (pct, msg)),
                "_stop": stop,
            })
        finally:
            emit("scan_end", {"name": name})

    def _humanize(self, text: str) -> str:
        """Safety net: small models sometimes leak tool names ("read_uart_live") into replies."""
        for name in self.tools.tools:
            text = re.sub(rf"\s*\(\s*`?{name}`?(\(\))?\s*\)", "", text)          # "(read_uart_live)"
            text = re.sub(rf"`?{name}`?(\(\))?(\s+command)?", "Jack", text)       # bare mention
        return text

    def _reply(self, text: str, client: ChatClient, tools_used: List[str]) -> JackReply:
        text = self._humanize(text)
        return JackReply(text=text, speech=_split_speech(text), provider=client.provider, tools_used=tools_used)

    def _agent_loop(self, client: ChatClient, user_text: str, emit: EventCallback) -> JackReply:
        messages = [self._system_message(), *self.history, {"role": "user", "content": user_text}]
        tools_used: List[str] = []
        schemas = [s for s in self.tools.schemas()
                   if getattr(self, "_allow_scans", True) or not self.tools.get(s["function"]["name"]).streams]
        retried = False

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                msg = client.chat(messages, tools=schemas)
            except LLMError as e:
                if e.retryable and not retried:
                    retried = True
                    continue
                raise

            calls = msg["tool_calls"]
            if not calls:
                text = (msg["content"] or "").strip() or "Boss, mujhe iska jawab nahi mila."
                return self._reply(text, client, tools_used)

            messages.append({"role": "assistant", "content": msg["content"] or "",
                             "tool_calls": [{"id": c.get("id"), "type": "function",
                                             "function": c.get("function", {})} for c in calls]})
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._exec_tool(name, args, emit)
                tools_used.append(name)
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": result})

        # Too many rounds — ask for a final answer without tools
        msg = client.chat(messages + [{"role": "user", "content": "Ab tools mat chalao, jo mila uspe final jawab do."}])
        text = (msg["content"] or "").strip() or "Boss, analysis poora nahi ho paya."
        return self._reply(text, client, tools_used)

    def _local_answer(self, user_text: str) -> JackReply:
        """No AI available — answer directly from the databases."""
        # Follow-ups like "VBAT 3.9V hai, ab kya?" carry no symptom, so include the previous question.
        prev = [m["content"] for m in self.history if m["role"] == "user"][-1:]
        query = " ".join(prev + [user_text])
        patterns = self.kb.search_fault_patterns(query, limit=1)
        fixes = self.kb.search_community_fixes(query, limit=2, min_score=3)
        lines: List[str] = []

        if patterns.get("found"):
            p = patterns["results"][0]
            lines.append(f"**Fault pattern: {p.get('symptom', p['pattern_id'])}**")
            for c in (p.get("possible_causes") or [])[:4]:
                lines.append(f"- {c.get('ic', '?')} ({c.get('confidence', '?')}%): {c.get('reason', '')}"
                             f" → Check: {c.get('check', '')}")
            steps = p.get("repair_steps") or []
            if steps:
                lines.append("\n**Repair steps:**")
                lines += [f"{i}. {s}" for i, s in enumerate(steps[:5], 1)]
        if fixes.get("found"):
            lines.append("\n**Community fixes:**")
            for f in fixes["results"]:
                lines.append(f"- {f.get('device_model', '')}: {f.get('root_cause', '')} → {f.get('fix_description', '')}")

        if not lines:
            speech = "Boss, AI abhi offline hai aur database mein iska match nahi mila. Thoda detail mein symptom batao."
            return JackReply(text=speech, speech=speech, provider="local")

        speech = "Boss, AI abhi offline hai, lekin database se ye mila."
        return JackReply(text=speech + "\n\n" + "\n".join(lines), speech=speech, provider="local",
                         tools_used=["search_fault_patterns", "search_community_fixes"])
