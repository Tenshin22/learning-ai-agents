import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from datetime import datetime
from weather import get_weather

# Аннотация `переменная: тип` — это подсказка для человека и редактора кода.
# Python сам её игнорирует при запуске, но IDE сможет подсказывать методы
# и предупреждать об ошибках ещё до запуска программы.

#print(os.environ)

# Вычисляет путь к папке learning-ai-agents на основе расположения самого main.py
# Path — тип «путь к файлу/папке» из модуля pathlib (удобнее работать, чем со строкой)
BASE_DIR: Path = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE_DIR / "lesson-3" / "history_chat.json"
ENV_PATH: Path = BASE_DIR / ".env"

weather = get_weather()

if weather is None:
    CURRENT_WEATHER = (
        "Актуальные данные о погоде в Красноярске недоступны. "
        "Не придумывай погодные условия."
    )
else:
    CURRENT_WEATHER = (
        f"Погода в Красноярске:\n"
        f"Температура: {weather['temperature_2m']} °C\n"
        f"Влажность: {weather['relative_humidity_2m']} %\n"
        f"Ветер: {weather['wind_speed_10m']} км/ч\n"
        f"Время данных: {weather['time']}"
    )

with open(ENV_PATH, mode="r", encoding="utf-8") as file:
    # str — обычная строка (текст)
    env: str = file.read()

# Разделяем строку, очищая от лишних пробелов и переносов
# Типы объявляем заранее — при распаковке кортежа аннотировать нельзя
env_name: str    # имя переменной окружения (например, "DEEPSEEK_API_KEY")
env_value: str   # её значение (например, сам токен)
env_name, env_value = env.strip().split("=")
os.environ[env_name] = env_value

# Получаем токен из окружения
# str | None означает «либо строка, либо None» — get() вернёт None,
# если такой переменной окружения нет
api_key: str | None = os.environ.get(env_name)

now: datetime = datetime.now()

string_date: str = str(now)

SYSTEM_PROMPT = f"ты помощник. Текущая дата:{string_date}. Текущая погода:{CURRENT_WEATHER}"

def ask_neuraldeep(api_key: str | None, messages: list[dict[str, str]], temp: float):
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
        with urllib.request.urlopen(req) as response:
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

temp = 1

if HISTORY_PATH.exists():
    try:
        with open(HISTORY_PATH, mode="r", encoding="utf-8") as f:
            messages = json.load(f)
            
    except json.JSONDecodeError:
        print("история переписки повреждена или пуста")
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

else:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
while True:
    try:
        user_prompt = input("\n--Ваш запрос---\n")
        
    except KeyboardInterrupt:
        print("\nВы вышли")
        break
    
    messages.append({"role": "user", "content": user_prompt})
    
    llm_response = ask_neuraldeep(api_key, messages, temp)
    print(llm_response)
    
    messages.append({"role": "assistant", "content": llm_response})
    
    with open(HISTORY_PATH, mode="w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    
    user_answer = input("Если хотите выйти напишите Выход\nЕсли нет Enter\nВвод: ").lower()
    
    if user_answer == "выход":
        break