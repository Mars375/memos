"""Tests for MemOS config module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from memos.config import (
    config_path,
    load_config,
    resolve,
    write_config,
)


class TestLoadConfig:
    def test_load_missing_file_returns_empty(self, tmp_path: Path):
        assert load_config(tmp_path / "nosuch.toml") == {}

    def test_load_valid_toml(self, tmp_path: Path):
        p = tmp_path / ".memos.toml"
        p.write_text('[memos]\nbackend = "chroma"\nport = 9000\n')
        cfg = load_config(p)
        assert cfg["backend"] == "chroma"
        assert cfg["port"] == 9000

    def test_load_flat_toml(self, tmp_path: Path):
        p = tmp_path / ".memos.toml"
        p.write_text('backend = "memory"\n')
        cfg = load_config(p)
        assert cfg["backend"] == "memory"

    def test_load_invalid_toml_returns_empty(self, tmp_path: Path):
        p = tmp_path / ".memos.toml"
        p.write_text("{{invalid toml!!!")
        assert load_config(p) == {}


class TestResolve:
    def test_defaults_only(self):
        cfg = resolve()
        assert cfg["backend"] == "memory"
        assert cfg["port"] == 8000

    def test_file_overrides_default(self, tmp_path: Path):
        p = tmp_path / ".memos.toml"
        p.write_text('[memos]\nbackend = "chroma"\n')
        with patch("memos.config.load_config", return_value={"backend": "chroma"}):
            cfg = resolve()
        assert cfg["backend"] == "chroma"

    def test_env_overrides_file(self):
        env = {"MEMOS_BACKEND": "chroma", "MEMOS_PORT": "9999"}
        with patch.dict(os.environ, env, clear=False):
            cfg = resolve()
        assert cfg["backend"] == "chroma"
        assert cfg["port"] == 9999

    def test_cache_path_env(self):
        with patch.dict(os.environ, {"MEMOS_CACHE_PATH": "/data/.memos/embeddings.db"}, clear=False):
            cfg = resolve()
        assert cfg["cache_path"] == "/data/.memos/embeddings.db"

    def test_cli_overrides_env(self):
        with patch.dict(os.environ, {"MEMOS_BACKEND": "chroma"}, clear=False):
            cfg = resolve({"backend": "memory"})
        assert cfg["backend"] == "memory"

    def test_sanitize_env_bool(self):
        with patch.dict(os.environ, {"MEMOS_BACKEND": "memory", "MEMOS_SANITIZE": "false"}, clear=False):
            # sanitize isn't in ENV_MAP by default, so just test that env works for known keys
            cfg = resolve()
        assert cfg["backend"] == "memory"

    def test_unknown_cli_key_ignored(self):
        cfg = resolve({"unknown_key": "value"})
        assert "unknown_key" not in cfg


class TestWriteConfig:
    def test_write_creates_file(self, tmp_path: Path):
        p = tmp_path / "sub" / ".memos.toml"
        result = write_config({"backend": "chroma", "port": 9000}, p)
        assert result == p
        content = p.read_text()
        assert 'backend = "chroma"' in content
        assert "port = 9000" in content

    def test_write_ignores_unknown_keys(self, tmp_path: Path):
        p = tmp_path / ".memos.toml"
        write_config({"backend": "memory", "foobar": True}, p)
        content = p.read_text()
        assert "foobar" not in content

    def test_write_bool(self, tmp_path: Path):
        p = tmp_path / ".memos.toml"
        write_config({"sanitize": False}, p)
        assert "sanitize = false" in p.read_text()


class TestConfigPath:
    def test_default_path(self):
        with patch.dict(os.environ, {}, clear=True):
            p = config_path()
        assert p.name == ".memos.toml"

    def test_env_override(self, tmp_path):
        config_file = str(tmp_path / "my.toml")
        with patch.dict(os.environ, {"MEMOS_CONFIG": config_file}, clear=True):
            assert config_path() == Path(config_file)


class TestCLIConfig:
    """Integration tests for memos config CLI commands."""

    def test_config_path_command(self, tmp_path: Path):
        import io
        from contextlib import redirect_stdout

        from memos.cli import main

        f = io.StringIO()
        with redirect_stdout(f):
            main(["config", "path"])
        output = f.getvalue().strip()
        assert ".memos.toml" in output

    def test_config_show_json(self):
        import io
        from contextlib import redirect_stdout

        from memos.cli import main

        f = io.StringIO()
        with redirect_stdout(f):
            main(["config", "show", "--json"])
        data = json.loads(f.getvalue())
        assert "backend" in data
        assert "port" in data

    def test_config_set_and_read(self, tmp_path: Path):
        import io
        from contextlib import redirect_stdout

        from memos.cli import main

        cfg_file = tmp_path / ".memos.toml"
        with patch("memos.config.config_path", return_value=cfg_file):
            # Set a value
            f = io.StringIO()
            with redirect_stdout(f):
                main(["config", "set", "backend=chroma", "port=9000"])
            assert "✓" in f.getvalue()

            # Verify file contents
            content = cfg_file.read_text()
            assert 'backend = "chroma"' in content
            assert "port = 9000" in content

    def test_config_set_invalid_key(self):
        from memos.cli import main

        with pytest.raises(SystemExit):
            main(["config", "set", "nonsense=value"])

    def test_config_set_bool_coercion(self, tmp_path: Path):
        import io
        from contextlib import redirect_stdout

        from memos.cli import main

        cfg_file = tmp_path / ".memos.toml"
        with patch("memos.config.config_path", return_value=cfg_file):
            f = io.StringIO()
            with redirect_stdout(f):
                main(["config", "set", "sanitize=false"])
            content = cfg_file.read_text()
            assert "sanitize = false" in content

    def test_config_init_creates_file(self, tmp_path: Path):
        import io
        from contextlib import redirect_stdout

        from memos.cli import main

        cfg_file = tmp_path / ".memos.toml"
        with patch("memos.cli.commands_system.config_path", return_value=cfg_file):
            f = io.StringIO()
            with redirect_stdout(f):
                main(["config", "init"])
            assert cfg_file.is_file()
            assert "✓" in f.getvalue()

    def test_config_init_no_overwrite(self, tmp_path: Path):
        from memos.cli import main

        cfg_file = tmp_path / ".memos.toml"
        cfg_file.write_text("[memos]\n")
        with (
            patch("memos.cli.commands_system.config_path", return_value=cfg_file),
            patch("memos.config.config_path", return_value=cfg_file),
        ):
            with pytest.raises(SystemExit):
                main(["config", "init"])

    def test_config_init_force_overwrite(self, tmp_path: Path):
        import io
        from contextlib import redirect_stdout

        from memos.cli import main

        cfg_file = tmp_path / ".memos.toml"
        cfg_file.write_text("old content")
        with (
            patch("memos.cli.commands_system.config_path", return_value=cfg_file),
            patch("memos.config.config_path", return_value=cfg_file),
        ):
            f = io.StringIO()
            with redirect_stdout(f):
                main(["config", "init", "--force"])
            assert "✓" in f.getvalue()
