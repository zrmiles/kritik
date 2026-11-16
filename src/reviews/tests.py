from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from games.models import Game

from .models import Review
from .serializers import ReviewSerializer

User = get_user_model()
TEXT = "Достаточно длинный текст рецензии."
EXAMPLE_TEXT = "Душная, но гениальная игра про чуму и выбор."


class ReviewCrudTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(slug="hades", title="Hades")
        self.author = User.objects.create_user("author", password="x", display_name="Автор")
        self.other = User.objects.create_user("other", password="x")
        self.client = self.client_for(self.author)

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create(self, client=None, **data):
        payload = {"game_id": self.game.pk, "score": 8, "text": TEXT, **data}
        return (client or self.client).post("/api/reviews/", payload, format="json")

    def game_stats(self):
        data = APIClient().get(f"/api/games/{self.game.pk}/").data
        rating = data["average_rating"]
        return (float(rating) if rating is not None else None), data["review_count"]

    def test_anonymous_cannot_create(self):
        self.assertEqual(self.create(client=APIClient()).status_code, 401)

    def test_full_crud_recalculates_average(self):
        self.assertEqual(self.game_stats(), (None, 0))

        mine = self.create(score=8)
        self.assertEqual(mine.status_code, 201)
        self.assertTrue(mine.data["is_owner"])
        self.create(client=self.client_for(self.other), score=4)
        self.assertEqual(self.game_stats(), (6.0, 2))

        updated = self.client.patch(f"/api/reviews/{mine.data['id']}/", {"score": 10}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.game_stats(), (7.0, 2))

        self.assertEqual(self.client.delete(f"/api/reviews/{mine.data['id']}/").status_code, 204)
        self.assertEqual(self.game_stats(), (4.0, 1))

    def test_one_review_per_game(self):
        self.create()
        response = self.create()
        self.assertEqual(response.status_code, 400)
        self.assertIn("game_id", response.data)

    def test_one_review_per_game_race(self):
        # US-5: второй одновременный запрос проходит validate() раньше, чем первый сохранён.
        # Ответ должен быть тем же 400, что и при обычном повторе, а не 500.
        self.create()
        with mock.patch.object(ReviewSerializer, "validate", lambda serializer, attrs: attrs):
            response = self.create(score=3)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"game_id": ["Вы уже оставили рецензию на эту игру."]})
        self.assertEqual(Review.objects.get().score, 8)

    def test_validation(self):
        self.assertEqual(self.create(score=0).status_code, 400)
        self.assertEqual(self.create(score=11).status_code, 400)
        self.assertEqual(self.create(text="Коротко").status_code, 400)
        self.assertEqual(self.create(text="я" * 501).status_code, 400)
        self.assertEqual(self.create(game_id=999).status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_cannot_move_review_to_another_game(self):
        review = self.create().data
        other_game = Game.objects.create(slug="celeste", title="Celeste")
        response = self.client.patch(f"/api/reviews/{review['id']}/", {"game_id": other_game.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_foreign_review_is_read_only(self):
        review = self.create().data
        stranger = self.client_for(self.other)
        self.assertEqual(stranger.patch(f"/api/reviews/{review['id']}/", {"score": 1}, format="json").status_code, 404)
        self.assertEqual(stranger.delete(f"/api/reviews/{review['id']}/").status_code, 404)
        self.assertEqual(Review.objects.get().score, 8)

        public = stranger.get(f"/api/games/{self.game.pk}/reviews/").data
        self.assertEqual(public[0]["author"], "Автор")
        self.assertFalse(public[0]["is_owner"])

    def test_my_reviews(self):
        self.create()
        Review.objects.create(author=self.other, game=self.game, score=3, text=TEXT)
        mine = self.client.get("/api/me/reviews/").data
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["game"]["title"], "Hades")

    def test_score_distribution(self):
        self.create(score=8)
        self.create(client=self.client_for(self.other), score=8)
        distribution = APIClient().get(f"/api/games/{self.game.pk}/").data["score_distribution"]
        self.assertEqual(distribution, [0, 0, 0, 0, 0, 0, 0, 2, 0, 0])


class ReviewContractTests(TestCase):
    """ЛР 4: проверка контракта POST /api/reviews/ (docs/interface-contract.md, FR-4, US-5)."""

    def setUp(self):
        # Состояние из раздела 3 контракта: у игры уже 3 рецензии с оценками 3, 9 и 10, средняя 7.33.
        self.game = Game.objects.create(slug="pathologic-2", title="Мор (Pathologic 2)")
        for index, score in enumerate((3, 9, 10)):
            critic = User.objects.create_user(f"critic{index}", password="x")
            Review.objects.create(author=critic, game=self.game, score=score, text=TEXT)
        self.anna = User.objects.create_user("anna", password="x", display_name="Анна")
        self.client = APIClient()
        self.client.force_authenticate(self.anna)

    def publish(self, game=None, **data):
        payload = {"game_id": (game or self.game).pk, "score": 9, "text": EXAMPLE_TEXT, **data}
        return self.client.post("/api/reviews/", payload, format="json")

    def game_card(self):
        return APIClient().get(f"/api/games/{self.game.pk}/").data

    def test_contract_example_1_publish_review(self):
        """Обычный случай: пример 1 контракта — 201, тело рецензии и пересчёт оценки сообщества."""
        response = self.publish()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["author"], "Анна")
        self.assertIs(response.data["is_owner"], True)
        self.assertEqual(response.data["score"], 9)
        self.assertEqual(response.data["text"], EXAMPLE_TEXT)
        self.assertNotIn("game_id", response.data)

        card = self.game_card()
        self.assertEqual(card["average_rating"], "7.80")
        self.assertEqual(card["review_count"], 4)
        self.assertEqual(card["score_distribution"], [0, 0, 1, 0, 0, 0, 0, 0, 2, 1])

    def test_contract_example_2_second_review_is_rejected(self):
        """Ошибка: пример 2 контракта — повторная рецензия даёт 400 и ничего не меняет."""
        self.publish()
        response = self.publish(score=8, text="Вторая попытка написать рецензию на Мор.")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"game_id": ["Вы уже оставили рецензию на эту игру."]})
        card = self.game_card()
        self.assertEqual(card["average_rating"], "7.75")
        self.assertEqual(card["review_count"], 4)
        self.assertEqual(Review.objects.get(author=self.anna).score, 9)

    def test_score_boundaries(self):
        """Граничные значения оценки: 1 и 10 принимаются, 0 и 11 — нет."""
        low = Game.objects.create(slug="low", title="Low")
        high = Game.objects.create(slug="high", title="High")
        self.assertEqual(self.publish(game=low, score=1).data["score"], 1)
        self.assertEqual(self.publish(game=high, score=10).data["score"], 10)

        too_low = self.publish(score=0)
        self.assertEqual(too_low.status_code, 400)
        self.assertEqual(too_low.data, {"score": ["Убедитесь, что это значение больше либо равно 1."]})
        too_high = self.publish(score=11)
        self.assertEqual(too_high.status_code, 400)
        self.assertEqual(too_high.data, {"score": ["Убедитесь, что это значение меньше либо равно 10."]})
        self.assertFalse(Review.objects.filter(author=self.anna, game=self.game).exists())

    def test_text_length_boundaries(self):
        """Граничные значения длины текста: 10 и 500 символов — да, 9 и 501 — нет; пробелы по краям не в счёт."""
        short_ok = Game.objects.create(slug="short", title="Short")
        long_ok = Game.objects.create(slug="long", title="Long")
        self.assertEqual(self.publish(game=short_ok, text="я" * 10).status_code, 201)
        self.assertEqual(self.publish(game=long_ok, text="я" * 500).status_code, 201)

        self.assertEqual(
            self.publish(text="я" * 9).data,
            {"text": ["Убедитесь, что это значение содержит не менее 10 символов (сейчас 9)."]},
        )
        self.assertEqual(
            self.publish(text="я" * 501).data,
            {"text": ["Убедитесь, что это значение содержит не более 500 символов (сейчас 501)."]},
        )
        self.assertEqual(
            self.publish(text="   ок   ").data,
            {"text": ["Убедитесь, что это значение содержит не менее 10 символов (сейчас 2)."]},
        )
        self.assertEqual(self.game_card()["review_count"], 3)
