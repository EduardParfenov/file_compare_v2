"""Проверка достоверности правил проекта (`AGENTS.md`).

Правила проекта не должны ссылаться на несуществующие элементы репозитория:

- модули `services/*.py`, названные в правилах, должны существовать;
- файлы и каталоги из структуры проекта должны существовать;
- имена публичного API, названные в разделе «Ключевые API», должны быть
  определены в исходном коде приложения.

Тест работает только с файлами репозитория: приватные пользовательские данные
(папка с файлами пользователя и файл с секретами) в проверке не участвуют и не
открываются.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Корень репозитория — вычисляется от расположения теста, а не от CWD.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Файл правил проекта.
AGENTS_FILE = REPO_ROOT / "AGENTS.md"

#: Пути, наличие которых проверяется по правилам проекта.
DOCUMENTED_PATHS = (
    "main.py",
    "config.py",
    "requirements.txt",
    "requirements-dev.txt",
    "pytest.ini",
    "ruff.toml",
    ".env.example",
    ".gitignore",
    "README.md",
    "AGENTS.md",
    "backlog.md",
    "services/__init__.py",
    "static/index.html",
    "static/app.js",
    "static/styles.css",
    "tests/conftest.py",
    ".github/workflows/ci.yml",
    "openspec",
)

#: Заголовок раздела с перечнем публичного API в правилах проекта.
API_SECTION_MARKER = "## 14."


def _agents_text() -> str:
    """Прочитать правила проекта."""
    return AGENTS_FILE.read_text(encoding="utf-8")


def _api_section(text: str) -> str:
    """Выделить раздел «Ключевые API» из правил проекта.

    Args:
        text: Полный текст правил проекта.

    Returns:
        Текст раздела либо пустая строка, если раздел не найден.
    """
    if API_SECTION_MARKER not in text:
        return ""
    return text.split(API_SECTION_MARKER, 1)[1]


def _app_sources() -> str:
    """Собрать текст исходников приложения.

    Returns:
        Склеенное содержимое модулей `main.py`, `config.py` и `services/*.py`.
    """
    parts = [
        (REPO_ROOT / "main.py").read_text(encoding="utf-8"),
        (REPO_ROOT / "config.py").read_text(encoding="utf-8"),
    ]
    for path in sorted((REPO_ROOT / "services").glob("*.py")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _mentioned_service_modules(text: str) -> set[str]:
    """Имена модулей `services/*.py`, упомянутых в правилах проекта."""
    return set(re.findall(r"services/([A-Za-z0-9_]+\.py)", text))


def _mentioned_callables(section: str) -> set[str]:
    """Имена вызываемых функций и методов, названных в разделе API."""
    names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_.]*)\(", section)
    return {name.split(".")[-1] for name in names}


def _mentioned_settings_attributes(section: str) -> set[str]:
    """Имена атрибутов настроек, названных в разделе API."""
    return set(re.findall(r"\bsettings\.([A-Za-z_][A-Za-z0-9_]*)", section))


def test_documented_project_files_exist() -> None:
    """Файлы и каталоги из правил проекта присутствуют в репозитории."""
    missing = [name for name in DOCUMENTED_PATHS if not (REPO_ROOT / name).exists()]
    assert not missing, f"Пути, упомянутые в AGENTS.md, отсутствуют: {missing}"


def test_mentioned_service_modules_exist() -> None:
    """Модули `services/*.py`, названные в правилах, существуют."""
    mentioned = _mentioned_service_modules(_agents_text())
    assert mentioned, "В правилах проекта не найдено упоминаний модулей сервисов"
    services_dir = REPO_ROOT / "services"
    missing = [
        name for name in sorted(mentioned) if not (services_dir / name).is_file()
    ]
    assert not missing, f"Модули, упомянутые в AGENTS.md, отсутствуют: {missing}"


def test_documented_api_names_exist() -> None:
    """Публичный API, названный в разделе «Ключевые API», определён в коде."""
    section = _api_section(_agents_text())
    assert section, f"В AGENTS.md не найден раздел «{API_SECTION_MARKER} Ключевые API»"
    callables = _mentioned_callables(section)
    assert callables, "В разделе «Ключевые API» не найдено имён вызываемых функций"
    source = _app_sources()
    missing = [
        name
        for name in sorted(callables)
        if not re.search(rf"\b(?:def|class)\s+{re.escape(name)}\b", source)
    ]
    assert not missing, f"Документированные API отсутствуют в коде: {missing}"


def test_documented_settings_attributes_exist() -> None:
    """Атрибуты настроек, названные в правилах, присутствуют в конфигурации."""
    section = _api_section(_agents_text())
    assert section, f"В AGENTS.md не найден раздел «{API_SECTION_MARKER} Ключевые API»"
    attributes = _mentioned_settings_attributes(section)
    assert attributes, "В разделе «Ключевые API» не найдено атрибутов настроек"
    source = (REPO_ROOT / "config.py").read_text(encoding="utf-8")
    missing = [name for name in sorted(attributes) if name not in source]
    assert not missing, f"Документированные настройки отсутствуют: {missing}"
