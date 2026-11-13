"""Интеграционный тест фронтенда: панель ИИ-аналитики и раскладка интерфейса.

Проверяется:
- клик по шапке боковой панели ИИ-аналитики сворачивает и разворачивает её
  содержимое и не порождает ошибок JavaScript;
- успешный, но пустой ответ ИИ-модели сопровождается пояснением, отдельным
  от сообщения об ошибке;
- интерфейс не обрезается по вертикали: страница не прокручивается, панель
  ИИ-аналитики видна целиком, а прокручиваются области страниц внутри панелей.

Сервер, браузер, страница и пара тестовых PDF — общие фикстуры
`tests/conftest.py`.

Требует установленного браузера Playwright (`playwright install chromium`);
если браузера нет — тест пропускается, а не падает.
"""

from __future__ import annotations


class _EmptyStreamClient:
    """Мок vLLM: async-генератор завершается без единого фрагмента."""

    async def stream_analysis(self, prompt: str, **kwargs):
        """Пустой успешный поток: ни одного фрагмента и ни одной ошибки."""
        return
        yield  # pragma: no cover — недостижимо, делает функцию async-генератором

    async def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        **kwargs,
    ):
        """Пустой успешный поток для визуального анализа."""
        return
        yield  # pragma: no cover — недостижимо, делает функцию async-генератором


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


def _new_js_errors(js_errors: list[dict], mark: int) -> list[dict]:
    """Ошибки JavaScript, накопленные после отметки ``mark``.

    Список ошибок общий для тестового модуля, поэтому проверяется не он
    целиком, а только те ошибки, которые внес конкретный тест: тест с
    намеренно падающим потоком не должен «заражать» следующие проверки.

    Args:
        js_errors: Общий список ошибок страницы.
        mark: Отметка — длина списка в начале теста.

    Returns:
        Ошибки, добавленные после отметки.
    """
    return js_errors[mark:]


def test_ai_panel_toggle_collapses_and_expands(browser_page):
    """Клик по шапке панели ИИ сворачивает и разворачивает её без ошибок JS."""
    page, js_errors = browser_page
    mark = len(js_errors)

    # Изначально панель развёрнута.
    assert page.is_visible("#aiPanelContent") is True
    assert page.inner_text("#aiPanelToggle").strip() == "▲"

    # Клик по индикатору состояния — он находится в шапке панели.
    page.click("#aiPanelToggle")
    page.wait_for_timeout(300)

    # Панель свёрнута, индикатор показывает свёрнутое состояние.
    assert page.is_visible("#aiPanelContent") is False
    assert page.inner_text("#aiPanelToggle").strip() == "▼"

    page.click("#aiPanelToggle")
    page.wait_for_timeout(300)

    # Панель снова развёрнута, индикатор вернулся в исходное состояние.
    assert page.is_visible("#aiPanelContent") is True
    assert page.inner_text("#aiPanelToggle").strip() == "▲"

    # Клик по самой шапке (по заголовку) тоже переключает панель.
    page.click("#aiPanelHeader")
    page.wait_for_timeout(300)
    assert page.is_visible("#aiPanelContent") is False

    page.click("#aiPanelHeader")
    page.wait_for_timeout(300)
    assert page.is_visible("#aiPanelContent") is True

    assert _new_js_errors(js_errors, mark) == [], (
        f"JS ошибки: {[e['message'] for e in _new_js_errors(js_errors, mark)]}"
    )


def test_empty_ai_answer_is_explained_to_user(browser_page, pdf_files, monkeypatch):
    """Пустой успешный ответ модели: пользователь видит пояснение, не ошибку."""
    page, js_errors = browser_page
    pdf_a, pdf_b = pdf_files
    mark = len(js_errors)

    # Мок ИИ-модели живёт в том же процессе, что и тестовый сервер.
    monkeypatch.setattr("main.vllm_client", _EmptyStreamClient())

    _compare_documents(page, pdf_a, pdf_b)

    # До запуска анализа ни пояснения, ни ошибки нет.
    assert page.is_visible("#aiEmpty") is False
    assert page.is_visible("#aiError") is False

    page.click("#btnAiAnalyze")
    page.wait_for_selector("#aiEmpty:not(.ui-hidden)", timeout=15000)
    page.wait_for_timeout(500)

    # Пояснение о пустом ответе видимо, блок ошибки скрыт.
    assert page.is_visible("#aiEmpty") is True
    assert "пустой ответ" in page.inner_text("#aiEmpty")
    assert page.is_visible("#aiError") is False

    # Кнопка запуска снова доступна.
    assert (
        page.evaluate("() => document.getElementById('btnAiAnalyze').disabled") is False
    )

    assert _new_js_errors(js_errors, mark) == [], (
        f"JS ошибки: {[e['message'] for e in _new_js_errors(js_errors, mark)]}"
    )


