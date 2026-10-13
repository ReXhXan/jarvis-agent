import json

import pytest

from jarvis.tools.builtin import _parse_due, safe_eval


def call(reg, name, **args):
    r = reg.call_tool(name, args)
    return r["isError"], r["content"][0]["text"]


@pytest.mark.parametrize("expr,val", [("2*(3+4)", 14), ("2^10", 1024), ("sqrt(16)+pi-pi", 4), ("-3 % 5", 2)])
def test_calculator(expr, val):
    assert safe_eval(expr) == val


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "(1).__class__", "9**99999", "a+1"])
def test_calculator_rejects_unsafe(expr):
    with pytest.raises((ValueError, SyntaxError)):
        safe_eval(expr)


def test_calculator_tool_formats_ints(registry):
    assert call(registry, "calculator", expression="10/2") == (False, "5")


def test_weather_with_mocked_http(registry):
    err, text = call(registry, "weather", city="Bengaluru")
    data = json.loads(text)
    assert not err and data["temperature_c"] == 27.5 and data["conditions"] == "overcast"
    assert call(registry, "weather", city="Atlantis")[0] is True


def test_notes_crud(registry):
    assert call(registry, "add_note", text="buy GPU")[1] == "Saved note #1"
    call(registry, "add_note", text="read MCP spec")
    notes = json.loads(call(registry, "list_notes", query="MCP")[1])
    assert [n["text"] for n in notes] == ["read MCP spec"]
    call(registry, "delete_note", note_id=1)
    assert len(json.loads(call(registry, "list_notes")[1])) == 1


def test_reminders(registry):
    call(registry, "add_reminder", text="past", when="2000-01-01T00:00:00")
    call(registry, "add_reminder", text="soon", when="in 10 minutes")
    rs = json.loads(call(registry, "list_reminders")[1])
    assert [r["text"] for r in rs] == ["past", "soon"] and rs[0]["overdue"] and not rs[1]["overdue"]
    call(registry, "complete_reminder", reminder_id=1)
    assert [r["text"] for r in json.loads(call(registry, "list_reminders")[1])] == ["soon"]


def test_parse_due_relative_and_bad():
    assert _parse_due("2 hours") > _parse_due("in 30 min")
    with pytest.raises(ValueError):
        _parse_due("someday")


def test_file_search_respects_roots_and_hidden(registry):
    hits = json.loads(call(registry, "file_search", query="report")[1])
    assert len(hits) == 1 and hits[0].endswith("report_q3.md")
    assert json.loads(call(registry, "file_search", query="bank", content=True)[1])[0].endswith("todo.txt")


def test_system_info(registry):
    info = json.loads(call(registry, "system_info")[1])
    assert {"os", "python", "cpus", "disk_free_gb"} <= info.keys()


def test_web_search_stub(registry):
    assert json.loads(call(registry, "web_search", query="x")[1])["results"] == []
