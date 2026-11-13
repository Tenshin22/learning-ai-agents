import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from datetime import datetime
from weather import get_weather
from netcheck import ensure_api

# Аннотация `переменная: тип` — это подсказка для человека и редактора кода.
# Python сам её игнорирует при запуске, но IDE сможет подсказывать методы
# и предупреждать об ошибках ещё до запуска программы.

# Вычисляет путь к папке learning-ai-agents на основе расположения самого ex4.py
# Path — тип «путь к файлу/папке» из модуля pathlib (удобнее работать, чем со строкой)
BASE_DIR: Path = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE_DIR / "lesson-3" / "history_chat.json"
ENV_PATH: Path = BASE_DIR / ".env"

# Пары «ключ в словаре погоды, подпись, единица измерения».
# По этому списку ex4.py показывает только те показатели, которые есть.
WEATHER_FIELDS = (
    ("temperature_c", "Температура", "°C"),
    ("humidity_pct", "Влажность", "%"),
    ("pressure_mmhg", "Давление", "мм рт. ст."),
    ("pm25_ugm3", "PM2.5", "мкг/м³"),
    ("pm10_ugm3", "PM10", "мкг/м³"),
    ("aqi", "Индекс качества воздуха", ""),
    ("wind_speed_ms", "Скорость ветра", "м/с"),
)


def _format_number(value: float) -> str:
    """Печатает 4.0 как «4», а -0.1 оставляет как «-0.1»."""
    if value == 0:
        return "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def format_weather(weather: dict | None) -> str:
    """Превращает единый словарь погоды в текст для системного промпта."""
    if weather is None:
        return (
            "Актуальные данные о погоде в Красноярске недоступны. "
            "Не придумывай погодные условия."
        )

    lines: list[str] = []

    if weather.get("data_type") == "measurement":
        lines.append("Данные: фактические измерения станции.")
    else:
        lines.append(
            "Данные: расчётные данные модели Open-Meteo, "
            "а не измерения станции."
        )

    lines.append(f"Источник: {weather.get('source', 'неизвестен')}")

    station = weather.get("station")
    if station:
        lines.append(f"Станция: {station}")

    measured_at = weather.get("measured_at")
    lines.append(f"Время измерения: {measured_at or 'не указано'}")

    if weather.get("is_stale"):
        reason = weather.get("stale_reason") or "причина не указана"
        lines.append(f"ВНИМАНИЕ: данные устарели — {reason}.")

    for key, label, unit in WEATHER_FIELDS:
        value = weather.get(key)
        if value is None:
            continue

        if key == "aqi" and weather.get("aqi_type"):
            label = f"{label} ({weather['aqi_type']})"

        suffix = f" {unit}" if unit else ""
        lines.append(f"{label}: {_format_number(value)}{suffix}")

    missing = [
        label
        for key, label, _unit in WEATHER_FIELDS
        if weather.get(key) is None
    ]
    if missing:
        lines.append("Недоступны: " + ", ".join(missing) + ".")

    return "\n".join(lines)


