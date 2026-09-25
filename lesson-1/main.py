import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Аннотация `переменная: тип` — это подсказка для человека и редактора кода.
# Python сам её игнорирует при запуске, но IDE сможет подсказывать методы
# и предупреждать об ошибках ещё до запуска программы.

#print(os.environ)

# Вычисляет путь к папке learning-ai-agents на основе расположения самого main.py
# Path — тип «путь к файлу/папке» из модуля pathlib (удобнее работать, чем со строкой)
BASE_DIR: Path = Path(__file__).resolve().parent.parent
ENV_PATH: Path = BASE_DIR / ".env"

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
    "model": "gpt-oss-120b",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Привет"},
    ],
    "max_tokens": 500,
    "temperature": 0.2,
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
        print("Ответ нейросети:")
        print(result["choices"][0]["message"]["content"])

except urllib.error.HTTPError as e:
    print(f"Ошибка HTTP: {e.code}")
    print(e.read().decode("utf-8"))
except Exception as e:
    print(f"Произошла ошибка: {e}")
