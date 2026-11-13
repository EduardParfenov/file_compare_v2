"""Общие фикстуры для тестов проекта file-compare-v2.

Предоставляет:
- `client` — TestClient FastAPI-приложения (без запуска uvicorn).
- `make_pdf` — фабрика временного валидного PDF-файла с заданным текстом
  через PyMuPDF (не зависит от пользовательских файлов в `input/`).
- `pdf_a` / `pdf_b` — два временных PDF (исходная и измененная версия)
  для тестирования эндпоинта `/api/v1/compare`.
- `pdf_no_text` — PDF без текстового слоя (отсканированный документ).
- `live_server` — приложение, поднятое в фоновом потоке на свободном
  локальном порту (один сервер на всю сессию тестов).
- `chromium_browser` — браузер Chromium для Playwright (один на модуль).
- `browser_page` — страница браузера с накопленным списком JS-ошибок
  (свежая страница на каждый тестовый модуль).
- `pdf_files` — пара тестовых PDF для браузерных сценариев.

Браузерный харнесс вынесен сюда, потому что он дословно повторялся в двух
тестовых файлах; общее состояние — сервер — живёт на сессию, а браузер,
страница и список JS-ошибок — на модуль: открытый контекст Playwright
держит в главном потоке работающий event loop asyncio, и на сессионной
области он ломал бы `asyncio.run()` в небраузерных тестах, а список
ошибок не должен попадать из одного модуля в другой.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import fitz  # PyMuPDF
import pytest
import uvicorn
from fastapi.testclient import TestClient
from playwright.sync_api import Browser, Page, sync_playwright

from main import app

#: Размер окна браузера в браузерных тестах.
#: 1280x800 — тот размер, при котором измерен обрезанный интерфейс
#: (body.scrollHeight = 865 при высоте окна 800).
BROWSER_VIEWPORT = {"width": 1280, "height": 800}


def _free_port() -> int:
    """Найти свободный TCP-порт для тестового сервера."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _chromium_installed() -> bool:
    """Проверить, установлен ли браузер Chromium для Playwright."""
    try:
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001
        return False


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


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    """Поднять приложение в фоновом потоке и вернуть его базовый URL.

    Сервер живёт на всю сессию тестов: один uvicorn вместо одного на
    каждый тестовый модуль.

    Yields:
        Базовый URL приложения, например ``http://127.0.0.1:34567``.
    """
    port = _free_port()
    server_config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(server_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            server.should_exit = True
            pytest.skip("Не удалось запустить тестовый сервер uvicorn")
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def chromium_browser() -> Iterator[Browser]:
    """Браузер Chromium для браузерных тестов.

    Область видимости — модуль, а не сессия: открытый контекст
    ``sync_playwright()`` держит в главном потоке работающий event loop
    asyncio, и на сессионной области он ломал бы ``asyncio.run()`` в
    небраузерных тестах (проверено: ``RuntimeError: asyncio.run() cannot be
    called from a running event loop``). Контекст закрывается вместе с
    модулем — работающего цикла в главном потоке не остаётся.

    При отсутствии Chromium тесты пропускаются, а не падают.

    Yields:
        Запущенный браузер Chromium.
    """
    if not _chromium_installed():
        pytest.skip("Требуется браузер Playwright: playwright install chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def browser_page(
    chromium_browser: Browser, live_server: str
) -> Iterator[tuple[Page, list[dict]]]:
    """Открыть страницу приложения и собирать ошибки JavaScript.

    Страница и список ошибок — на уровне модуля: ошибки, накопленные в
    одном тестовом модуле, не должны попадать в проверки другого.

    Yields:
        Кортеж (страница браузера, список ошибок JavaScript).
    """
    js_errors: list[dict] = []
    page = chromium_browser.new_page(viewport=BROWSER_VIEWPORT)

    def on_page_error(exc) -> None:
        js_errors.append({"message": str(exc), "stack": getattr(exc, "stack", None)})

    def on_console(msg) -> None:
        if msg.type == "error":
            js_errors.append({"message": msg.text, "stack": None})

    page.on("pageerror", on_page_error)
    page.on("console", on_console)

    page.goto(f"{live_server}/static/index.html")
    page.wait_for_timeout(2000)

    yield page, js_errors

    page.close()


@pytest.fixture(scope="module")
def pdf_files(tmp_path_factory) -> list[str]:
    """Создать пару тестовых PDF-файлов для браузерных сценариев.

    Вторая версия отличается от первой: один абзац удалён, другой добавлен —
    так diff содержит и операцию DELETE, и операцию INSERT.

    Returns:
        Список из двух путей: исходная версия и изменённая.
    """
    tmp_dir = tmp_path_factory.mktemp("browser_pdfs")
    paths = []
    for name, lines in (
        (
            "a.pdf",
            [
                "Original document content.",
                "Second paragraph of the original document.",
                "Third paragraph of the original document.",
            ],
        ),
        (
            "b.pdf",
            [
                "Original document content.",
                "Third paragraph of the original document.",
                "Added paragraph of the new version.",
            ],
        ),
    ):
        path = tmp_dir / name
        doc = fitz.open()
        page = doc.new_page()
        for index, line in enumerate(lines):
            page.insert_text((72, 72 + index * 20), line, fontsize=12)
        doc.save(str(path))
        doc.close()
        paths.append(str(path))
    return paths
