#!/bin/sh
set -e

python manage.py migrate --noinput

# Демо-каталог нужен, пока нет ключа RAWG; повторный запуск ничего не дублирует.
if [ "${SEED_DEMO:-1}" = "1" ]; then
    python manage.py seed_demo
fi

if [ -n "$RAWG_API_KEY" ] && [ "${IMPORT_RAWG_PAGES:-0}" -gt 0 ]; then
    python manage.py import_rawg --pages "$IMPORT_RAWG_PAGES" || echo "Импорт RAWG не удался — каталог работает на сохранённых данных."
fi

exec "$@"
