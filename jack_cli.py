"""
Talk to Jack from the terminal (for testing Sections 1 & 2 before the GUI is ready).

    venv\\Scripts\\python jack_cli.py

Commands:  /reset  (clear memory)   /exit
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.jack import JackBrain


def on_event(kind, data):
    if kind == "status":
        print(f"  ⏳ {data}")
    elif kind == "tool":
        print(f"  🔧 {data['label']}  {data['args']}")
    elif kind == "error":
        print(f"  ⚠️  {data}")


def main():
    brain = JackBrain()
    stats = brain.kb.stats()
    print(f"💠 Jack online. Database: {stats}")
    print("   (/reset = memory clear, /exit = band karo)\n")
    while True:
        try:
            text = input("Boss > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/exit":
            break
        if text == "/reset":
            brain.reset()
            print("  🧹 Memory clear.\n")
            continue
        reply = brain.chat(text, on_event=on_event)
        print(f"\nJack [{reply.provider}, {reply.seconds}s] > {reply.text}\n")
        if reply.error:
            print(f"  (skipped backends: {reply.error})\n")


if __name__ == "__main__":
    main()
