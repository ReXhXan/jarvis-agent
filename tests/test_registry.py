import pytest

from jarvis.tools.registry import ToolRegistry


def make():
    reg = ToolRegistry()

    @reg.register()
    def greet(name: str, times: int = 1) -> str:
        """Say hello."""
        return " ".join([f"hi {name}"] * times)

    @reg.register()
    def boom() -> str:
        """Always fails."""
        raise RuntimeError("kaboom")
    return reg


def test_mcp_style_spec():
    spec = {t["name"]: t for t in make().list_tools()}["greet"]
    assert spec["description"] == "Say hello."
    assert spec["inputSchema"] == {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string"}, "times": {"type": "integer", "default": 1}}}


def test_call_and_coercion():
    r = make().call_tool("greet", {"name": "Rehan", "times": "2"})
    assert r == {"content": [{"type": "text", "text": "hi Rehan hi Rehan"}], "isError": False}


@pytest.mark.parametrize("name,args,msg", [
    ("greet", {}, "missing required"), ("greet", {"name": "x", "evil": 1}, "unknown argument"),
    ("nope", {}, "Unknown tool"), ("boom", {}, "kaboom"),
])
def test_errors_are_returned_not_raised(name, args, msg):
    r = make().call_tool(name, args)
    assert r["isError"] and msg in r["content"][0]["text"]


def test_duplicate_registration_rejected():
    reg = make()
    with pytest.raises(ValueError):
        reg.add(lambda: None, name="greet")
