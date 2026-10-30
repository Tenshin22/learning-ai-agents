import json
import urllib.request

url = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=56.0184"
    "&longitude=92.8672"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
    "&timezone=Asia%2FKrasnoyarsk"
)

with urllib.request.urlopen(url, timeout=60) as response:
    data = json.load(response)

weather = data["current"]

# print("Город: Красноярск")
# print("Температура:", weather["temperature_2m"], "°C")
# print("Влажность:", weather["relative_humidity_2m"], "%")
# print("Ветер:", weather["wind_speed_10m"], "км/ч")
# print("Время данных:", weather["time"])