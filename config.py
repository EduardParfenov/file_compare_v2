"""Чтение конфигурации приложения из переменных окружения.

Все настройки (URL и ключ vLLM, имя модели, хост и порт FastAPI, CORS)
берутся из переменных окружения. Источники и их приоритет:

1. встроенные значения по умолчанию (``DEFAULTS``);
2. переменные окружения оболочки;
3. файл ``.env`` в корне проекта.

Файл ``.env`` имеет приоритет над переменными окружения оболочки: если
переменная задана в обоих источниках, побеждает значение из ``.env``.

Путь к ``.env`` определяется относительно расположения этого модуля, а не
относительно текущего рабочего каталога и не поиском вверх по дереву
каталогов. Поэтому конфигурация не зависит от того, откуда запущено
приложение, а файл ``.env`` из родительской директории не подхватывается.

Чтение конфигурации не имеет побочных эффектов: значения из ``.env`` не
записываются в окружение текущего процесса.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

#: Путь к файлу `.env` — всегда в корне проекта, рядом с этим модулем.
ENV_FILE = Path(__file__).resolve().parent / ".env"

#: Встроенные значения по умолчанию (используются, если переменная не задана).
DEFAULTS: dict[str, str] = {
    "VLLM_API_URL": "http://localhost:8000/v1",
    "VLLM_MODEL_NAME": "qwen3-vl-8b",
    "VLLM_API_KEY": "",
    "FASTAPI_HOST": "0.0.0.0",
    "FASTAPI_PORT": "8000",
    "CORS_ORIGINS": "*",
}


def read_environment(
    env_file: Path | str | None = ENV_FILE,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Собрать итоговые значения переменных окружения.

    Args:
        env_file: Путь к файлу ``.env``. ``None`` — файл не читается.
        base: Базовый набор значений (по умолчанию — ``os.environ``).

    Returns:
        Словарь значений, в котором значения из ``.env`` перекрывают базовые.

    Ключ без знака ``=`` (значение ``None``) игнорируется — как это делает
    ``python-dotenv``. Пустое значение (``KEY=``) перекрывает базовое.
    """
    merged = dict(os.environ if base is None else base)
    if env_file is None:
        return merged
    path = Path(env_file)
    if not path.is_file():
        return merged
    file_values = dotenv_values(path)
    merged.update({k: v for k, v in file_values.items() if v is not None})
    return merged


@dataclass(frozen=True)
class Settings:
    """Настройки приложения, вычисленные из переменных окружения."""

    VLLM_API_URL: str
    VLLM_MODEL_NAME: str
    VLLM_API_KEY: str
    FASTAPI_HOST: str
    FASTAPI_PORT: int
    CORS_ORIGINS: str
    #: Признак того, что адрес эндпоинта ИИ-модели задан явно
    #: (в окружении оболочки или в файле `.env`), а не взят из дефолта.
    vllm_configured: bool = False

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Settings":
        """Собрать настройки из словаря значений.

        Args:
            values: Значения переменных окружения. Отсутствующие ключи
                берутся из ``DEFAULTS``.

        Returns:
            Экземпляр ``Settings``.

        Порядок приоритетов: встроенные дефолты < окружение оболочки < ``.env``
        (последние два уже свёрнуты в ``values`` функцией ``read_environment``).
        """
        merged = {**DEFAULTS, **(values or {})}
        try:
            port = int(str(merged["FASTAPI_PORT"]))
        except (TypeError, ValueError):
            port = int(DEFAULTS["FASTAPI_PORT"])
        return cls(
            VLLM_API_URL=str(merged["VLLM_API_URL"]),
            VLLM_MODEL_NAME=str(merged["VLLM_MODEL_NAME"]),
            VLLM_API_KEY=str(merged["VLLM_API_KEY"]),
            FASTAPI_HOST=str(merged["FASTAPI_HOST"]),
            FASTAPI_PORT=port,
            CORS_ORIGINS=str(merged["CORS_ORIGINS"]),
            vllm_configured="VLLM_API_URL" in (values or {}),
        )


settings = Settings.from_env(read_environment())
