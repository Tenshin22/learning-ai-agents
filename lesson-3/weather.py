import json
import urllib.request
import urllib.error

DEBUG_MODE = False

def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=56.0184"
        "&longitude=92.8672"
        "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        "&timezone=Asia%2FKrasnoyarsk")

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.load(response)
            
        weather = data["current"]

        if DEBUG_MODE:
            print("Город: Красноярск")
            print("Температура:", weather["temperature_2m"], "°C")
            print("Влажность:", weather["relative_humidity_2m"], "%")
            print("Ветер:", weather["wind_speed_10m"], "км/ч")
            print("Время данных:", weather["time"])

        
    except urllib.error.HTTPError as error:
        if DEBUG_MODE:
            print("Ошибка сервера:", error.code)

    except urllib.error.URLError as error:
        if DEBUG_MODE:
            print("Не удалось подключиться к серверу погоды.")
            print("Проверьте интернет или подключение к VPN.")
            print("Подробности:", error.reason)

    except TimeoutError:
        if DEBUG_MODE:
            print("Сервер слишком долго не отвечает.")
            print("Попробуйте включить VPN или повторить запрос.")

    except (KeyError, json.JSONDecodeError):
        print("Не удалось прочитать данные о погоде.")