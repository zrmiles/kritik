# Архитектура

## Компоненты

```mermaid
flowchart LR
    subgraph Браузер
        SPA["SPA на ES-модулях<br/>src/frontend/static/frontend/js"]
    end

    subgraph Django["Django + DRF (gunicorn)"]
        FE["frontend<br/>отдаёт index.html + CSRF-cookie"]
        ACC["accounts<br/>регистрация, JWT, refresh-cookie"]
        GAMES["games<br/>каталог, фильтры, сортировки,<br/>статистика, импорт RAWG"]
        REV["reviews<br/>CRUD рецензий, права автора"]
        SAVED["saved_games<br/>личный список"]
        ADMIN["Django admin<br/>CRUD игр, журнал импорта"]
    end

    DB[("PostgreSQL<br/>(SQLite локально)")]
    RAWG[["RAWG API<br/>api.rawg.io"]]

    SPA -- "fetch /api/*, JWT" --> ACC & GAMES & REV & SAVED
    SPA -- "GET /" --> FE
    ACC & GAMES & REV & SAVED & ADMIN --> DB
    CMD["manage.py import_rawg"] -- "HTTP, ключ из .env" --> RAWG
    CMD --> DB
```

- **Где авторизация.** `accounts` выдаёт JWT. Права проверяются во view: запись рецензий и личный список требуют токен, а выборка рецензий для изменения ограничена `author = request.user`, поэтому чужие рецензии недоступны (`404`).
- **Где считается рейтинг.** `GameQuerySet.with_review_stats()` добавляет к запросу `Avg(score)` и `Count(reviews)`. Рейтинг не хранится отдельным полем, поэтому не может разойтись с рецензиями.
- **Где фильтрация.** `src/games/views.py → GameQuerySetMixin.filter_queryset_params`. Фильтры по жанрам и платформам сделаны подзапросами `pk__in`, а не join: иначе при выборе нескольких жанров строки игры размножились бы и исказили агрегаты.
- **Поиск по кириллице.** SQLite сравнивает без учёта регистра только латиницу, поэтому у игры есть служебное поле `search_title` (название в `casefold()`), оно заполняется при сохранении.
- **Фронтенд** — одностраничное приложение без сборщика. Экраны переключаются по хешу (`#/game/5`), а состояние фильтров хранится в адресе (`#/?genre=action&rating_min=8`), поэтому работают кнопка «Назад» и ссылки на результаты поиска.

## Модель данных

```mermaid
erDiagram
    USER ||--o{ REVIEW : пишет
    USER ||--o{ SAVED_GAME : сохраняет
    GAME ||--o{ REVIEW : получает
    GAME ||--o{ SAVED_GAME : "входит в"
    GAME }o--o{ GENRE : "относится к"
    GAME }o--o{ PLATFORM : "выходит на"

    USER {
        bigint id PK
        string username UK
        string display_name
        string password
    }
    GAME {
        bigint id PK
        slug slug UK
        string title
        string search_title "casefold для поиска"
        text description
        date release_date "может быть пустой"
        url cover_url
        string data_source "manual | rawg"
        string external_id "UK вместе с data_source"
        url source_url
    }
    GENRE {
        bigint id PK
        slug slug UK "совпадает со slug RAWG"
        string name UK
    }
    PLATFORM {
        bigint id PK
        slug slug UK
        string name UK
    }
    REVIEW {
        bigint id PK
        bigint author_id FK
        bigint game_id FK
        smallint score "CHECK 1..10"
        text text "10..500 символов"
        datetime created_at
        datetime updated_at
    }
    SAVED_GAME {
        bigint id PK
        bigint user_id FK
        bigint game_id FK
        datetime created_at
    }
    IMPORT_RUN {
        bigint id PK
        string source
        string status "running | success | failed"
        json parameters
        int created_count
        int updated_count
        text error
    }
```

Ограничения на уровне БД:

- `unique(author, game)` — одна рецензия на игру от пользователя;
- `check(1 <= score <= 10)`;
- `unique(user, game)` — игра не попадает в список дважды;
- `unique(data_source, external_id) where external_id is not null` — повторный импорт не создаёт дубликаты.

## Сценарий: пользователь пишет рецензию

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant S as SPA
    participant A as API
    participant D as БД

    U->>S: Открывает игру, нажимает «Написать рецензию»
    alt не авторизован
        S->>U: Окно входа/регистрации
        U->>S: Логин и пароль
        S->>A: POST /auth/login/ (X-CSRFToken)
        A-->>S: access-токен + refresh-cookie
    end
    U->>S: Выбирает оценку 1–10, пишет текст
    S->>S: Проверка: оценка выбрана, текст ≥ 10 символов
    S->>A: POST /reviews/ {game_id, score, text}
    A->>D: INSERT (unique author+game, check score)
    A-->>S: 201
    S->>A: GET /games/{id}/ и /games/{id}/reviews/
    A->>D: AVG(score), COUNT(*), распределение оценок
    A-->>S: Новый рейтинг и гистограмма
    S->>U: «Рецензия опубликована. Оценка игры пересчитана.»
```

## Сессия после перезагрузки страницы

Access-токен живёт только в памяти вкладки. При загрузке SPA вызывает `POST /auth/refresh/`: если refresh-cookie на месте, сервер выдаёт новый access-токен и пользователь снова авторизован. Если access-токен истёк во время работы, клиент получает `401`, один раз обновляет токен и повторяет запрос (`src/frontend/static/frontend/js/api.js`).
