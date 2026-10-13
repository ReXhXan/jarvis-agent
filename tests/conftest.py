import httpx
import pytest

from jarvis.storage import Store
from jarvis.tools.builtin import build_registry


def fake_weather_transport(request: httpx.Request) -> httpx.Response:
    if "geocoding" in request.url.host:
        name = request.url.params["name"]
        if name.lower() == "atlantis":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"results": [{"name": name, "country": "India",
                                                      "latitude": 12.97, "longitude": 77.59}]})
    return httpx.Response(200, json={"current": {"temperature_2m": 27.5, "relative_humidity_2m": 70,
                                                 "wind_speed_10m": 9.0, "weather_code": 3}})


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def registry(store, tmp_path):
    (tmp_path / "report_q3.md").write_text("quarterly numbers")
    (tmp_path / "todo.txt").write_text("call the bank about the loan")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "report_secret.md").write_text("x")
    http = httpx.Client(transport=httpx.MockTransport(fake_weather_transport))
    return build_registry(store, [str(tmp_path)], http=http)
