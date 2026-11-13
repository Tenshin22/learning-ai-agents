import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# Подробные сообщения об ошибках. В обычном режиме они не мешают чату.
DEBUG_MODE = False

# Один HTTP-запрос не должен висеть бесконечно.
HTTP_TIMEOUT = 10

# Данные старше двух часов считаем устаревшими.
STALE_AFTER = timedelta(hours=2)

# Красноярск живёт в UTC+7 круглый год, перехода на летнее время нет.
KRASNOYARSK_TZ = timezone(timedelta(hours=7))

# Основной источник: публичный API air.krasn.ru.
KRASN_DATA_URL = "https://air.krasn.ru/api/2.0/data"
KRASN_SOURCE = "air.krasn.ru (сеть мониторинга КНЦ СО РАН)"
KRASN_SOURCE_URL = "https://air.krasn.ru/"
KRASN_STATION_ID = 4228
KRASN_STATION_NAME = "о. Татышев"

# Резервный источник: существующий Open-Meteo.
# wind_speed_unit=ms нужен, чтобы ветер был в тех же единицах, что у станции.
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=56.0184"
    "&longitude=92.8672"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure"
    "&wind_speed_unit=ms"
    "&timezone=Asia%2FKrasnoyarsk"
)
OPEN_METEO_SOURCE = "Open-Meteo (расчётные данные модели)"
OPEN_METEO_SOURCE_URL = "https://open-meteo.com/"
OPEN_METEO_STATION = "Красноярск (56.0184, 92.8672)"

# 1 гПа = 0.750061683 мм рт. ст.
HPA_TO_MMHG = 0.750061683

# Единый набор показателей. По этому списку считаем, чего не хватает.
INDICATOR_KEYS = (
    "temperature_c",
    "humidity_pct",
    "pressure_mmhg",
    "pm25_ugm3",
    "pm10_ugm3",
    "aqi",
    "wind_speed_ms",
)


