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

    def test_me_requires_authenticated_user_and_never_returns_hash(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.app.dependency_overrides[auth_endpoint.current_user] = lambda: USER
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plan"]["code"], "START")
        self.assertNotIn("password_hash", response.text)


if __name__ == "__main__":
    unittest.main()
