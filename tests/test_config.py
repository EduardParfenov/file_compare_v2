"""Тесты для модуля конфигурации `config.py`.

Проверяются:
- приоритет источников: встроенные дефолты < окружение оболочки < `.env`;
- путь к `.env` (корень проекта, без поиска вверх по дереву) и независимость
  конфигурации от текущего рабочего каталога;
- отсутствие побочных эффектов: чтение `.env` не меняет `os.environ`;
- граничные случаи разбора `.env` (пустое значение, ключ без `=`).

Тесты не используют `reload(config)` и не зависят от наличия локального
`.env` в корне проекта: значения передаются явно.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

import config


# ---------------------------------------------------------------------------
# Дефолты и значения из окружения
# ---------------------------------------------------------------------------


def test_defaults_applied_when_nothing_configured():
    """При отсутствии переменных применяются встроенные дефолты."""
    settings = config.Settings.from_env({})
    assert settings.VLLM_API_URL == "http://localhost:8000/v1"
    assert settings.VLLM_MODEL_NAME == "qwen3-vl-8b"
    assert settings.VLLM_API_KEY == ""
    assert settings.FASTAPI_HOST == "0.0.0.0"
    assert settings.FASTAPI_PORT == 8000
    assert settings.CORS_ORIGINS == "*"


def test_shell_values_used_when_env_file_absent(tmp_path):
    """Значения из окружения оболочки используются, если файла `.env` нет."""
    values = config.read_environment(
        env_file=tmp_path / ".env",
        base={"VLLM_API_URL": "http://from-shell:9000/v1"},
    )
    assert values["VLLM_API_URL"] == "http://from-shell:9000/v1"


def test_env_file_values_override_shell_values(tmp_path):
    """Файл `.env` перекрывает переменные окружения оболочки."""
    env_file = tmp_path / ".env"
    env_file.write_text("VLLM_API_URL=http://from-dotenv:9000/v1\n", encoding="utf-8")

    values = config.read_environment(
        env_file=env_file,
        base={"VLLM_API_URL": "http://from-shell:9000/v1"},
    )
    assert values["VLLM_API_URL"] == "http://from-dotenv:9000/v1"


def test_env_file_values_override_defaults(tmp_path):
    """Значения из `.env` используются вместо встроенных дефолтов."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VLLM_API_URL=http://dotenv:9000/v1\n"
        "VLLM_MODEL_NAME=dotenv-model\n"
        "VLLM_API_KEY=dotenv-key\n"
        "FASTAPI_HOST=127.0.0.1\n"
        "FASTAPI_PORT=9000\n"
        "CORS_ORIGINS=http://dotenv.local\n",
        encoding="utf-8",
    )

    settings = config.Settings.from_env(config.read_environment(env_file=env_file, base={}))
    assert settings.VLLM_API_URL == "http://dotenv:9000/v1"
    assert settings.VLLM_MODEL_NAME == "dotenv-model"
    assert settings.VLLM_API_KEY == "dotenv-key"
    assert settings.FASTAPI_HOST == "127.0.0.1"
    assert settings.FASTAPI_PORT == 9000
    assert isinstance(settings.FASTAPI_PORT, int)
    assert settings.CORS_ORIGINS == "http://dotenv.local"


def test_empty_value_in_env_file_overrides_shell_value(tmp_path):
    """Пустое значение `KEY=` перекрывает значение окружения оболочки."""
    env_file = tmp_path / ".env"
    env_file.write_text("VLLM_API_KEY=\n", encoding="utf-8")

    values = config.read_environment(
        env_file=env_file,
        base={"VLLM_API_KEY": "shell-key"},
    )
    assert values["VLLM_API_KEY"] == ""


def test_key_without_equals_is_ignored(tmp_path):
    """Ключ без знака `=` не затирает значение окружения оболочки."""
    env_file = tmp_path / ".env"
    env_file.write_text("VLLM_API_KEY\n", encoding="utf-8")

    values = config.read_environment(
        env_file=env_file,
        base={"VLLM_API_KEY": "shell-key"},
    )
    assert values["VLLM_API_KEY"] == "shell-key"


def test_invalid_port_falls_back_to_default():
    """Некорректный порт не ломает загрузку конфигурации."""
    settings = config.Settings.from_env({"FASTAPI_PORT": "not-a-number"})
    assert settings.FASTAPI_PORT == 8000


# ---------------------------------------------------------------------------
# Путь к .env и независимость от рабочего каталога
# ---------------------------------------------------------------------------


def test_env_file_path_points_to_project_root():
    """Путь к `.env` выводится от расположения модуля `config`."""
    assert config.ENV_FILE == Path(config.__file__).resolve().parent / ".env"


def test_env_file_in_parent_directory_is_not_used(tmp_path):
    """`.env` из родительской директории не подхватывается (нет поиска вверх)."""
    (tmp_path / ".env").write_text("VLLM_API_URL=http://parent:9000/v1\n", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()

    values = config.read_environment(env_file=subdir / ".env", base={})
    assert "VLLM_API_URL" not in values


def test_config_does_not_depend_on_current_working_directory(tmp_path, monkeypatch):
    """Результат чтения конфигурации не зависит от текущего каталога."""
    from_project_root = config.read_environment()

    monkeypatch.chdir(tmp_path)
    from_tmp_dir = config.read_environment()

    assert from_tmp_dir == from_project_root


def test_default_env_file_is_read_when_present():
    """По умолчанию читается файл `.env` рядом с модулем `config`."""
    values = config.read_environment()
    if not config.ENV_FILE.is_file():
        return
    for key, value in dotenv_values(config.ENV_FILE).items():
        if value is None:
            continue
        assert values[key] == value


# ---------------------------------------------------------------------------
# Отсутствие побочных эффектов
# ---------------------------------------------------------------------------


def test_read_environment_does_not_mutate_os_environ(tmp_path, monkeypatch):
    """Чтение `.env` не записывает значения в окружение процесса."""
    env_file = tmp_path / ".env"
    env_file.write_text("VLLM_API_URL=http://from-dotenv:9000/v1\n", encoding="utf-8")

    monkeypatch.setenv("VLLM_API_URL", "http://from-shell:9000/v1")
    monkeypatch.delenv("VLLM_MODEL_NAME", raising=False)

    values = config.read_environment(env_file=env_file)

    assert values["VLLM_API_URL"] == "http://from-dotenv:9000/v1"
    assert os.environ["VLLM_API_URL"] == "http://from-shell:9000/v1"
    assert "VLLM_MODEL_NAME" not in os.environ


def test_module_level_settings_built_from_read_environment():
    """Экземпляр `settings` собран той же чистой функцией, что проверяется выше."""
    assert config.settings == config.Settings.from_env(config.read_environment())


def test_module_level_settings_expose_expected_fields():
    """Публичные настройки доступны и имеют корректные типы."""
    assert isinstance(config.settings.VLLM_API_URL, str)
    assert isinstance(config.settings.VLLM_MODEL_NAME, str)
    assert isinstance(config.settings.VLLM_API_KEY, str)
    assert isinstance(config.settings.FASTAPI_HOST, str)
    assert isinstance(config.settings.FASTAPI_PORT, int)
    assert isinstance(config.settings.CORS_ORIGINS, str)
    assert isinstance(config.settings.vllm_configured, bool)


def test_vllm_configured_reflects_explicit_setting():
    """Признак настройки ИИ-контура верен только при явно заданном адресе."""
    assert config.Settings.from_env({}).vllm_configured is False
    assert config.Settings.from_env({"VLLM_API_URL": "http://x/v1"}).vllm_configured is True
