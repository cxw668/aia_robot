from __future__ import annotations

import unittest
from unittest.mock import patch

from app.routers.auth import _create_token, _validate_password_strength, get_username_from_token
from app.database import User


class AuthHelperTests(unittest.TestCase):
    def test_validate_password_strength_accepts_letter_and_number(self) -> None:
        self.assertIsNone(_validate_password_strength("abc12345"))

    def test_validate_password_strength_rejects_short_password(self) -> None:
        self.assertEqual(
            _validate_password_strength("a1b2"),
            "Password must be at least 8 characters long",
        )

    def test_validate_password_strength_rejects_password_without_letter(self) -> None:
        self.assertEqual(
            _validate_password_strength("12345678"),
            "Password must include at least one letter",
        )

    def test_validate_password_strength_rejects_password_without_number(self) -> None:
        self.assertEqual(
            _validate_password_strength("abcdefgh"),
            "Password must include at least one number",
        )

    @patch("app.routers.auth.JWT_SECRET_KEY", "unit-test-secret")
    def test_create_token_can_be_read_back(self) -> None:
        user = User(id=7, username="tester", password_hash="hashed")
        token = _create_token(user)
        self.assertEqual(get_username_from_token(token), "tester")
