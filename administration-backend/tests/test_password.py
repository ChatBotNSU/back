"""Unit tests for utils/password.py."""

import pytest
from unittest.mock import patch, MagicMock

from utils.password import verify_password, get_password_hash, password_hash


class TestVerifyPassword:
    """Tests for verify_password function."""

    def test_verify_password_correct(self):
        # Given
        plain_password = "test_password123"
        hashed = password_hash.hash(plain_password)

        # When
        result = verify_password(plain_password, hashed)

        # Then
        assert result is True

    def test_verify_password_incorrect(self):
        # Given
        plain_password = "test_password123"
        wrong_password = "wrong_password"
        hashed = password_hash.hash(plain_password)

        # When
        result = verify_password(wrong_password, hashed)

        # Then
        assert result is False

    def test_verify_password_empty(self):
        # Given
        hashed = password_hash.hash("some_password")

        # When
        result = verify_password("", hashed)

        # Then
        assert result is False


class TestGetPasswordHash:
    """Tests for get_password_hash function."""

    def test_get_password_hash_returns_string(self):
        # Given
        password = "test_password123"

        # When
        result = get_password_hash(password)

        # Then
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_password_hash_different_for_same_password(self):
        # Given
        password = "test_password123"

        # When
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Then - hashes should be different due to salt
        assert hash1 != hash2
        assert len(hash1) > 0
        assert len(hash2) > 0

    def test_get_password_hash_verify(self):
        # Given
        password = "test_password123"

        # When
        hashed = get_password_hash(password)
        result = password_hash.verify(password, hashed)

        # Then
        assert result is True
