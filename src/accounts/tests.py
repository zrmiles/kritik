from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()
PASSWORD = "Str0ng-pass-phrase"


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def register(self, **overrides):
        data = {"username": "player", "display_name": "Игрок", "password": PASSWORD, "password_confirm": PASSWORD}
        return self.client.post("/api/auth/register/", {**data, **overrides}, format="json")

    def test_register_returns_access_token_and_sets_refresh_cookie(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["user"]["public_name"], "Игрок")
        cookie = response.cookies[settings.JWT_REFRESH_COOKIE]
        self.assertTrue(cookie["httponly"])

    def test_register_rejects_mismatched_passwords(self):
        response = self.register(password_confirm="another-pass-123")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirm", response.data)

    def test_register_rejects_duplicate_username(self):
        self.register()
        self.assertEqual(self.register().status_code, 400)

    def test_login_with_wrong_password_is_rejected(self):
        User.objects.create_user("player", password=PASSWORD)
        response = self.client.post("/api/auth/login/", {"username": "player", "password": "wrong"}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "invalid_credentials")

    def test_refresh_restores_session_and_logout_revokes_it(self):
        User.objects.create_user("player", password=PASSWORD)
        login = self.client.post("/api/auth/login/", {"username": "player", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 200)

        refreshed = self.client.post("/api/auth/refresh/")
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").data["username"], "player")

        old_refresh = self.client.cookies[settings.JWT_REFRESH_COOKIE].value
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.client.cookies[settings.JWT_REFRESH_COOKIE] = old_refresh
        self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 401)

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_login_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post("/api/auth/login/", {"username": "x", "password": "y"}, format="json")
        self.assertEqual(response.status_code, 403)
