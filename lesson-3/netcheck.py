# netcheck.py — проверка доступа к API NeuralDeep и автоисправление маршрута.
#
# Зачем это нужно: если на компьютере включён VPN в режиме TUN (например, Happ),
# он перехватывает весь трафик, и соединение с api.neuraldeep.ru может рваться
# на этапе TLS-рукопожатия. В этом случае python покажет загадочную ошибку вида
#   [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
#
# Этот модуль проверяет API ДО старта чата, объясняет причину простыми словами
# и при необходимости добавляет маршрут к API в обход VPN (нужно подтвердить UAC).

import socket
import subprocess
import urllib.error
import urllib.request

# Адрес для проверки: метод /v1/models не тратит токены,
# сервер просто отвечает списком моделей (или 401, если нет ключа)
API_URL: str = "https://api.neuraldeep.ru/v1/models"

# IP сервера api.neuraldeep.ru на момент написания модуля.
# Используется как запасной вариант, если DNS-запрос не сработает
API_IP: str = "91.210.169.63"


def check_api(timeout: float = 5.0) -> bool:
    # Пробуем открыть адрес API.
    # urlopen выбрасывает исключение, если соединение не получилось.
    # ВАЖНО: HTTPError (например, 401 «нет ключа») — это УСПЕХ для нас:
    # сервер ответил, значит сеть до него работает.
    req: urllib.request.Request = urllib.request.Request(API_URL, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def check_internet(timeout: float = 5.0) -> bool:
    # Проверяем заведомо рабочий сайт.
    # Это позволяет отличить «интернета нет вообще» от «блокируется только API»
    try:
        with urllib.request.urlopen("https://ya.ru", timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def find_gateway() -> tuple[str, int] | None:
    # Спрашиваем у Windows таблицу маршрутов через PowerShell (interop из WSL).
    # Берём шлюз по умолчанию (0.0.0.0/0), исключая виртуальные адаптеры:
    #   tun — VPN, Tailscale — VPN, vEthernet — WSL, Loopback — сама система.
    ps_script: str = (
        "Get-NetRoute -DestinationPrefix '0.0.0.0/0' | "
        "Where-Object { $_.InterfaceAlias -notmatch 'tun|Tailscale|vEthernet|Loopback' } | "
        "Sort-Object RouteMetric | Select-Object -First 1 | "
        'ForEach-Object { "$($_.NextHop) $($_.InterfaceIndex)" }'
    )

    try:
        proc: subprocess.CompletedProcess = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    # Ожидаем строку вида "192.168.0.1 22" — адрес шлюза и номер интерфейса
    parts: list[str] = proc.stdout.split()
    if len(parts) < 2:
        return None

    try:
        return parts[0], int(parts[1])
    except ValueError:
        return None


def fix_route() -> bool:
    # 1. Узнаём адрес реального роутера (мимо VPN)
    gw: tuple[str, int] | None = find_gateway()
    if gw is None:
        return False

    gateway: str = gw[0]
    if_index: int = gw[1]

    # 2. Узнаём актуальный IP API — он мог измениться с момента написания модуля
    try:
        ip: str = socket.gethostbyname("api.neuraldeep.ru")
    except OSError:
        ip = API_IP

    # 3. Добавляем маршрут с повышением прав.
    # Start-Process -Verb RunAs вызывает окно UAC — пользователь должен нажать «Да»
    ps_add: str = (
        "Start-Process route.exe -Verb RunAs -Wait -ArgumentList "
        f"'add {ip} mask 255.255.255.255 {gateway} metric 1 if {if_index}'"
    )

    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_add],
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False

    # 4. Проверяем, помогло ли
    return check_api()


def ensure_api() -> bool:
    # Главная функция модуля: проверить API, а при проблеме —
    # объяснить причину и предложить исправление
    if check_api():
        print("API доступен, всё в порядке")
        return True

    print("API NeuralDeep недоступен")

    if not check_internet():
        print("Интернета нет вообще — проверьте подключение к сети.")
        return False

    print("Интернет работает, но API блокируется.")
    print("Похоже, VPN в режиме TUN (например, Happ) перехватывает трафик.")

    answer: str = input("Добавить маршрут в обход VPN? Появится окно UAC [да/Enter]: ")
    if answer.strip().lower() in ("да", "д", "y", "yes"):
        print("Добавляю маршрут... подтвердите запрос в окне UAC")
        if fix_route():
            print("Готово — API доступен!")
            return True
        print("Не получилось. Откройте PowerShell от имени администратора и выполните:")
    else:
        print("Хорошо. Исправить можно вручную, в PowerShell от администратора:")

    print(f"    route add {API_IP} mask 255.255.255.255 <адрес_роутера> metric 1")
    return False


# Этот блок срабатывает только при прямом запуске файла: uv run python netcheck.py
# Удобно для быстрой диагностики сети, не запуская весь чат
if __name__ == "__main__":
    print("Проверяю API:", API_URL)

    if check_api():
        print("OK — API доступен")
    else:
        print("API недоступен")
        print("Интернет:", "есть" if check_internet() else "нет")
        print("Если интернет есть, а API нет — вероятно, виноват VPN (режим TUN).")
        print("Запустите ensure_api() или добавьте маршрут вручную (см. выше).")
