"""Tests for AuthConfig typed configuration."""

import os
from unittest.mock import patch

import pytest

from app.gateway.auth.config import AuthConfig


def test_auth_config_defaults():
    config = AuthConfig(jwt_secret="test-secret-key-123")
    assert config.env == "production"
    assert config.cookie_secure is True
    assert config.token_expiry_days == 7


def test_auth_config_dev_allows_insecure_cookie():
    config = AuthConfig(jwt_secret="test-secret", env="development", cookie_secure=False)
    assert config.cookie_secure is False


def test_auth_config_prod_rejects_insecure_cookie():
    with pytest.raises(ValueError, match="cookie_secure must be True in production"):
        AuthConfig(jwt_secret="test-secret", env="production", cookie_secure=False)


def test_auth_config_from_env():
    env = {
        "AUTH_JWT_SECRET": "test-jwt-secret-from-env",
        "ENV": "development",
        "AUTH_COOKIE_SECURE": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        import app.gateway.auth.config as cfg

        old = cfg._auth_config
        cfg._auth_config = None
        try:
            config = cfg.get_auth_config()
            assert config.jwt_secret == "test-jwt-secret-from-env"
            assert config.env == "development"
            assert config.cookie_secure is False
        finally:
            cfg._auth_config = old
