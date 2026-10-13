from jarvis.agent import Agent, parse_action
from jarvis.cli import main
from jarvis.llm import MockLLM, ScriptedLLM
from jarvis.memory import ConversationMemory


def agent(llm, registry, store, max_steps=5):
    return Agent(llm, registry, ConversationMemory(store, "t", window=6), max_steps)


def test_parse_action_tolerates_fences_and_prose():
    assert parse_action('```json\n{"tool": "x", "arguments": {}}\n```')["tool"] == "x"
    assert parse_action("just text") == {"answer": "just text"}


def test_tool_call_then_answer(registry, store):
    llm = ScriptedLLM([{"tool": "calculator", "arguments": {"expression": "6*7"}}, {"answer": "It's 42."}])
    res = agent(llm, registry, store).ask("what is 6*7?")
    assert res.answer == "It's 42." and res.tool_calls[0]["result"] == "42"
    assert "TOOL_RESULT calculator (ok):\n42" in llm.calls[1][-1]["content"]
    assert "inputSchema" in llm.calls[0][0]["content"]  # tool specs reach the model


def test_multi_step_tools(registry, store):
    llm = ScriptedLLM([{"tool": "add_note", "arguments": {"text": "a"}},
                       {"tool": "list_notes", "arguments": {}}, {"answer": "done"}])
    assert len(agent(llm, registry, store).ask("note a and list").tool_calls) == 2


def test_tool_error_fed_back(registry, store):
    llm = ScriptedLLM([{"tool": "does_not_exist", "arguments": {}}, {"answer": "sorry"}])
    res = agent(llm, registry, store).ask("x")
    assert res.tool_calls[0]["isError"] and "(error)" in llm.calls[1][-1]["content"]


def test_max_steps_guard(registry, store):
    llm = ScriptedLLM([{"tool": "system_info", "arguments": {}}] * 10)
    res = agent(llm, registry, store, max_steps=2).ask("loop")
    assert len(res.tool_calls) == 2 and "limit" in res.answer


def test_memory_carries_across_turns(registry, store):
    llm = ScriptedLLM([{"answer": "Nice to meet you, Rehan."}, {"answer": "You're Rehan."}])
    a = agent(llm, registry, store)
    a.ask("My name is Rehan")
    a.ask("What's my name?")
    contents = [m["content"] for m in llm.calls[1]]
    assert "My name is Rehan" in contents and "Nice to meet you, Rehan." in contents


def test_memory_window(store):
    m = ConversationMemory(store, "w", window=3)
    for i in range(5):
        m.add("user", str(i))
    assert [r["content"] for r in m.recent()] == ["2", "3", "4"]
    m.clear()
    assert m.recent() == []


def test_mock_llm_end_to_end(registry, store):
    a = agent(MockLLM(), registry, store)
    assert "1024" in a.ask("what is 2^10").answer
    assert "Saved note" in a.ask("note buy milk").answer
    assert "27.5" in a.ask("weather in Pune").answer


def test_cli_session(registry, store):
    out, inputs = [], iter(["what is 3*3", "/tools", "/clear", "exit"])
    a = agent(MockLLM(), registry, store)
    assert main(["--verbose"], agent=a, input_fn=lambda _: next(inputs), print_fn=out.append) == 0
    assert any("9" in o and o.startswith("Jarvis:") for o in out)
    assert any("calculator" in o and "weather" in o for o in out) and "Memory cleared." in out


def test_voice_is_optional(monkeypatch):
    import builtins

    import pytest

    from jarvis.voice import Voice, VoiceUnavailable
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n))
                        if n in {"pyttsx3", "speech_recognition"} else real(n, *a, **k))
    with pytest.raises(VoiceUnavailable):
        Voice()
