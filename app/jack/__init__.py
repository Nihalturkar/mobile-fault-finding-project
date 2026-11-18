"""
Jack — Mooxy AI's voice assistant for mobile repair technicians.

Sections:
  1. Brain           (brain.py, llm.py)   — tool-calling agent with memory + fallback
  2. Knowledge tools (knowledge.py)       — searches the local repair databases
  3. Action tools    (planned)            — runs hardware tests / log analysis
  4. Voice input     (planned)
  5. Voice output    (planned)
  6. Jack UI page    (planned)
  7. Proactive mode  (planned)
"""

from app.jack.brain import JackBrain, JackReply

__all__ = ["JackBrain", "JackReply"]
