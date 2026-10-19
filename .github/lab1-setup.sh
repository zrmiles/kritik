#!/usr/bin/env bash
# Настройка репозитория на GitHub для ЛР 1 (задачи 1, 2, 4, 5).
#
# Нужен GitHub CLI: brew install gh && gh auth login
#
#   .github/lab1-setup.sh setup [логин_преподавателя]
#       создаёт публичный репозиторий, отправляет main и lab-1, заводит метки,
#       защищает main, выдаёт преподавателю доступ на чтение, создаёт issues и PR lab-1 → main.
#   .github/lab1-setup.sh finish
#       выполняется после одобрения преподавателем: сливает PR, ставит тег lab-1,
#       закрывает issue product.
set -euo pipefail

REPO_NAME="${REPO_NAME:-kritik}"
cd "$(git rev-parse --show-toplevel)"

require_gh() {
    command -v gh >/dev/null || { echo "Установите GitHub CLI: brew install gh && gh auth login"; exit 1; }
    gh auth status >/dev/null 2>&1 || { echo "Выполните gh auth login"; exit 1; }
}

issue() { # заголовок метка тело → номер issue
    local url
    if [ -n "$2" ]; then
        url=$(gh issue create --title "$1" --label "$2" --body "$3")
    else
        url=$(gh issue create --title "$1" --body "$3")
    fi
    echo "${url##*/}"
}

setup() {
    local teacher="${1:-}"
    require_gh

    # Задача 2. Репозиторий. Публичный, потому что защита веток на бесплатном тарифе работает только для публичных.
    if ! git remote get-url origin >/dev/null 2>&1; then
        gh repo create "$REPO_NAME" --public --source=. --remote=origin \
            --description "Критик — агрегатор пользовательских отзывов на видеоигры (Django + DRF)"
    fi
    git push -u origin main lab-1
    local repo url
    repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
    url="https://github.com/$repo"

    # Метки.
    gh label create review --color 0E8A16 --description "Замечание преподавателя или рецензента" --force
    gh label create bug --color D73A4A --description "Ошибка" --force
    gh label create change-request --color FBCA04 --description "Запрос на изменение требований (CR-n)" --force
    gh label create question --color D876E3 --description "Вопрос, требующий решения" --force

    # Защита main: только через pull request, обязательный зелёный CI, правило распространяется и на администратора.
    gh api -X PUT "repos/$repo/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": {"strict": true, "contexts": ["test", "docker"]},
  "enforce_admins": true,
  "required_pull_request_reviews": {"required_approving_review_count": 0},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

    # Доступ преподавателя на чтение (issues и pull requests входят в право pull).
    if [ -n "$teacher" ]; then
        gh api -X PUT "repos/$repo/collaborators/$teacher" -f permission=pull >/dev/null
        echo "Преподавателю $teacher отправлено приглашение (доступ на чтение)."
    fi

    # Задача 1. Issue product.
    local product
    product=$(issue "product: паспорт проекта «Критик» и план на семестр" "" "$(cat <<EOF
**Репозиторий:** $url
**Паспорт:** [docs/00-project.md]($url/blob/lab-1/docs/00-project.md)

**Проект:** «Критик» — агрегатор пользовательских отзывов на видеоигры. Собственный проект, начат 26.09.2026, лицензия MIT.

**Проблема:** оценки игр в магазинах и у изданий смешаны с маркетингом, а мнения на форумах разрознены. «Критик» показывает только оценки (1–10) и короткие рецензии пользователей сервиса, а также даёт удобный поиск по каталогу из RAWG.

**Роли:** гость, пользователь, администратор и внешняя система RAWG API.
**Сущности (5):** игра, жанр, платформа, рецензия, запись личного списка.
**Функции (9):** вход и регистрация; поиск, фильтры и сортировки; страница игры; CRUD рецензии; личный список; мои рецензии; сводка каталога; импорт из RAWG; администрирование.
**Три основные:** поиск по каталогу с фильтрами, рецензии с пересчётом средней оценки, импорт из RAWG.
**Стек:** Python 3.13, Django 5.2, DRF, SimpleJWT, PostgreSQL/SQLite, JS без сборщика, Docker, GitHub Actions.
**Команда:** индивидуально, Лазарев Юрий (все роли).

**План на семестр (≈ 68 ч):** ЛР 2 — спецификация UR/FR/NFR; ЛР 3 — валидация и CR (полезность рецензий, публичный профиль); ЛР 4 — архитектура C4 и ADR; ЛР 5 — тесты в tests/, T-n, покрытие ≥ 80 %, реализация CR; ЛР 6 — выпуск v1.0.0, развёртывание. Подробнее в разделе 7 паспорта.

Прошу согласовать выбор проекта и план. Issue остаётся открытым до завершения задачи 5.
EOF
)")

    # Задача 4. Наблюдения о проблемах.
    issue "Приложение запускается с небезопасным SECRET_KEY при DJANGO_DEBUG=false" bug "$(cat <<'EOF'
**Где:** `src/config/settings.py` — `SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key-...")`; `docker-compose.yml` — значение по умолчанию `docker-local-secret-key-change-me-in-production`.

**Шаги:** запустить `docker compose up` без `DJANGO_SECRET_KEY` (DEBUG выключен).
**Ожидается:** запуск прерывается с понятной ошибкой.
**Фактически:** приложение работает с общеизвестным ключом. JWT и сессии можно подделать.

**Предложение:** при `DEBUG=false` завершать запуск с `ImproperlyConfigured`, если ключ не задан или совпадает с ключом разработки. В compose ключ не задавать по умолчанию. Запланировано на ЛР 6.
EOF
)" >/dev/null

    issue "Условия использования RAWG API: атрибуция, лимиты, публичное развёртывание" question "$(cat <<'EOF'
