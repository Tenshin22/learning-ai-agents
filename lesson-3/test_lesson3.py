import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ex4
import weather

KRASNOYARSK_TZ = timezone(timedelta(hours=7))


def time_string(hours_ago: float = 0) -> str:
    return (datetime.now(KRASNOYARSK_TZ) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


class FakeResponse:
    """Мини-замена ответа urlopen для тестов."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


def json_response(payload: dict) -> FakeResponse:
    return FakeResponse(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def krasn_payload(**overrides) -> dict:
    row = {
        "time": time_string(),
        "site": weather.KRASN_STATION_ID,
        "t": -0.1,
        "p": 751.2,
        "h": 90,
        "aqi": 25,
        "iaqi": 22,
        "pm25": 4.0,
        "pm10": 4.7,
        "pm25_mcp": 0.13,
    }
    row.update(overrides)

    return {
        "status": {"code": 1, "message": "OK"},
        "data": [row],
    }


def open_meteo_payload(**overrides) -> dict:
    current = {
        "time": datetime.now(KRASNOYARSK_TZ).strftime("%Y-%m-%dT%H:%M"),
        "temperature_2m": -1.0,
        "relative_humidity_2m": 80,
        "wind_speed_10m": 2.5,
        "surface_pressure": 1000.0,
    }
    current.update(overrides)

    return {"current": current}


def make_urlopen(handler):
    """Подменяет urlopen: handler получает URL и решает, что вернуть."""

    def fake_urlopen(request, timeout=None):
        url = getattr(request, "full_url", str(request))
        return handler(url)

    return fake_urlopen


def sample_weather(**overrides) -> dict:
    data = {
        "source": weather.KRASN_SOURCE,
        "source_url": weather.KRASN_SOURCE_URL,
        "station": weather.KRASN_STATION_NAME,
        "station_id": weather.KRASN_STATION_ID,
        "measured_at": time_string(),
        "data_type": "measurement",
        "aggregation": "hourly",
        "temperature_c": -0.1,
        "humidity_pct": 90.0,
        "pressure_mmhg": 751.2,
        "pm25_ugm3": 4.0,
        "pm10_ugm3": 4.7,
        "aqi": 22.0,
        "aqi_type": "Instant AQI",
        "wind_speed_ms": None,
        "is_stale": False,
        "stale_reason": None,
        "missing": ["wind_speed_ms"],
    }
    data.update(overrides)

    return data


class WeatherTests(unittest.TestCase):
    def test_primary_source_works(self):
        def handler(url):
            self.assertIn("air.krasn.ru", url)
            return json_response(krasn_payload())

        with patch.object(
            weather.urllib.request,
            "urlopen",
            new=make_urlopen(handler),
        ):
            result = weather.get_weather()

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], weather.KRASN_SOURCE)
        self.assertEqual(result["station"], weather.KRASN_STATION_NAME)
        self.assertEqual(result["station_id"], weather.KRASN_STATION_ID)
        self.assertEqual(result["data_type"], "measurement")
        self.assertFalse(result["is_stale"])
        self.assertEqual(result["temperature_c"], -0.1)
        self.assertEqual(result["humidity_pct"], 90.0)
        self.assertEqual(result["pressure_mmhg"], 751.2)
        self.assertEqual(result["pm25_ugm3"], 4.0)
        self.assertEqual(result["pm10_ugm3"], 4.7)
        self.assertEqual(result["aqi"], 22.0)
        self.assertEqual(result["aqi_type"], "Instant AQI")
        self.assertIsNone(result["wind_speed_ms"])
        self.assertIn("wind_speed_ms", result["missing"])

    def test_primary_fails_and_backup_works(self):
        def handler(url):
            if "air.krasn.ru" in url:
                raise urllib.error.URLError("нет соединения")
            self.assertIn("open-meteo.com", url)
            return json_response(open_meteo_payload())

        with patch.object(
            weather.urllib.request,
            "urlopen",
            new=make_urlopen(handler),
        ):
            result = weather.get_weather()

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], weather.OPEN_METEO_SOURCE)
        self.assertEqual(result["data_type"], "model")
        self.assertEqual(result["temperature_c"], -1.0)
        self.assertEqual(result["humidity_pct"], 80.0)
        self.assertEqual(result["pressure_mmhg"], 750.1)
        self.assertEqual(result["wind_speed_ms"], 2.5)
        self.assertIsNone(result["pm25_ugm3"])
        self.assertIsNone(result["pm10_ugm3"])
        self.assertIsNone(result["aqi"])
        self.assertIn("pm25_ugm3", result["missing"])
        self.assertIn("pm10_ugm3", result["missing"])
        self.assertIn("aqi", result["missing"])

    def test_both_sources_unavailable(self):
        def handler(url):
            raise urllib.error.URLError("нет интернета")

        with patch.object(
            weather.urllib.request,
            "urlopen",
            new=make_urlopen(handler),
        ):
            result = weather.get_weather()

        self.assertIsNone(result)

    def test_incomplete_and_stale_primary_is_returned_with_warning(self):
        stale_payload = krasn_payload(
            time=time_string(hours_ago=5),
            p=None,
            h=None,
            pm10=None,
            iaqi=None,
            aqi=60,
        )

        def handler(url):
            if "air.krasn.ru" in url:
                return json_response(stale_payload)
            raise urllib.error.URLError("резерв недоступен")

        with patch.object(
            weather.urllib.request,
            "urlopen",
            new=make_urlopen(handler),
        ):
            result = weather.get_weather()

        self.assertIsNotNone(result)
        self.assertTrue(result["is_stale"])
        self.assertIn("старше двух часов", result["stale_reason"])
        self.assertEqual(result["aqi"], 60.0)
        self.assertEqual(result["aqi_type"], "AQI (усреднённый)")
        self.assertIn("pressure_mmhg", result["missing"])
        self.assertIn("humidity_pct", result["missing"])
        self.assertIn("pm10_ugm3", result["missing"])

    def test_missing_time_is_staleness_error(self):
        payload = krasn_payload()
        del payload["data"][0]["time"]

        def handler(url):
            if "air.krasn.ru" in url:
                return json_response(payload)
            raise urllib.error.URLError("резерв недоступен")

        with patch.object(
            weather.urllib.request,
            "urlopen",
            new=make_urlopen(handler),
        ):
            result = weather.get_weather()

        self.assertIsNotNone(result)
        self.assertTrue(result["is_stale"])
        self.assertIn("время измерения отсутствует", result["stale_reason"])

    def test_invalid_json_is_handled(self):
        def handler(url):
            if "air.krasn.ru" in url:
                return FakeResponse(b"not a json")
            raise urllib.error.URLError("резерв недоступен")

        with patch.object(
            weather.urllib.request,
            "urlopen",
            new=make_urlopen(handler),
        ):
            result = weather.get_weather()

        self.assertIsNone(result)


class ChatTests(unittest.TestCase):
    def test_weather_is_only_in_system_prompt(self):
        text = ex4.format_weather(sample_weather())

        history = [
            "старая строка вместо словаря",
            {"role": "system", "content": "старый системный промпт"},
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте"},
        ]

        messages = ex4.build_messages(history, "СИСТЕМА\n" + text)

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn(weather.KRASN_STATION_NAME, messages[0]["content"])
        self.assertIn("Температура", messages[0]["content"])
        self.assertEqual(
            messages[1],
            {"role": "user", "content": "Привет"},
        )
        self.assertNotIn("Температура", messages[1]["content"])

        for message in messages:
            self.assertIsInstance(message, dict)
            self.assertIn("role", message)
            self.assertIn("content", message)

    def test_format_shows_missing_and_stale(self):
        text = ex4.format_weather(
            sample_weather(
                pm25_ugm3=None,
                pm10_ugm3=None,
                aqi=None,
                aqi_type=None,
                is_stale=True,
                stale_reason="данные старше двух часов (5.0 ч)",
            )
        )

        self.assertIn("устарели", text)
        self.assertIn("Недоступны:", text)
        self.assertIn("PM2.5", text)
        self.assertNotIn("PM2.5: ", text)

    def test_format_marks_model_data(self):
        text = ex4.format_weather(
            sample_weather(
                source=weather.OPEN_METEO_SOURCE,
                station=weather.OPEN_METEO_STATION,
                station_id=None,
                data_type="model",
                pm25_ugm3=None,
                pm10_ugm3=None,
                aqi=None,
                aqi_type=None,
            )
        )

        self.assertIn("расчётные данные", text)
        self.assertIn("Недоступны:", text)

    def test_chat_starts_and_uses_weather(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            history_path = tmp_path / "history_chat.json"

            env_path.write_text("TEST_KEY=secret\n", encoding="utf-8")
            history_path.write_text("[]", encoding="utf-8")

            captured = {}

            def fake_ask(api_key, messages, temp):
                captured["messages"] = [dict(item) for item in messages]
                return "Тестовый ответ"

            with (
                patch.object(ex4, "ENV_PATH", env_path),
                patch.object(ex4, "HISTORY_PATH", history_path),
                patch.object(
                    ex4,
                    "get_weather",
                    return_value=sample_weather(),
                ),
                patch.object(ex4, "ensure_api", return_value=True),
                patch.object(ex4, "ask_neuraldeep", side_effect=fake_ask),
                patch("builtins.input", side_effect=["Привет", "выход"]),
            ):
                ex4.main()

            sent = captured["messages"]
            self.assertEqual(sent[0]["role"], "system")
            self.assertIn(weather.KRASN_STATION_NAME, sent[0]["content"])
            self.assertIn("Температура", sent[0]["content"])
            self.assertEqual(sent[-1], {"role": "user", "content": "Привет"})
            self.assertNotIn("Температура", sent[-1]["content"])

            saved = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertTrue(all(isinstance(item, dict) for item in saved))
            self.assertEqual(saved[0]["role"], "system")
            self.assertEqual(saved[-2]["content"], "Привет")
            self.assertEqual(saved[-1]["content"], "Тестовый ответ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