def test_ai_error_is_shown_instead_of_empty_explanation(
    browser_page, pdf_files, monkeypatch
):
    """Ошибка потока: вместо пояснения о пустом ответе показана ошибка."""
    page, js_errors = browser_page
    pdf_a, pdf_b = pdf_files

    class _FailingClient(_EmptyStreamClient):
        """Мок vLLM: поток падает до первого фрагмента."""

        async def stream_analysis(self, prompt: str, **kwargs):
            raise RuntimeError("ИИ-модель недоступна")
            yield  # pragma: no cover — недостижимо

    monkeypatch.setattr("main.vllm_client", _FailingClient())

    _compare_documents(page, pdf_a, pdf_b)

    page.click("#btnAiAnalyze")
    page.wait_for_selector("#aiError:not(.ui-hidden)", timeout=15000)
    page.wait_for_timeout(500)

    # Показана ошибка, а пояснение о пустом ответе не показано.
    assert page.is_visible("#aiError") is True
    assert page.is_visible("#aiEmpty") is False

    # Ошибки консоли здесь ожидаемы (сервер ответил 500), поэтому они только
    # выводятся, а не проверяются на отсутствие.
    print(f"\nJS ошибки ({len(js_errors)}):")
    for e in js_errors:
        print(f"  {e['message']}")


def test_interface_layout_is_not_clipped(browser_page):
    """Интерфейс занимает высоту окна: ничего не срезано, страница не прокручивается."""
    page, js_errors = browser_page
    mark = len(js_errors)

    layout = page.evaluate("""() => {
        const body = document.body;
        const aside = document.getElementById('aiPanel');
        return {
            viewport_h: window.innerHeight,
            body_scroll_h: body.scrollHeight,
            body_client_h: body.clientHeight,
            aside_bottom: aside.getBoundingClientRect().bottom,
        };
    }""")

    assert layout["body_scroll_h"] <= layout["body_client_h"], (
        f"Страница прокручивается по вертикали: {layout}"
    )
    assert layout["body_scroll_h"] <= layout["viewport_h"]
    assert layout["aside_bottom"] <= layout["viewport_h"], (
        f"Нижняя часть панели ИИ срезана: {layout}"
    )

    assert _new_js_errors(js_errors, mark) == [], (
        f"JS ошибки: {[e['message'] for e in _new_js_errors(js_errors, mark)]}"
    )


def test_interface_layout_adapts_to_window_height(browser_page):
    """При изменении высоты окна раскладка подстраивается, обрезания нет."""
    page, js_errors = browser_page
    mark = len(js_errors)

    for height in (700, 900):
        page.set_viewport_size({"width": 1024, "height": height})
        page.wait_for_timeout(300)

        layout = page.evaluate("""() => {
            const body = document.body;
            const aside = document.getElementById('aiPanel');
            const main = document.querySelector('main');
            return {
                viewport_h: window.innerHeight,
                body_scroll_h: body.scrollHeight,
                body_client_h: body.clientHeight,
                aside_bottom: aside.getBoundingClientRect().bottom,
                main_h: main.getBoundingClientRect().height,
            };
        }""")

        assert layout["body_scroll_h"] <= layout["viewport_h"], layout
        assert layout["aside_bottom"] <= layout["viewport_h"], layout
        # Основная область занимает остаток высоты окна, а не всю высоту
        # целиком: иначе содержимое снова вышло бы за пределы окна.
        assert layout["main_h"] < layout["viewport_h"], layout

    # Возвращаем исходный размер окна: страница общая для модуля.
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(300)

    assert _new_js_errors(js_errors, mark) == [], (
        f"JS ошибки: {[e['message'] for e in _new_js_errors(js_errors, mark)]}"
    )


def test_comparison_panels_scroll_internally(browser_page, pdf_files):
    """Прокручивается область страниц, а не всё окно приложения."""
    page, js_errors = browser_page
    pdf_a, pdf_b = pdf_files
    mark = len(js_errors)

    _compare_documents(page, pdf_a, pdf_b)
    page.wait_for_selector(".page-canvas", timeout=15000)

    # Область страниц содержит отрендеренную страницу выше своей высоты.
    scroll = page.evaluate("""() => {
        const panel = document.getElementById('panelA');
        panel.scrollTop = 120;
        return {
            panel_top: panel.scrollTop,
            panel_client_h: panel.clientHeight,
            panel_scroll_h: panel.scrollHeight,
            window_y: window.scrollY,
        };
    }""")

    assert scroll["panel_scroll_h"] > scroll["panel_client_h"], scroll
    assert scroll["panel_top"] > 0, scroll
    # Окно приложения не прокручивается — прокручивается только панель.
    assert scroll["window_y"] == 0, scroll

    assert _new_js_errors(js_errors, mark) == [], (
        f"JS ошибки: {[e['message'] for e in _new_js_errors(js_errors, mark)]}"
    )