def _http_get_json(url: str) -> dict:
    """Делает один GET-запрос и возвращает разобранный JSON."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "learning-ai-agents/1.0"},
    )

    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read()

    if not raw:
        raise ValueError("пустой ответ сервера")

    return json.loads(raw.decode("utf-8"))


def _number(value) -> float | None:
    """Превращает число из JSON в float, а всё неподходящее — в None."""
    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value) -> datetime | None:
    """Разбирает время API. Если время не указано — возвращает None."""
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()

    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None

    # API отдаёт время без часового пояса, но это время Красноярска.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KRASNOYARSK_TZ)

    return parsed


def _freshness(value) -> tuple[bool, str | None]:
    """Проверяет, не устарели ли данные. Возвращает (устарели, причина)."""
    measured_at = _parse_time(value)

    if measured_at is None:
        return True, "время измерения отсутствует или не распознано"

    age = datetime.now(KRASNOYARSK_TZ) - measured_at

    if age > STALE_AFTER:
        hours = age.total_seconds() / 3600
        return True, f"данные старше двух часов ({hours:.1f} ч)"

    if age < -STALE_AFTER:
        return True, "время измерения заметно опережает текущее время"

    return False, None


def _make_result(
    *,
    source: str,
    source_url: str,
    station: str,
    station_id: int | None,
    measured_at: str | None,
    data_type: str,
    aggregation: str,
    values: dict,
    aqi_type: str | None = None,
) -> dict:
    """Собирает ответ разных источников в один понятный словарь."""
    result = {
        "source": source,
        "source_url": source_url,
        "station": station,
        "station_id": station_id,
        "measured_at": measured_at,
        "data_type": data_type,
        "aggregation": aggregation,
        "temperature_c": values.get("temperature_c"),
        "humidity_pct": values.get("humidity_pct"),
        "pressure_mmhg": values.get("pressure_mmhg"),
        "pm25_ugm3": values.get("pm25_ugm3"),
        "pm10_ugm3": values.get("pm10_ugm3"),
        "aqi": values.get("aqi"),
        "aqi_type": aqi_type,
        "wind_speed_ms": values.get("wind_speed_ms"),
    }

    result["is_stale"], result["stale_reason"] = _freshness(measured_at)
    result["missing"] = [
        key for key in INDICATOR_KEYS if result.get(key) is None
    ]

    return result


def _krasn_url() -> str:
    """Собирает адрес запроса за последними часами одной станции."""
    now = datetime.now(KRASNOYARSK_TZ)

    params = urllib.parse.urlencode(
        {
            "time_begin": (now - timedelta(hours=3)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "time_end": now.strftime("%Y-%m-%d %H:%M:%S"),
            "time_interval": "hour",
            "sites": KRASN_STATION_ID,
        }
    )

    return f"{KRASN_DATA_URL}?{params}"


def _get_krasn_weather() -> tuple[dict | None, str | None]:
    """Получает данные air.krasn.ru. Возвращает (погода, текст ошибки)."""
    url = _krasn_url()

    try:
        payload = _http_get_json(url)
    except urllib.error.HTTPError as error:
        return None, f"air.krasn.ru: HTTP {error.code}"
    except urllib.error.URLError as error:
        return None, f"air.krasn.ru: нет соединения ({error.reason})"
    except TimeoutError:
        return None, "air.krasn.ru: превышено время ожидания"
    except (OSError, ValueError) as error:
        # ValueError покрывает и json.JSONDecodeError, и пустой ответ.
        return None, f"air.krasn.ru: {error}"

    if not isinstance(payload, dict):
        return None, "air.krasn.ru: ответ не является JSON-объектом"

    status = payload.get("status")
    if not isinstance(status, dict) or status.get("code") != 1:
        message = status.get("message") if isinstance(status, dict) else "нет статуса"
        return None, f"air.krasn.ru: ошибка API ({message})"

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        return None, "air.krasn.ru: нет данных за последние 3 часа"

    # Берём последнюю по времени строку нужной станции.
    row = None
    for item in reversed(rows):
        if isinstance(item, dict) and item.get("site") in (None, KRASN_STATION_ID):
            row = item
            break

    if row is None:
        return None, "air.krasn.ru: в ответе нет данных нужной станции"

    measured_at = row.get("time") if isinstance(row.get("time"), str) else None

    # iaqi — это Instant AQI, который показывает сам сайт.
    # Если его нет, берём обычный aqi.
    aqi = _number(row.get("iaqi"))
    aqi_type = "Instant AQI"
    if aqi is None:
        aqi = _number(row.get("aqi"))
        aqi_type = "AQI (усреднённый)" if aqi is not None else None

    values = {
        "temperature_c": _number(row.get("t")),
        "humidity_pct": _number(row.get("h")),
        "pressure_mmhg": _number(row.get("p")),
        "pm25_ugm3": _number(row.get("pm25")),
        "pm10_ugm3": _number(row.get("pm10")),
        "aqi": aqi,
        # В публичном API 2.0 ветра нет, но поле wv поддерживаем на будущее.
        "wind_speed_ms": _number(row.get("wv")),
    }

    result = _make_result(
        source=KRASN_SOURCE,
        source_url=KRASN_SOURCE_URL,
        station=KRASN_STATION_NAME,
        station_id=KRASN_STATION_ID,
        measured_at=measured_at,
        data_type="measurement",
        aggregation="hourly",
        values=values,
        aqi_type=aqi_type,
    )

    return result, None


def _get_open_meteo_weather() -> tuple[dict | None, str | None]:
    """Получает расчётные данные Open-Meteo. Это резервный источник."""
    try:
        payload = _http_get_json(OPEN_METEO_URL)
    except urllib.error.HTTPError as error:
        return None, f"Open-Meteo: HTTP {error.code}"
    except urllib.error.URLError as error:
        return None, f"Open-Meteo: нет соединения ({error.reason})"
    except TimeoutError:
        return None, "Open-Meteo: превышено время ожидания"
    except (OSError, ValueError) as error:
        return None, f"Open-Meteo: {error}"

    if not isinstance(payload, dict):
        return None, "Open-Meteo: ответ не является JSON-объектом"

    current = payload.get("current")
    if not isinstance(current, dict):
        return None, "Open-Meteo: в ответе нет блока current"

    pressure_hpa = _number(current.get("surface_pressure"))
    pressure_mmhg = (
        round(pressure_hpa * HPA_TO_MMHG, 1)
        if pressure_hpa is not None
        else None
    )

    values = {
        "temperature_c": _number(current.get("temperature_2m")),
        "humidity_pct": _number(current.get("relative_humidity_2m")),
        "pressure_mmhg": pressure_mmhg,
        # Open-Meteo в этом запросе не даёт PM и AQI.
        "pm25_ugm3": None,
        "pm10_ugm3": None,
        "aqi": None,
        "wind_speed_ms": _number(current.get("wind_speed_10m")),
    }

    measured_at = (
        current.get("time") if isinstance(current.get("time"), str) else None
    )

    result = _make_result(
        source=OPEN_METEO_SOURCE,
        source_url=OPEN_METEO_SOURCE_URL,
        station=OPEN_METEO_STATION,
        station_id=None,
        measured_at=measured_at,
        data_type="model",
        aggregation="current",
        values=values,
    )

    return result, None


def _print_weather(weather: dict) -> None:
    """Печатает краткую сводку для отладки."""
    print(f"Источник: {weather['source']}")
    print(f"Станция: {weather['station']}")
    print(f"Время измерения: {weather['measured_at']}")
    print(f"Устарели: {weather['is_stale']} ({weather['stale_reason']})")
    print(f"Недоступны: {', '.join(weather['missing']) or 'нет'}")


def get_weather() -> dict | None:
    """Возвращает погоду в едином формате или None, если источников нет.

    Сначала пробуем air.krasn.ru. Если он недоступен или данные устарели,
    пробуем Open-Meteo. Повторных запросов и бесконечных циклов нет.
    """
    primary, primary_error = _get_krasn_weather()

    if primary is not None and not primary["is_stale"]:
        if DEBUG_MODE:
            _print_weather(primary)
        return primary

    backup, backup_error = _get_open_meteo_weather()

    if backup is not None and not backup["is_stale"]:
        if DEBUG_MODE:
            if primary is not None:
                print("Данные air.krasn.ru устарели:", primary["stale_reason"])
            _print_weather(backup)
        return backup

    # Резерв тоже не дал свежих данных. Лучше показать устаревшие
    # фактические измерения с явным предупреждением, чем ничего.
    if primary is not None:
        if DEBUG_MODE:
            print("air.krasn.ru вернул устаревшие данные:", primary["stale_reason"])
            _print_weather(primary)
        return primary

    if backup is not None:
        if DEBUG_MODE:
            print("Open-Meteo вернул устаревшие данные:", backup["stale_reason"])
            _print_weather(backup)
        return backup

    if DEBUG_MODE:
        print("Не удалось получить погоду.")
        print("air.krasn.ru:", primary_error)
        print("Open-Meteo:", backup_error)

    return None