def build_messages(history: list, system_prompt: str) -> list[dict[str, str]]:
    """Оставляет только корректные сообщения и добавляет один системный промпт.

    В старом history_chat.json могла лежать строка вместо словаря.
    Такие элементы отбрасываются, а нормальная история user/assistant
    сохраняется.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    if not isinstance(history, list):
        return messages

    for item in history:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})

    return messages


def load_history(path: Path) -> list:
    """Читает историю переписки. При ошибке возвращает пустой список."""
    if not path.exists():
        return []

    try:
        with open(path, mode="r", encoding="utf-8") as file:
            history = json.load(file)
    except (json.JSONDecodeError, OSError):
        print("История переписки повреждена или пуста — начинаю новую.")
        return []

    if not isinstance(history, list):
        print("История переписки имеет неверный формат — начинаю новую.")
        return []

    return history


def save_history(path: Path, messages: list[dict[str, str]]) -> None:
    """Сохраняет историю только после успешного ответа модели."""
    with open(path, mode="w", encoding="utf-8") as file:
        json.dump(messages, file, ensure_ascii=False, indent=2)


def ask_neuraldeep(
    api_key: str | None,
    messages: list[dict[str, str]],
    temp: float,
):
    # 2. Настройка запроса к NeuralDeep
    # Ссылка должна вести на конкретный метод создания диалога
    url: str = "https://api.neuraldeep.ru/v1/chat/completions"

    # Заголовки (Headers) [2]
    # dict[str, str] — словарь, где и ключи, и значения — строки
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Данные запроса (Body)
    # dict[str, Any] — словарь со строковыми ключами и значениями любого типа:
    # Any нужен, потому что значения разные (строка, список, число)
    data: dict[str, Any] = {
        "model": "qwen3.6-35b-a3b",
        "messages": messages,
        "max_tokens": 2000,
        "temperature": temp,
    }

    # Кодируем JSON в байты (urllib требует bytes для POST-запросов) [1, 2]
    # bytes — последовательность байтов, а не текст
    json_data: bytes = json.dumps(data).encode("utf-8")

    # Создаем объект запроса [2]
    # Request — класс из urllib.request, описывающий HTTP-запрос
    req: urllib.request.Request = urllib.request.Request(
        url, data=json_data, headers=headers, method="POST"
    )

    # 3. Выполнение запроса
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            # Читаем и декодируем ответ: байты -> строка
            res_body: str = response.read().decode("utf-8")
            # Парсим JSON для удобной работы с результатом:
            # получаем словарь со строковыми ключами и значениями любого типа
            result: dict[str, Any] = json.loads(res_body)

            # Выводим ответ модели
            return result["choices"][0]["message"]["content"]

    except urllib.error.HTTPError as e:
        print(f"Ошибка HTTP: {e.code}")
        print(e.read().decode("utf-8"))
    except Exception as e:
        return f"Произошла ошибка: {e}"


def main() -> None:
    weather = get_weather()
    current_weather = format_weather(weather)

    with open(ENV_PATH, mode="r", encoding="utf-8") as file:
        # str — обычная строка (текст)
        env: str = file.read()

    # Разделяем строку, очищая от лишних пробелов и переносов.
    # split("=", 1) не ломается, если в значении ключа тоже есть «=».
    # Типы объявляем заранее — при распаковке кортежа аннотировать нельзя
    env_name: str    # имя переменной окружения (например, "DEEPSEEK_API_KEY")
    env_value: str   # её значение (например, сам токен)
    env_name, env_value = env.strip().split("=", 1)
    os.environ[env_name] = env_value

    # Получаем токен из окружения
    # str | None означает «либо строка, либо None» — get() вернёт None,
    # если такой переменной окружения нет
    api_key: str | None = os.environ.get(env_name)

    now: datetime = datetime.now()

    # Погода добавляется только в системный промпт, а не в каждое
    # сообщение пользователя. Так история остаётся чистой.
    SYSTEM_PROMPT = (
        f"Ты помощник. Текущая дата: {now}.\n"
        f"Данные о погоде в Красноярске:\n{current_weather}\n"
        "Используй эти данные как справочную информацию. "
        "Если показатель отсутствует или данные устарели, обязательно скажи "
        "об этом и не придумывай значения."
    )

    messages = build_messages(load_history(HISTORY_PATH), SYSTEM_PROMPT)

    # Проверяем доступ к API до старта чата: если сеть или VPN мешают,
    # модуль netcheck объяснит причину и предложит исправление
    if not ensure_api():
        print("Без доступа к API чат не сможет работать. Выходим.")
        return

    temp = 1.0

    while True:
        try:
            user_prompt = input("\n--Ваш запрос---\n")

        except KeyboardInterrupt:
            print("\nВы вышли")
            break

        # Пользовательское сообщение — только его текст, без погоды.
        messages.append({"role": "user", "content": user_prompt})

        try:
            llm_response = ask_neuraldeep(api_key, messages, temp)
        except KeyboardInterrupt:
            print("\n\nНе делай мне больно ПОЖАЛУЙСТА. Не нажимай Ctrl + C")
            llm_response = None

        if isinstance(llm_response, str) and llm_response.strip():
            print(llm_response)
            messages.append({"role": "assistant", "content": llm_response})

            try:
                save_history(HISTORY_PATH, messages)
            except OSError as error:
                print("Не удалось сохранить историю:", error)
        else:
            print("Не удалось получить ответ от модели.")

        try:
            user_answer = input(
                "\nЕсли хотите выйти напишите Выход\n"
                "Если нет Enter\nВвод: "
            ).lower()
        except KeyboardInterrupt:
            print("\nВы вышли")
            break

        if user_answer == "выход":
            break


# Этот блок срабатывает только при прямом запуске файла.
# Благодаря ему тесты могут импортировать функции, не запуская чат и сеть.
if __name__ == "__main__":
    main()
