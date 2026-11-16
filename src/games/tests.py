from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from reviews.models import Review

from .models import Game, Genre, ImportRun, Platform
from .rawg import RawgError

User = get_user_model()


def make_game(slug, title, released, genres=(), platforms=(), scores=()):
    game = Game.objects.create(slug=slug, title=title, release_date=released)
    game.genres.set([Genre.objects.get_or_create(slug=s, defaults={"name": s.title()})[0] for s in genres])
    game.platforms.set([Platform.objects.get_or_create(slug=s, defaults={"name": s.upper()})[0] for s in platforms])
    for index, score in enumerate(scores):
        author, _ = User.objects.get_or_create(username=f"critic{index}")
        Review.objects.create(author=author, game=game, score=score, text="Текст рецензии для теста.")
    return game


class CatalogFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_game("hades", "Hades", date(2020, 9, 17), ["action", "indie"], ["pc", "switch"], [10, 8])
        make_game("celeste", "Celeste", date(2018, 1, 25), ["platformer", "indie"], ["pc", "switch"], [9])
        make_game("elden", "Elden Ring", date(2022, 2, 25), ["action", "rpg"], ["pc", "ps5"], [10, 4, 7])
        make_game("mor", "Мор", date(2019, 5, 23), ["adventure"], ["pc"], [])
        make_game("undated", "Без даты", None, ["rpg"], ["ps5"], [])

    def setUp(self):
        self.client = APIClient()

    def titles(self, query=""):
        response = self.client.get(f"/api/games/?{query}")
        self.assertEqual(response.status_code, 200, response.data)
        return [game["title"] for game in response.data["results"]]

    def test_filters_combine(self):
        self.assertEqual(self.titles("genre=action&platform=switch"), ["Hades"])
        self.assertEqual(self.titles("genre=indie&year_from=2019"), ["Hades"])
        self.assertEqual(self.titles("platform=pc&year_to=2019&ordering=title"), ["Celeste", "Мор"])

    def test_multiple_genres_match_any_without_duplicates_or_skewed_average(self):
        response = self.client.get("/api/games/?genre=action,indie,rpg&ordering=title")
        titles = [game["title"] for game in response.data["results"]]
        self.assertEqual(titles, ["Celeste", "Elden Ring", "Hades", "Без даты"])
        self.assertEqual(response.data["count"], 4)
        hades = next(game for game in response.data["results"] if game["title"] == "Hades")
        self.assertEqual((float(hades["average_rating"]), hades["review_count"]), (9.0, 2))

    def test_search_is_case_insensitive_for_cyrillic(self):
        self.assertEqual(self.titles("search=мОр"), ["Мор"])
        self.assertEqual(self.titles("search=ELDEN"), ["Elden Ring"])

    def test_rating_filters(self):
        self.assertEqual(self.titles("rating_min=9"), ["Hades", "Celeste"])
        self.assertEqual(self.titles("reviewed=1&ordering=title"), ["Celeste", "Elden Ring", "Hades"])

    def test_orderings(self):
        # По оценке: без оценок — в конце; при равной оценке выше игра с большим числом рецензий.
        self.assertEqual(self.titles("ordering=rating"), ["Hades", "Celeste", "Elden Ring", "Без даты", "Мор"])
        self.assertEqual(self.titles("ordering=reviews")[:3], ["Elden Ring", "Hades", "Celeste"])
        self.assertEqual(self.titles("ordering=newest"), ["Elden Ring", "Hades", "Мор", "Celeste", "Без даты"])
        self.assertEqual(self.titles("ordering=oldest")[:2], ["Celeste", "Мор"])

    def test_invalid_parameters_are_reported(self):
        for query, field in [
            ("ordering=random", "ordering"),
            ("year=abc", "year"),
            ("year_from=2022&year_to=2020", "year_to"),
            ("rating_min=11", "rating_min"),
            ("rating_min=x", "rating_min"),
        ]:
            response = self.client.get(f"/api/games/?{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertIn(field, response.data)

    def test_filters_endpoint_lists_only_used_values(self):
        Genre.objects.create(slug="unused", name="Unused")
        data = self.client.get("/api/games/filters/").data
        self.assertNotIn("unused", [genre["slug"] for genre in data["genres"]])
        self.assertEqual(data["years"], [2022, 2020, 2019, 2018])
        indie = next(genre for genre in data["genres"] if genre["slug"] == "indie")
        self.assertEqual(indie["count"], 2)

    def test_stats(self):
        data = self.client.get("/api/games/stats/").data
        self.assertEqual((data["games"], data["reviews"], data["critics"]), (5, 6, 3))

    def test_page_size_parameter(self):
        response = self.client.get("/api/games/?page_size=2")
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["count"], 5)


RAWG_PAGE = [
    {
        "id": 3498,
        "slug": "grand-theft-auto-v",
        "name": "Grand Theft Auto V",
        "released": "2013-09-17",
        "background_image": "https://media.rawg.io/media/games/gta.jpg",
        "genres": [{"slug": "action", "name": "Action"}],
        "platforms": [{"platform": {"slug": "pc", "name": "PC"}}],
    },
    {
        "id": 4200,
        "slug": "portal-2",
        "name": "Portal 2",
        "released": "not-a-date",
        "background_image": None,
        "genres": [{"slug": "puzzle", "name": "Puzzle"}],
        "platforms": [],
    },
]


@override_settings(RAWG_API_KEY="test-key")
class RawgImportTests(TestCase):
    def run_import(self, results=RAWG_PAGE):
        with patch("games.rawg.RawgClient.list_games", return_value=results):
            call_command("import_rawg", stdout=StringIO())

    def test_repeated_import_does_not_duplicate(self):
        Genre.objects.create(slug="action", name="Экшен")
        self.run_import()
        self.run_import()

        self.assertEqual(Game.objects.count(), 2)
        gta = Game.objects.get(external_id="3498")
        self.assertEqual(gta.data_source, Game.DataSource.RAWG)
        self.assertEqual(gta.source_url, "https://rawg.io/games/grand-theft-auto-v")
        # Русское название жанра из справочника не перезаписывается английским из RAWG.
        self.assertEqual(list(gta.genres.values_list("name", flat=True)), ["Экшен"])
        self.assertIsNone(Game.objects.get(external_id="4200").release_date)

        runs = list(ImportRun.objects.order_by("started_at").values_list("status", "created_count", "updated_count"))
        self.assertEqual(runs, [("success", 2, 0), ("success", 0, 2)])

    def test_provider_failure_is_logged_and_catalog_survives(self):
        self.run_import()
        with patch("games.rawg.RawgClient.list_games", side_effect=RawgError("RAWG недоступен: timeout.")):
            with self.assertRaises(CommandError):
                call_command("import_rawg", stdout=StringIO())

        failed = ImportRun.objects.latest("started_at")
        self.assertEqual(failed.status, ImportRun.Status.FAILED)
        self.assertIn("timeout", failed.error)
        self.assertEqual(APIClient().get("/api/games/").data["count"], 2)

    @override_settings(RAWG_API_KEY="")
    def test_missing_api_key_is_reported(self):
        with self.assertRaisesMessage(CommandError, "RAWG_API_KEY"):
            call_command("import_rawg", stdout=StringIO())
        self.assertEqual(ImportRun.objects.get().status, ImportRun.Status.FAILED)


class SeedDemoTests(TestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_demo", stdout=StringIO())
        counts = (Game.objects.count(), Review.objects.count())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual((Game.objects.count(), Review.objects.count()), counts)
        self.assertGreaterEqual(counts[0], 20)
