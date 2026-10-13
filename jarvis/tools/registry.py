"""MCP-style tool registry.

Tools are described the way the Model Context Protocol does it (`name`, `description`, `inputSchema` as
JSON Schema), listed with `list_tools()`, and invoked with `call_tool(name, arguments)`, which returns
`{"content": [{"type": "text", "text": ...}], "isError": bool}`. That makes it straightforward to expose the
same registry over a real MCP server later, or to mount tools from external MCP servers.
"""
import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

log = logging.getLogger(__name__)
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


def schema_from_signature(fn: Callable) -> dict:
    hints = get_type_hints(fn)
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {"type": _JSON_TYPES.get(hints.get(name, str), "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
        else:
            props[name]["default"] = p.default
    return {"type": "object", "properties": props, "required": required}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str | None = None, description: str | None = None, schema: dict | None = None):
        def deco(fn):
            t = Tool(name or fn.__name__, (description or inspect.getdoc(fn) or "").strip(),
                     schema or schema_from_signature(fn), fn)
            if t.name in self._tools:
                raise ValueError(f"tool {t.name!r} already registered")
            self._tools[t.name] = t
            return fn
        return deco

    def add(self, fn: Callable, **kw) -> None:
        self.register(**kw)(fn)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[dict]:
        return [t.spec() for t in self._tools.values()]

    def _validate(self, tool: Tool, args: dict) -> dict:
        props, req = tool.input_schema.get("properties", {}), tool.input_schema.get("required", [])
        missing = [r for r in req if r not in args]
        if missing:
            raise ValueError(f"missing required argument(s): {', '.join(missing)}")
        unknown = set(args) - set(props)
        if unknown:
            raise ValueError(f"unknown argument(s): {', '.join(sorted(unknown))}")
        out = {}
        for k, v in args.items():
            t = props[k].get("type")
            if t == "integer" and not isinstance(v, bool):
                v = int(v)
            elif t == "number" and not isinstance(v, bool):
                v = float(v)
            elif t == "string" and not isinstance(v, str):
                v = str(v)
            out[k] = v
        return out

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return _result(f"Unknown tool {name!r}. Available: {', '.join(self._tools)}", True)
        try:
            result = tool.fn(**self._validate(tool, arguments or {}))
        except Exception as e:  # tool errors go back to the model instead of crashing the agent
            log.warning("tool %s failed: %s", name, e)
            return _result(f"{type(e).__name__}: {e}", True)
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        return _result(text, False)


def _result(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}
