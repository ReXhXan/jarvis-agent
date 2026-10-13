"""ReAct-style agent loop: the model either calls a tool or answers, for at most `max_steps` tool calls."""
import json
import logging
import re
from dataclasses import dataclass, field

from .llm import LLM
from .memory import ConversationMemory
from .tools.registry import ToolRegistry

log = logging.getLogger(__name__)

SYSTEM = """You are Jarvis, a concise and helpful personal assistant.
You can use these tools (MCP format):
{tools}

Reply with exactly ONE JSON object and nothing else:
  {{"tool": "<name>", "arguments": {{...}}}}   to call a tool, or
  {{"answer": "<text for the user>"}}          when you can answer.
After a tool call you will receive TOOL_RESULT. Never make up tool results. If a tool fails, explain or try another way."""


@dataclass
class TurnResult:
    answer: str
    tool_calls: list[dict] = field(default_factory=list)


def parse_action(text: str) -> dict:
    """Parse the model's JSON action, tolerating code fences or surrounding prose."""
    text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {"answer": text}
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"answer": text}
    return obj if isinstance(obj, dict) else {"answer": str(obj)}


class Agent:
    def __init__(self, llm: LLM, registry: ToolRegistry, memory: ConversationMemory, max_steps: int = 5):
        self.llm, self.registry, self.memory, self.max_steps = llm, registry, memory, max_steps

    def _system(self) -> dict:
        return {"role": "system", "content": SYSTEM.format(tools=json.dumps(self.registry.list_tools(), indent=1))}

    def ask(self, user_text: str) -> TurnResult:
        history = self.memory.recent()
        scratch = [{"role": "user", "content": user_text}]
        calls: list[dict] = []
        answer = None
        for _ in range(self.max_steps + 1):
            action = parse_action(self.llm.chat([self._system(), *history, *scratch]))
            if "tool" not in action:
                answer = str(action.get("answer", "")).strip() or "(no answer)"
                break
            if len(calls) >= self.max_steps:
                answer = "I hit my tool-call limit for this request. Here's what I have so far."
                break
            name, args = action["tool"], action.get("arguments") or {}
            result = self.registry.call_tool(name, args if isinstance(args, dict) else {})
            text = result["content"][0]["text"]
            calls.append({"tool": name, "arguments": args, "isError": result["isError"], "result": text})
            log.info("tool %s(%s) -> %s", name, args, text[:120])
            scratch += [{"role": "assistant", "content": json.dumps(action)},
                        {"role": "user", "content": f"TOOL_RESULT {name} ({'error' if result['isError'] else 'ok'}):\n{text}"}]
        self.memory.add("user", user_text)
        self.memory.add("assistant", answer)
        return TurnResult(answer, calls)
