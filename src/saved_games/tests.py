from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from games.models import Game

User = get_user_model()


class SavedGamesTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(slug="hades", title="Hades")
        self.other_game = Game.objects.create(slug="celeste", title="Celeste")
        self.user = User.objects.create_user("owner", password="x")
        self.stranger = User.objects.create_user("stranger", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get("/api/me/saved-games/").status_code, 401)

    def test_add_list_and_remove(self):
        response = self.client.post("/api/me/saved-games/", {"game_id": self.game.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["game"]["is_saved"])

        listed = self.client.get("/api/me/saved-games/").data
        self.assertEqual([item["game"]["id"] for item in listed], [self.game.pk])

        catalog = {g["id"]: g["is_saved"] for g in self.client.get("/api/games/").data["results"]}
        self.assertEqual(catalog, {self.game.pk: True, self.other_game.pk: False})

        self.assertEqual(self.client.delete(f"/api/me/saved-games/{self.game.pk}/").status_code, 204)
        self.assertEqual(self.client.get("/api/me/saved-games/").data, [])

    def test_duplicate_is_rejected(self):
        self.client.post("/api/me/saved-games/", {"game_id": self.game.pk}, format="json")
        response = self.client.post("/api/me/saved-games/", {"game_id": self.game.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unknown_game_is_rejected(self):
        response = self.client.post("/api/me/saved-games/", {"game_id": 999}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_lists_are_private(self):
        self.client.post("/api/me/saved-games/", {"game_id": self.game.pk}, format="json")
        stranger = APIClient()
        stranger.force_authenticate(self.stranger)
        self.assertEqual(stranger.get("/api/me/saved-games/").data, [])
        self.assertEqual(stranger.delete(f"/api/me/saved-games/{self.game.pk}/").status_code, 404)
        self.assertEqual(len(self.client.get("/api/me/saved-games/").data), 1)
