from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from games.models import Game

from .models import Review

User = get_user_model()
TEXT = "Достаточно длинный текст рецензии."


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
