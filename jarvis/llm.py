"""Pluggable chat LLMs. All take a list of {role, content} messages and return text.

Tool calling uses a provider-agnostic JSON protocol (see agent.py), so even small local models
on Ollama can use tools.
"""
import json
import re
from collections import deque

import httpx


class LLM:
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError


class OpenAICompatibleLLM(LLM):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        from openai import OpenAI
        self.client, self.model = OpenAI(api_key=api_key, base_url=base_url), model

    def chat(self, messages):
        r = self.client.chat.completions.create(model=self.model, temperature=0.2, messages=messages,
                                                response_format={"type": "json_object"})
        return r.choices[0].message.content or ""


class OllamaLLM(LLM):
    def __init__(self, model: str, base_url: str):
        self.model, self.url = model, base_url.rstrip("/") + "/api/chat"

    def chat(self, messages):
        r = httpx.post(self.url, timeout=120, json={"model": self.model, "stream": False,
                                                    "format": "json", "messages": messages})
        r.raise_for_status()
        return r.json()["message"]["content"]


class ScriptedLLM(LLM):
    """Replays fixed replies; records what it was sent. For tests."""

    def __init__(self, replies: list[str | dict]):
        self.replies = deque(json.dumps(r) if isinstance(r, dict) else r for r in replies)
        self.calls: list[list[dict]] = []

    def chat(self, messages):
        self.calls.append([dict(m) for m in messages])
        return self.replies.popleft()


class MockLLM(LLM):
    """Offline keyword router so the CLI is usable with no API key or model."""

    RULES = [
        (re.compile(r"weather (?:in|for|at) ([a-z .'-]+)", re.I), lambda m: ("weather", {"city": m.group(1).strip()})),
        (re.compile(r"remind me (?:to )?(.+?) in (.+)$", re.I),
         lambda m: ("add_reminder", {"text": m.group(1), "when": "in " + m.group(2)})),
        (re.compile(r"(?:my|list|show) notes", re.I), lambda m: ("list_notes", {})),
        (re.compile(r"(?:my|list|show) reminders", re.I), lambda m: ("list_reminders", {})),
        (re.compile(r"(?:note|remember)(?: that)?:?\s+(.+)$", re.I), lambda m: ("add_note", {"text": m.group(1)})),
        (re.compile(r"find (?:files? )?(?:named |called )?(.+)$", re.I), lambda m: ("file_search", {"query": m.group(1)})),
        (re.compile(r"system info|my (?:computer|system)", re.I), lambda m: ("system_info", {})),
        (re.compile(r"search (?:the web )?for (.+)$", re.I), lambda m: ("web_search", {"query": m.group(1)})),
        (re.compile(r"(?:calculate|compute|what is|what's)\s+([-\d\s.+*/()^%a-z]+?)\??$", re.I),
         lambda m: ("calculator", {"expression": m.group(1).strip()})),
    ]

    def chat(self, messages):
        last = messages[-1]
        if last["role"] == "user" and last["content"].startswith("TOOL_RESULT"):
            return json.dumps({"answer": "Here's what I found: " + last["content"].split("\n", 1)[-1][:500]})
        text = last["content"].strip()
        for rx, make in self.RULES:
            if m := rx.search(text):
                name, args = make(m)
                return json.dumps({"tool": name, "arguments": args})
        if re.search(r"\b(hi|hello|hey)\b", text, re.I):
            return json.dumps({"answer": "Hello! I'm Jarvis. Ask me to calculate, check weather, take notes or set reminders."})
        return json.dumps({"answer": "I'm running in offline mock mode. Set LLM_PROVIDER for open-ended chat."})


def get_llm(settings) -> LLM:
    p = settings.llm_provider.lower()
    if p == "openai":
        return OpenAICompatibleLLM(settings.llm_model, settings.openai_api_key)
    if p == "groq":
        return OpenAICompatibleLLM(settings.llm_model, settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    if p == "ollama":
        return OllamaLLM(settings.llm_model, settings.ollama_base_url)
    return MockLLM()
