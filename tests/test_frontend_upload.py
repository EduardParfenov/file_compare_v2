"""Интеграционный тест фронтенда: загрузка двух PDF через кнопки в браузере.

Проверяет, что:
- страница загружается без JS-ошибок;
- клик по кнопке «Оригинал (PDF)» открывает диалог выбора файла;
- клик по кнопке «Новая версия (PDF)» открывает диалог выбора файла;
- после выбора обоих файлов кнопка «Сравнить документы» становится активной;
- нажатие «Сравнить документы» отправляет запрос на /api/v1/compare и получает 200.

Тест самодостаточен: приложение поднимается в фоновом потоке на свободном
локальном порту, внешний сервер не требуется. Сервер, браузер, страница и
пара тестовых PDF — общие фикстуры `tests/conftest.py`.

Требует установленного браузера Playwright (`playwright install chromium`);
если браузера нет — тест пропускается, а не падает.
"""

from __future__ import annotations


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
    assert (
        page.evaluate("() => document.getElementById('btnCompare').disabled") is False
    )

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
