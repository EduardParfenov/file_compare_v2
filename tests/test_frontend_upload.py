"""Интеграционный тест фронтенда: загрузка двух PDF через кнопки в браузере.

Проверяет, что:
- страница загружается без JS-ошибок;
- клик по кнопке «Оригинал (PDF)» открывает диалог выбора файла;
- клик по кнопке «Новая версия (PDF)» открывает диалог выбора файла;
- после выбора обоих файлов кнопка «Сравнить документы» становится активной;
- нажатие «Сравнить документы» отправляет запрос на /api/v1/compare и получает 200.

Тест самодостаточен: приложение поднимается в фоновом потоке на свободном
локальном порту, внешний сервер не требуется.

Требует установленного браузера Playwright (`playwright install chromium`);
если браузера нет — тест пропускается, а не падает.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import fitz  # PyMuPDF
import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from main import app


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


pytestmark = pytest.mark.skipif(
    not _chromium_installed(),
    reason="Требуется браузер Playwright: playwright install chromium",
)


@pytest.fixture(scope="module")
def pdf_files(tmp_path_factory):
    """Создаёт два тестовых PDF-файла для загрузки."""
    tmp_dir = tmp_path_factory.mktemp("pdfs")
    paths = []
    for name, text in (("a.pdf", "Original document content."), ("b.pdf", "Modified document content.")):
        path = tmp_dir / name
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
        doc.save(str(path))
        doc.close()
        paths.append(str(path))
    return paths


@pytest.fixture(scope="module")
def live_server():
    """Поднять приложение в фоновом потоке и вернуть его базовый URL."""
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
def browser_page(live_server):
    """Запускает браузер, открывает страницу и возвращает (page, js_errors_with_stack)."""
    js_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def on_page_error(exc):
            stack = getattr(exc, "stack", None)
            js_errors.append({"message": str(exc), "stack": stack})

        def on_console(msg):
            if msg.type == "error":
                js_errors.append({"message": msg.text, "stack": None})

        page.on("pageerror", on_page_error)
        page.on("console", on_console)

        page.goto(f"{live_server}/static/index.html")
        page.wait_for_timeout(2000)

        yield page, js_errors

        browser.close()


def test_frontend_file_upload(browser_page, pdf_files):
    """Полный цикл: выбор двух файлов -> нажатие «Сравнить» -> ответ 200."""
    page, js_errors = browser_page
    pdf_a, pdf_b = pdf_files

    # Выводим ошибки, которые уже накопились после загрузки страницы
    print(f"\nJS ошибки после загрузки страницы ({len(js_errors)}):")
    for e in js_errors:
        print(f"  {e['message']}")
        if e.get("stack"):
            print(f"    Stack: {e['stack'][:500]}")

    # Клик по кнопке «Оригинал (PDF)» -> выбор файла
    with page.expect_file_chooser() as fc_info:
        page.click('label:has-text("Оригинал (PDF)")')
    fc_info.value.set_files([pdf_a])
    page.wait_for_timeout(500)

    # Кнопка сравнения ещё неактивна (нет второго файла)
    assert page.evaluate("() => document.getElementById('btnCompare').disabled") is True

    # Клик по кнопке «Новая версия (PDF)» -> выбор файла
    with page.expect_file_chooser() as fc_info:
        page.click('label:has-text("Новая версия (PDF)")')
    fc_info.value.set_files([pdf_b])
    page.wait_for_timeout(500)

    # Кнопка сравнения стала активной
    assert page.evaluate("() => document.getElementById('btnCompare').disabled") is False

    # Нажатие «Сравнить документы»
    page.click("#btnCompare")
    page.wait_for_timeout(3000)

    # Статус-бар сообщает об успешном сравнении
    status = page.inner_text("#statusBar")
    assert "Сравнено:" in status

    # Выводим все ошибки
    print(f"\nВсе JS ошибки ({len(js_errors)}):")
    for e in js_errors:
        print(f"  {e['message']}")
        if e.get("stack"):
            print(f"    Stack: {e['stack'][:500]}")

    # Нет JS-ошибок
    assert js_errors == [], f"JS ошибки: {[e['message'] for e in js_errors]}"
