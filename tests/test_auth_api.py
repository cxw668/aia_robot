from __future__ import annotations

import unittest
from unittest.mock import patch

from jose import jwt

from app.database import User
from tests.api_test_utils import FakeAsyncSession, auth_headers, create_test_client


class AuthApiTests(unittest.TestCase):
    def test_register_login_and_refresh_flow(self) -> None:
        db = FakeAsyncSession()

        with create_test_client(db) as client:
            register_response = client.post(
                "/auth/register",
                json={"username": "alice", "password": "abc12345"},
            )

            self.assertEqual(register_response.status_code, 200)
            register_payload = register_response.json()
            self.assertEqual(register_payload["username"], "alice")
            self.assertTrue(register_payload["token"])

            duplicate_response = client.post(
                "/auth/register",
                json={"username": "alice", "password": "abc12345"},
            )
            self.assertEqual(duplicate_response.status_code, 409)
            self.assertEqual(duplicate_response.json()["error"]["code"], "conflict")

            login_response = client.post(
                "/auth/login",
                json={"username": "alice", "password": "abc12345"},
            )
            self.assertEqual(login_response.status_code, 200)
            login_payload = login_response.json()
            self.assertEqual(login_payload["username"], "alice")
            self.assertTrue(login_payload["token"])

            refresh_response = client.post(
                "/auth/refresh",
                headers=auth_headers(login_payload["token"]),
            )
            self.assertEqual(refresh_response.status_code, 200)
            refresh_payload = refresh_response.json()
            self.assertEqual(refresh_payload["username"], "alice")
            self.assertTrue(refresh_payload["token"])

    def test_auth_returns_uniform_errors_for_weak_password_and_invalid_login(self) -> None:
        db = FakeAsyncSession()

        with create_test_client(db) as client:
            weak_password_response = client.post(
                "/auth/register",
                json={"username": "bob", "password": "short1"},
            )
            self.assertEqual(weak_password_response.status_code, 400)
            weak_password_error = weak_password_response.json()["error"]
            self.assertEqual(weak_password_error["code"], "bad_request")
            self.assertEqual(
                weak_password_error["message"],
                "Password must be at least 8 characters long",
            )

            invalid_login_response = client.post(
                "/auth/login",
                json={"username": "bob", "password": "abc12345"},
            )
            self.assertEqual(invalid_login_response.status_code, 401)
            invalid_login_error = invalid_login_response.json()["error"]
            self.assertEqual(invalid_login_error["code"], "unauthorized")
            self.assertEqual(invalid_login_error["message"], "Invalid credentials")

    def test_refresh_accepts_token_signed_with_previous_secret(self) -> None:
        db = FakeAsyncSession()
        db.add(User(id=9, username="legacy", password_hash="hashed"))
        legacy_token = jwt.encode(
            {"sub": "legacy", "uid": 9},
            "previous-secret",
            algorithm="HS256",
        )

        with patch("app.routers.auth.JWT_SECRET_KEYS", ("active-secret", "previous-secret")):
            with create_test_client(db) as client:
                refresh_response = client.post(
                    "/auth/refresh",
                    headers=auth_headers(legacy_token),
                )

        self.assertEqual(refresh_response.status_code, 200)
        refresh_payload = refresh_response.json()
        self.assertEqual(refresh_payload["username"], "legacy")
        self.assertTrue(refresh_payload["token"])
