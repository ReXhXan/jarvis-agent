"""Built-in tools: calculator, weather, web search (stub), notes, reminders, file search, system info."""
import ast
import math
import operator
import os
import platform
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from ..storage import Store, now_iso
from .registry import ToolRegistry

# ---------- calculator: safe AST evaluation, never eval() ----------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "floor", "ceil")}
_FUNCS |= {"abs": abs, "round": round}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id in _CONSTS:
            return _CONSTS[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            left, right = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("exponent too large")
            return _BIN[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARY:
            return _UNARY[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"unsupported expression element: {type(n).__name__}")
    if len(expr) > 200:
        raise ValueError("expression too long")
    return ev(ast.parse(expr.replace("^", "**"), mode="eval"))


# ---------- weather (Open-Meteo, no API key) ----------
_WMO = {0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 51: "light drizzle",
        61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 80: "rain showers", 95: "thunderstorm"}


def get_weather(city: str, http: httpx.Client) -> dict:
    geo = http.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1}).json()
    if not geo.get("results"):
        raise ValueError(f"city not found: {city}")
    g = geo["results"][0]
    cur = http.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": g["latitude"], "longitude": g["longitude"],
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"}).json()["current"]
    return {"city": g["name"], "country": g.get("country"), "temperature_c": cur["temperature_2m"],
            "humidity_pct": cur["relative_humidity_2m"], "wind_kmh": cur["wind_speed_10m"],
            "conditions": _WMO.get(cur["weather_code"], f"code {cur['weather_code']}")}


# ---------- file search, sandboxed to configured roots ----------
def search_files(query: str, roots: list[str], max_results: int = 20, content: bool = False) -> list[str]:
    q, hits = query.lower(), []
    for root in roots:
        base = Path(root).expanduser().resolve()
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"node_modules", "__pycache__", ".venv"}]
            for f in filenames:
                p = Path(dirpath) / f
                match = q in f.lower()
                if not match and content and p.stat().st_size < 1_000_000:
                    try:
                        match = q in p.read_text(encoding="utf-8", errors="ignore").lower()
                    except OSError:
                        pass
                if match:
                    hits.append(str(p))
                    if len(hits) >= max_results:
                        return hits
    return hits


def _parse_due(when: str) -> datetime:
    """Accept ISO 8601 or relative forms like 'in 10 minutes', '2 hours', '3d'."""
    w = when.strip().lower().removeprefix("in ").strip()
    units = {"m": "minutes", "min": "minutes", "minute": "minutes", "minutes": "minutes", "mins": "minutes",
             "h": "hours", "hr": "hours", "hour": "hours", "hours": "hours",
             "d": "days", "day": "days", "days": "days"}
    num = "".join(ch for ch in w if ch.isdigit() or ch == ".")
    unit = w[len(num):].strip()
    if num and unit in units:
        return datetime.now(timezone.utc) + timedelta(**{units[unit]: float(num)})
    dt = datetime.fromisoformat(when)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_registry(store: Store, roots: list[str], http: httpx.Client | None = None,
                   allow_network: bool = True) -> ToolRegistry:
    reg = ToolRegistry()
    http = http or httpx.Client(timeout=10)

    @reg.register()
    def calculator(expression: str) -> str:
        """Evaluate a math expression, e.g. '2*(3+4)', 'sqrt(16)', '15% of 200' as '0.15*200'."""
        v = safe_eval(expression)
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)

    @reg.register()
    def weather(city: str) -> dict:
        """Current weather for a city (temperature, humidity, wind, conditions)."""
        if not allow_network:
            raise RuntimeError("network tools are disabled (ALLOW_NETWORK=false)")
        return get_weather(city, http)

    @reg.register()
    def web_search(query: str, max_results: int = 5) -> dict:
        """Search the web. STUB: plug in Tavily/SerpAPI/Brave by replacing this function."""
        return {"query": query, "results": [], "note": "web_search is a stub; configure a search provider"}

    @reg.register()
    def add_note(text: str) -> str:
        """Save a note."""
        cur = store.execute("INSERT INTO notes(text, created_at) VALUES (?, ?)", (text, now_iso()))
        return f"Saved note #{cur.lastrowid}"

    @reg.register()
    def list_notes(query: str = "") -> list[dict]:
        """List saved notes, optionally filtered by a search string."""
        return store.query("SELECT id, text, created_at FROM notes WHERE text LIKE ? ORDER BY id",
                           (f"%{query}%",))

    @reg.register()
    def delete_note(note_id: int) -> str:
        """Delete a note by id."""
        n = store.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount
        return f"Deleted note #{note_id}" if n else f"No note #{note_id}"

    @reg.register()
    def add_reminder(text: str, when: str) -> str:
        """Create a reminder. `when` is ISO 8601 or relative like 'in 30 minutes', '2 hours', '1 day'."""
        due = _parse_due(when).isoformat(timespec="seconds")
        cur = store.execute("INSERT INTO reminders(text, due_at) VALUES (?, ?)", (text, due))
        return f"Reminder #{cur.lastrowid} set for {due}"

    @reg.register()
    def list_reminders(include_done: bool = False) -> list[dict]:
        """List reminders, soonest first. Each one has an `overdue` flag."""
        rows = store.query("SELECT id, text, due_at, done FROM reminders "
                           + ("" if include_done else "WHERE done = 0 ") + "ORDER BY due_at")
        now = now_iso()
        return [r | {"overdue": not r["done"] and r["due_at"] <= now} for r in rows]

    @reg.register()
    def complete_reminder(reminder_id: int) -> str:
        """Mark a reminder as done."""
        n = store.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)).rowcount
        return f"Reminder #{reminder_id} done" if n else f"No reminder #{reminder_id}"

    @reg.register()
    def file_search(query: str, content: bool = False, max_results: int = 20) -> list[str]:
        """Find files by name (or by contents with content=true) inside the allowed folders."""
        return search_files(query, roots, max_results, content)

    @reg.register()
    def system_info() -> dict:
        """OS, Python version, CPU count, disk usage and current time."""
        du = shutil.disk_usage(Path.cwd())
        return {"os": f"{platform.system()} {platform.release()}", "python": sys.version.split()[0],
                "machine": platform.machine(), "cpus": os.cpu_count(),
                "disk_free_gb": round(du.free / 1e9, 1), "disk_total_gb": round(du.total / 1e9, 1),
                "time": datetime.now().astimezone().isoformat(timespec="seconds")}

    return reg
