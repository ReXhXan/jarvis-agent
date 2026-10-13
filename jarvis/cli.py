"""Interactive CLI.

    python -m jarvis                 # chat in the terminal
    python -m jarvis --voice         # talk to it (needs voice extras)
    python -m jarvis -q "what is 2^10"
    python -m jarvis --tools         # print the MCP tool list
"""
import argparse
import json
import logging
from pathlib import Path

from .agent import Agent
from .config import Settings, get_settings
from .llm import LLM, get_llm
from .memory import ConversationMemory
from .storage import Store
from .tools.builtin import build_registry


def build_agent(s: Settings, llm: LLM | None = None, store: Store | None = None, session: str = "default") -> Agent:
    store = store or Store(str(Path(s.data_dir) / "jarvis.db"))
    reg = build_registry(store, s.roots, allow_network=s.allow_network)
    return Agent(llm or get_llm(s), reg, ConversationMemory(store, session, s.memory_window), s.max_tool_steps)


def main(argv=None, agent: Agent | None = None, input_fn=input, print_fn=print) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser(prog="jarvis")
    ap.add_argument("-q", "--query", help="ask one question and exit")
    ap.add_argument("--session", default="default")
    ap.add_argument("--voice", action="store_true", default=s.voice_enabled)
    ap.add_argument("--tools", action="store_true", help="list tools and exit")
    ap.add_argument("--verbose", action="store_true", help="show tool calls")
    a = ap.parse_args(argv)
    logging.basicConfig(level=s.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    agent = agent or build_agent(s, session=a.session)

    if a.tools:
        print_fn(json.dumps(agent.registry.list_tools(), indent=2))
        return 0

    def respond(text: str) -> str:
        res = agent.ask(text)
        if a.verbose:
            for c in res.tool_calls:
                print_fn(f"  ↳ {c['tool']}({json.dumps(c['arguments'])}) -> {c['result'][:200]}")
        print_fn(f"Jarvis: {res.answer}")
        return res.answer

    if a.query:
        respond(a.query)
        return 0

    voice = None
    if a.voice:
        from .voice import Voice, VoiceUnavailable
        try:
            voice = Voice()
        except VoiceUnavailable as e:
            print_fn(f"[voice disabled] {e}")

    print_fn("Jarvis ready. Type 'exit' to quit, '/clear' to reset memory, '/tools' to list tools.")
    while True:
        try:
            text = voice.listen() if voice else input_fn("You: ")
        except (EOFError, KeyboardInterrupt):
            break
        if text is None:
            continue
        text = text.strip()
        if not text:
            continue
        if text.lower() in {"exit", "quit", "bye"}:
            break
        if text == "/clear":
            agent.memory.clear()
            print_fn("Memory cleared.")
            continue
        if text == "/tools":
            print_fn(", ".join(t["name"] for t in agent.registry.list_tools()))
            continue
        answer = respond(text)
        if voice:
            voice.speak(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