Каталог импортируется из RAWG API. Нужно выяснить по условиям RAWG:
- обязательна ли атрибуция (ссылка на RAWG) и где её показывать;
- какие лимиты запросов действуют на бесплатном ключе;
- можно ли публично развернуть учебный стенд с данными и обложками RAWG (обложки подгружаются напрямую с CDN `media.rawg.io`).

Ответы повлияют на NFR (ЛР 2) и `docs/05-deployment.md` (ЛР 6).
EOF
)" >/dev/null

    issue "Производительность каталога: рейтинг вычисляется агрегатом на каждый запрос" question "$(cat <<'EOF'
`GameQuerySet.with_review_stats()` считает `Avg(score)` и `Count(reviews)` при каждом запросе списка. Это гарантирует согласованность, но при тысячах игр и десятках тысяч рецензий сортировка по оценке может стать медленной.

Нужно решить:
1. какое время ответа каталога записать в NFR;
2. нужна ли денормализация (поля `average_rating`, `review_count` и пересчёт при изменении рецензии) или достаточно индексов;
3. как измерять: нагрузочный прогон на сгенерированных данных.
EOF
)" >/dev/null

    issue "Тестирование: расположение тестов, покрытие, пагинация каталога" question "$(cat <<'EOF'
- 33 теста лежат в `src/<app>/tests.py`, а курс предполагает каталог `tests/`. Переносить ли их, и как настроить обнаружение тестов Django?
- Покрытие не измеряется. Какой порог задать в CI (предварительно 80 %)?
- Подгрузка «Показать ещё» не проверяется на демо-каталоге: в нём 24 игры при размере страницы 24. Нужны тестовые данные больше одной страницы.

Решение — в ЛР 5.
EOF
)" >/dev/null

    # Ссылка на репозиторий в issue product (требование задачи 2).
    gh issue comment "$product" --body "Репозиторий настроен: $url. Ветка main защищена (только PR и зелёный CI), метки review, bug, change-request и question созданы."

    gh pr create --base main --head lab-1 --title "ЛР 1: запуск проекта" --body "$(cat <<EOF
Лабораторная работа № 1 «Запуск проекта».

- Задача 1: паспорт \`docs/00-project.md\`, issue #$product.
- Задача 2: структура каталогов курса (код в \`src/\`), LICENSE, .gitignore, защита main, метки.
- Задача 3: точные версии зависимостей и Python, раздел README «Запуск», \`tests/smoke_test.py\`, протокол проверки в чистом контейнере.
- Задача 4: структура проекта, карта функций, состояние практик; 4 issues (bug и question).
- Задача 5: исследование выполнимости и план на семестр.

Refs #$product

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
    echo
    echo "Готово. Issue product: $url/issues/$product. После одобрения выполните: .github/lab1-setup.sh finish"
}

finish() {
    require_gh
    local product
    product=$(gh issue list --state open --search "product: in:title" --json number -q '.[0].number')
    gh pr merge lab-1 --merge
    git switch main
    git pull --ff-only
    git tag -a lab-1 -m "Лабораторная работа 1: запуск проекта"
    git push origin lab-1
    gh issue close "$product" --comment "План согласован, ЛР 1 слита в main, поставлен тег lab-1."
}

case "${1:-}" in
    setup) shift; setup "$@" ;;
    finish) finish ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
esac
