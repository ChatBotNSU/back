import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from config.config import load_config, get_config, AppConfig


class TestLoadConfig:
    """Tests for load_config function"""

    def test_load_config_success(self, tmp_path):
        """Test successful config loading"""
        config_data = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "IOStream": {
                    "stream_requests": "requests",
                    "stream_responses": "responses",
                    "group": "test-group",
                    "consumer": "test-consumer"
                }
            },
            "s3": {
                "host": "localhost",
                "port": 9000
            },
            "services": {
                "py_runner": {
                    "url": "http://localhost:8080/run",
                    "timeout_seconds": 15
                }
            }
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with patch.dict(os.environ, {
            "MINIO_ROOT_USER": "test-user",
            "MINIO_ROOT_PASSWORD": "test-password"
        }):
            config = load_config(config_file)

            assert config.redis.host == "localhost"
            assert config.redis.port == 6379
            assert config.s3.host == "localhost"
            assert config.s3.port == 9000
            assert config.s3.user == "test-user"
            assert config.s3.password == "test-password"
            assert config.services.py_runner.url == "http://localhost:8080/run"

    def test_load_config_file_not_found(self):
        """Test loading non-existent config file"""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.json")

    def test_load_config_missing_env_user(self, tmp_path):
        """Test loading config without MINIO_ROOT_USER"""
        config_data = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "IOStream": {
                    "stream_requests": "requests",
                    "stream_responses": "responses",
                    "group": "test-group",
                    "consumer": "test-consumer"
                }
            },
            "s3": {
                "host": "localhost",
                "port": 9000
            },
            "services": {
                "py_runner": {
                    "url": "http://localhost:8080/run"
                }
            }
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        # Clear env and set only password
        with patch.dict(os.environ, {"MINIO_ROOT_PASSWORD": "test-password"}, clear=True):
            with pytest.raises(Exception):
                load_config(config_file)

    def test_load_config_missing_env_password(self, tmp_path):
        """Test loading config without MINIO_ROOT_PASSWORD"""
        config_data = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "IOStream": {
                    "stream_requests": "requests",
                    "stream_responses": "responses",
                    "group": "test-group",
                    "consumer": "test-consumer"
                }
            },
            "s3": {
                "host": "localhost",
                "port": 9000
            },
            "services": {
                "py_runner": {
                    "url": "http://localhost:8080/run"
                }
            }
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        # Clear env and set only user
        with patch.dict(os.environ, {"MINIO_ROOT_USER": "test-user"}, clear=True):
            with pytest.raises(Exception):
                load_config(config_file)

    def test_load_config_invalid_json(self, tmp_path):
        """Test loading invalid JSON file"""
        config_file = tmp_path / "config.json"
        config_file.write_text("invalid json {")

        with pytest.raises(json.JSONDecodeError):
            load_config(config_file)


class TestGetConfig:
    """Tests for get_config function"""

    def test_get_config_default_path(self, tmp_path):
        """Test get_config with default path"""
        config_data = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "IOStream": {
                    "stream_requests": "requests",
                    "stream_responses": "responses",
                    "group": "test-group",
                    "consumer": "test-consumer"
                }
            },
            "s3": {
                "host": "localhost",
                "port": 9000
            },
            "services": {
                "py_runner": {
                    "url": "http://localhost:8080/run"
                }
            }
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with patch.dict(os.environ, {
            "MINIO_ROOT_USER": "test-user",
            "MINIO_ROOT_PASSWORD": "test-password"
        }):
            # Reset cached config
            import config.config as config_module
            config_module._config = None

            config = get_config(config_file)
            assert config.redis.host == "localhost"

    def test_get_config_caching(self, tmp_path):
        """Test that get_config caches the result"""
        config_data = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "IOStream": {
                    "stream_requests": "requests",
                    "stream_responses": "responses",
                    "group": "test-group",
                    "consumer": "test-consumer"
                }
            },
            "s3": {
                "host": "localhost",
                "port": 9000
            },
            "services": {
                "py_runner": {
                    "url": "http://localhost:8080/run"
                }
            }
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        with patch.dict(os.environ, {
            "MINIO_ROOT_USER": "test-user",
            "MINIO_ROOT_PASSWORD": "test-password"
        }):
            # Reset cached config
            import config.config as config_module
            config_module._config = None

            config1 = get_config(config_file)
            config2 = get_config(config_file)
            assert config1 is config2
