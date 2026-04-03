"""Tests for AuthConfig typed configuration."""

import os
from unittest.mock import patch

import pytest

from app.gateway.auth.config import AuthConfig


def test_auth_config_defaults():
    config = AuthConfig(jwt_secret="test-secret-key-123")
    assert config.token_expiry_days == 7


def test_auth_config_token_expiry_range():
    AuthConfig(jwt_secret="s", token_expiry_days=1)
    AuthConfig(jwt_secret="s", token_expiry_days=30)
    with pytest.raises(Exception):
        AuthConfig(jwt_secret="s", token_expiry_days=0)
    with pytest.raises(Exception):
        AuthConfig(jwt_secret="s", token_expiry_days=31)


def test_auth_config_from_env():
    env = {"AUTH_JWT_SECRET": "test-jwt-secret-from-env"}
    with patch.dict(os.environ, env, clear=False):
        import app.gateway.auth.config as cfg

        old = cfg._auth_config
        cfg._auth_config = None
        try:
            config = cfg.get_auth_config()
            assert config.jwt_secret == "test-jwt-secret-from-env"
        finally:
            cfg._auth_config = old


def test_auth_config_missing_secret_raises():
    import app.gateway.auth.config as cfg

    old = cfg._auth_config
    cfg._auth_config = None
    try:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("AUTH_JWT_SECRET", None)
            with pytest.raises(ValueError, match="AUTH_JWT_SECRET"):
                cfg.get_auth_config()
    finally:
        cfg._auth_config = old
