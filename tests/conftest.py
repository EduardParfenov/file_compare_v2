"""Общие фикстуры для тестов проекта file-compare-v2.

Предоставляет:
- `client` — TestClient FastAPI-приложения (без запуска uvicorn).
- `make_pdf` — фабрика временного валидного PDF-файла с заданным текстом
  через PyMuPDF (не зависит от пользовательских файлов в `input/`).
- `pdf_a` / `pdf_b` — два временных PDF (исходная и измененная версия)
  для тестирования эндпоинта `/api/v1/compare`.
- `pdf_no_text` — PDF без текстового слоя (отсканированный документ).
"""

from __future__ import annotations

import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    """TestClient для FastAPI-приложения."""
    return TestClient(app)


@pytest.fixture
def make_pdf(tmp_path):
    """Фабрика: создать временный PDF-файл с заданным текстом на одной странице.

    Args:
        text: Текст, который будет размещён на странице.
        filename: Имя файла (по умолчанию "test.pdf").

    Returns:
        Путь к созданному PDF-файлу.
    """

    def _create(text: str = "", filename: str = "test.pdf") -> str:
        path = tmp_path / filename
        doc = fitz.open()
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=12)
        doc.save(str(path))
        doc.close()
        return str(path)

    return _create


@pytest.fixture
def pdf_a(make_pdf) -> str:
    """Исходная версия PDF (версия А)."""
    return make_pdf("Hello World\nThis is the original document.", "a.pdf")


@pytest.fixture
def pdf_b(make_pdf) -> str:
    """Измененная версия PDF (версия Б) с добавленным абзацем."""
    return make_pdf(
        "Hello World\nThis is the original document.\nAdded paragraph.",
        "b.pdf",
    )


@pytest.fixture
def pdf_no_text(make_pdf) -> str:
    """PDF без текстового слоя (отсканированный документ): страница без текста."""
    return make_pdf("", "no_text.pdf")
