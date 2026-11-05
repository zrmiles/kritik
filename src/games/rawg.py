"""Клиент RAWG API и сохранение полученных игр в БД.

Документация провайдера: https://api.rawg.io/docs/
"""

import json
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from .models import Game, Genre, Platform


class RawgError(Exception):
    """Провайдер недоступен, отклонил запрос или вернул некорректные данные."""


class RawgClient:
    def __init__(self, api_key=None, base_url=None, timeout=None):
        self.api_key = api_key if api_key is not None else settings.RAWG_API_KEY
        self.base_url = (base_url or settings.RAWG_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.RAWG_TIMEOUT
        if not self.api_key:
            raise RawgError("Не задан RAWG_API_KEY. Получите ключ на https://rawg.io/apidocs и добавьте его в .env.")

    def _get(self, path, **params):
        query = urlencode({"key": self.api_key, **params})
        request = Request(f"{self.base_url}{path}?{query}", headers={"User-Agent": "Kritik/1.0"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RawgError(f"RAWG ответил ошибкой HTTP {exc.code} для {path}.") from exc
        except (URLError, TimeoutError) as exc:
            raise RawgError(f"RAWG недоступен: {getattr(exc, 'reason', exc)}.") from exc
        except ValueError as exc:
            raise RawgError("RAWG вернул ответ, который не удалось разобрать как JSON.") from exc

    def list_games(self, page=1, page_size=40, search="", ordering="-added"):
        params = {"page": page, "page_size": page_size, "ordering": ordering}
        if search:
            params["search"] = search
        data = self._get("/games", **params)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise RawgError("RAWG вернул список игр в неожиданном формате.")
        return data["results"]

    def game_details(self, rawg_id):
        data = self._get(f"/games/{rawg_id}")
        if not isinstance(data, dict):
            raise RawgError(f"RAWG вернул данные игры {rawg_id} в неожиданном формате.")
        return data


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _get_or_create_named(model, slug, name):
    """Находит справочник по slug, затем по имени; существующие (в том числе русские) названия не перезаписывает."""
    slug = slugify(slug or name)[:50]
    if not slug or not name:
        return None
    item = model.objects.filter(slug=slug).first() or model.objects.filter(name=name).first()
    return item or model.objects.create(slug=slug, name=name[:100])


def _unique_slug(base, rawg_id, game=None):
    # SlugField ограничен 50 символами: оставляем место под суффикс "-rawg-<id>".
    slug = slugify(base)[:36] or f"game-{rawg_id}"
    taken = Game.objects.filter(slug=slug)
    if game is not None:
        taken = taken.exclude(pk=game.pk)
    return f"{slug}-rawg-{rawg_id}" if taken.exists() else slug


@transaction.atomic
def save_rawg_game(data, details=None):
    """Создаёт или обновляет игру по RAWG id. Возвращает (game, created)."""
    rawg_id = data.get("id")
    title = (data.get("name") or "").strip()
    if not rawg_id or not title:
        raise RawgError("В ответе RAWG нет id или названия игры.")

    game = Game.objects.filter(data_source=Game.DataSource.RAWG, external_id=str(rawg_id)).first()
    created = game is None
    if created:
        game = Game(data_source=Game.DataSource.RAWG, external_id=str(rawg_id))

    rawg_slug = data.get("slug") or title
    game.slug = _unique_slug(rawg_slug, rawg_id, game if not created else None)
    game.title = title[:200]
    game.release_date = _parse_date(data.get("released"))
    game.cover_url = data.get("background_image") or ""
    game.source_url = f"https://rawg.io/games/{rawg_slug}"
    if details and details.get("description_raw"):
        game.description = details["description_raw"].strip()
    elif created:
        game.description = ""
    game.save()

    genres = [_get_or_create_named(Genre, g.get("slug"), g.get("name")) for g in data.get("genres") or []]
    platforms = [
        _get_or_create_named(Platform, p["platform"].get("slug"), p["platform"].get("name"))
        for p in data.get("platforms") or []
        if isinstance(p, dict) and isinstance(p.get("platform"), dict)
    ]
    game.genres.set([g for g in genres if g])
    game.platforms.set([p for p in platforms if p])
    return game, created
