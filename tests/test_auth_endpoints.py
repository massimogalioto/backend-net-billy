import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import auth_endpoint
from auth_service import CurrentUser


USER = CurrentUser("user-a", "demo@example.com", "Demo", "tenant-a", "Net Billy Demo", "START", "Start")


class AuthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(auth_endpoint.router)
        self.client = TestClient(self.app)

    def test_login_sets_http_only_session_cookie(self):
        with patch.object(auth_endpoint, "login", return_value=(USER, "opaque-session-token")):
            response = self.client.post("/auth/login", json={"email": USER.email, "password": "correct-password"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant"]["id"], "tenant-a")
        self.assertNotIn("opaque-session-token", response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=none", response.headers["set-cookie"])

    def test_invalid_login_is_generic_401(self):
        with patch.object(auth_endpoint, "login", side_effect=HTTPException(401, "Email o password non validi")):
            response = self.client.post("/auth/login", json={"email": "missing@example.com", "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Email o password non validi")

    def test_register_returns_free_user_and_sets_session_cookie(self):
        free_user = CurrentUser("user-free", "new@example.com", "Mario", "tenant-free", "Nuova attività", "FREE", "Free")
        with patch.object(auth_endpoint, "register", return_value=(free_user, "opaque-registration-token")):
            response = self.client.post("/auth/register", json={"company_name": "Nuova attività", "name": "Mario", "email": "NEW@EXAMPLE.COM", "password": "password-lunga"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["plan"]["code"], "FREE")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertNotIn("opaque-registration-token", response.text)

    def test_register_rejects_short_password_and_duplicate_email(self):
        short = self.client.post("/auth/register", json={"company_name": "Nuova", "name": "Mario", "email": "new@example.com", "password": "corta"})
        self.assertEqual(short.status_code, 422)
        with patch.object(auth_endpoint, "register", side_effect=HTTPException(409, "Email già registrata")):
            duplicate = self.client.post("/auth/register", json={"company_name": "Nuova", "name": "Mario", "email": "new@example.com", "password": "password-lunga"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"], "Email già registrata")

    def test_me_requires_authenticated_user_and_never_returns_hash(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.app.dependency_overrides[auth_endpoint.current_user] = lambda: USER
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plan"]["code"], "START")
        self.assertNotIn("password_hash", response.text)


if __name__ == "__main__":
    unittest.main()
