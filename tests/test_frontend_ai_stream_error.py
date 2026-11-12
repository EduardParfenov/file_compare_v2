"""Интеграционный тест фронтенда: ошибка потокового ИИ-анализа видна пользователю.

Проверяется:
- при обрыве стрима ИИ-модели в панели ИИ-аналитики появляется сообщение
  об ошибке (блок `#aiError` видим, ранее полученный частичный вывод сохранён);
- до запуска анализа блок ошибки скрыт;
- кнопка запуска возвращается в доступное состояние.

Тест самодостаточен: приложение поднимается в фоновом потоке на свободном
локальном порту, внешний сервер не требуется — vLLM заменяется моком.

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
from services.vllm_client import VllmClientError


# ---------------------------------------------------------------------------
# Мок ИИ-модели: отдаёт первый фрагмент, затем обрывает поток
# ---------------------------------------------------------------------------


class _FailingMidStreamClient:
    """Мок vLLM: async-генератор отдаёт фрагмент и затем падает при итерации."""

    chunk = "Первый фрагмент разбора изменений"

    async def stream_analysis(self, prompt: str, **kwargs):
        yield self.chunk
        raise VllmClientError("Ошибка при потоковом анализе через ИИ-модель: обрыв")

    async def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        **kwargs,
    ):
        yield self.chunk
        raise VllmClientError(
            "Ошибка при потоковом визуальном анализе через ИИ-модель: обрыв"
        )


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
    for name, text in (
        ("a.pdf", "Original document content."),
        ("b.pdf", "Modified document content."),
    ):
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
    """Запускает браузер, открывает страницу и возвращает (page, js_errors)."""
    js_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def on_page_error(exc):
            js_errors.append(
                {"message": str(exc), "stack": getattr(exc, "stack", None)}
            )

        def on_console(msg):
            if msg.type == "error":
                js_errors.append({"message": msg.text, "stack": None})

        page.on("pageerror", on_page_error)
        page.on("console", on_console)

        page.goto(f"{live_server}/static/index.html")
        page.wait_for_timeout(2000)

        yield page, js_errors

        browser.close()


def _compare_documents(page, pdf_a: str, pdf_b: str) -> None:
    """Загрузить два PDF и выполнить сравнение — это включает кнопки ИИ."""
    with page.expect_file_chooser() as fc_info:
        page.click('label:has-text("Оригинал (PDF)")')
    fc_info.value.set_files([pdf_a])
    with page.expect_file_chooser() as fc_info:
        page.click('label:has-text("Новая версия (PDF)")')
    fc_info.value.set_files([pdf_b])
    page.click("#btnCompare")
    page.wait_for_timeout(3000)

    assert (
        page.evaluate("() => document.getElementById('btnAiAnalyze').disabled") is False
    )


def test_ai_stream_error_is_visible_to_user(browser_page, pdf_files, monkeypatch):
    """Обрыв стрима: пользователь видит ошибку, частичный вывод сохранён."""
    page, js_errors = browser_page
    pdf_a, pdf_b = pdf_files

    # Мок ИИ-модели живёт в том же процессе, что и тестовый сервер.
    monkeypatch.setattr("main.vllm_client", _FailingMidStreamClient())

    # До запуска анализа блок ошибки скрыт.
    assert page.is_visible("#aiError") is False

    _compare_documents(page, pdf_a, pdf_b)

    # Запускаем ИИ-анализ: поток обрывается после первого фрагмента.
    page.click("#btnAiAnalyze")
    page.wait_for_selector("#aiError:not(.ui-hidden)", timeout=15000)
    page.wait_for_timeout(500)

    # Сообщение об ошибке видимо пользователю.
    assert page.is_visible("#aiError") is True
    error_text = page.inner_text("#aiError")
    assert "ИИ-модель" in error_text

    # Частичный вывод сохранён, кнопка снова доступна.
    assert "Первый фрагмент разбора изменений" in page.inner_text("#aiOutput")
    assert (
        page.evaluate("() => document.getElementById('btnAiAnalyze').disabled") is False
    )

    print(f"\nJS ошибки ({len(js_errors)}):")
    for e in js_errors:
        print(f"  {e['message']}")


def test_ai_page_report_stream_error_is_visible_to_user(
    browser_page, pdf_files, monkeypatch
):
    """Обрыв стрима в отчёте по странице: пользователь видит ошибку."""
    page, js_errors = browser_page
    pdf_a, pdf_b = pdf_files

    monkeypatch.setattr("main.vllm_client", _FailingMidStreamClient())

    _compare_documents(page, pdf_a, pdf_b)

    # Отчёт по странице снимает canvas отрендеренной страницы — дожидаемся
    # появления canvas (рендер выполняет pdf.js).
    page.wait_for_selector(".page-canvas", timeout=15000)

    page.click("#btnAiPageReport")
    page.wait_for_selector("#aiError:not(.ui-hidden)", timeout=20000)
    page.wait_for_timeout(500)

    assert page.is_visible("#aiError") is True
    error_text = page.inner_text("#aiError")
    assert "ИИ-модель" in error_text

    # Частичный вывод сохранён, кнопка снова доступна.
    assert "Первый фрагмент разбора изменений" in page.inner_text("#aiOutput")
    assert (
        page.evaluate("() => document.getElementById('btnAiPageReport').disabled")
        is False
    )

    print(f"\nJS ошибки отчёта ({len(js_errors)}):")
    for e in js_errors:
        print(f"  {e['message']}")
