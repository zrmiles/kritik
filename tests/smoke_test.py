#!/usr/bin/env python3
"""Проверка работоспособности запущенного «Критика» (smoke test).

Сценарий из трёх шагов:
  1. Главная страница открывается, каталог API отдаёт игры.
  2. Новый пользователь регистрируется и получает токен.
  3. Пользователь публикует рецензию, и у игры пересчитываются число рецензий и средняя оценка.

Нужен только Python 3 (стандартная библиотека). Запуск:
    python3 tests/smoke_test.py                       # http://127.0.0.1:8000
    python3 tests/smoke_test.py http://localhost:8000
Код возврата 0 — проект работает, 1 — проверка не пройдена.
"""

import http.cookiejar
import json
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
cookies = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(cookies))


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(f"{BASE_URL}{path}", data=data, method=method, headers=headers or {})
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with opener.open(request, timeout=10) as response:
            raw = response.read().decode()
            status = response.status
    except HTTPError as exc:
        raw, status = exc.read().decode(), exc.code
    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        payload = raw
    return status, payload


def check(condition, message):
    if not condition:
        print(f"  ✗ {message}")
        sys.exit(1)
    print(f"  ✓ {message}")


def wait_for_server(attempts=30):
    for _ in range(attempts):
        try:
            status, _ = call("GET", "/")
            if status == 200:
                return
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(2)
    print(f"Сервер {BASE_URL} не отвечает.")
    sys.exit(1)


def main():
    print(f"Проверка {BASE_URL}")
    wait_for_server()

    print("Шаг 1. Главная страница и каталог")
    status, page = call("GET", "/")
    check(status == 200 and "Критик" in page, "главная страница открывается")
    status, catalog = call("GET", "/api/games/?ordering=rating")
    check(status == 200 and catalog["count"] > 0, f"игр в каталоге: {catalog.get('count', 0)}")
    game = catalog["results"][0]

    print("Шаг 2. Регистрация")
    _, csrf = call("GET", "/api/auth/csrf/")
    csrf_header = {"X-CSRFToken": csrf["csrf_token"]}
    username = f"smoke-{uuid.uuid4().hex[:8]}"
    password = f"Smoke-{uuid.uuid4().hex}"
    status, auth = call(
        "POST",
        "/api/auth/register/",
        {"username": username, "password": password, "password_confirm": password},
        csrf_header,
    )
    check(status == 201 and auth.get("access"), f"пользователь {username} зарегистрирован")
    token = {"Authorization": f"Bearer {auth['access']}"}

    print("Шаг 3. Рецензия и пересчёт оценки")
    before = game["review_count"]
    status, review = call(
        "POST",
        "/api/reviews/",
        {"game_id": game["id"], "score": 9, "text": "Проверка работоспособности: рецензия от smoke-теста."},
        token,
    )
    check(status == 201, f"рецензия на «{game['title']}» опубликована")
    _, updated = call("GET", f"/api/games/{game['id']}/")
    check(updated["review_count"] == before + 1, f"число рецензий выросло: {before} → {updated['review_count']}")
    check(updated["average_rating"] is not None, f"средняя оценка: {updated['average_rating']}")

    # Убираем за собой рецензию, чтобы проверку можно было повторять на одной базе.
    call("DELETE", f"/api/reviews/{review['id']}/", headers=token)
    print("Проект работает.")


if __name__ == "__main__":
    main()
