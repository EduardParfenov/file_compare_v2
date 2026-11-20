## 1. Бэкенд: колонтилы — выделение и исключение из основного текста

- [x] 1.1 В `services/pdf_handler.py` добавить константу `FOOTER_BAND: float = 40.0` (высота полосы колонтиля снизу страницы) с комментирующим комментарием. Проверка: `grep -n "FOOTER_BAND" services/pdf_handler.py` — константа присутствует.
  - Выполнено: `services/pdf_handler.py` — `FOOTER_BAND: float = 40.0` с комментарием.
- [x] 1.2 В `extract_text_and_coords`: вычислить `footer_top = max(0.0, rect.height - FOOTER_BAND)`, `main_clip = fitz.Rect(0, 0, rect.width, footer_top)`, `footer_clip = fitz.Rect(0, footer_top, rect.width, rect.height)`, `text = page.get_text("text", clip=main_clip)`, `footer_text = page.get_text("text", clip=footer_clip)`, `raw_words = page.get_text("words", clip=main_clip)`; добавить `footer_text` в структуру `pages_data` и обновить docstring. Проверка: эксперимент — `get_text("text", clip=main_clip)` не включает текст в `y >= height - 40`; тест `tests/test_pdf_handler.py::test_footer_text_recognized_and_excluded_from_main_text` — зелёный.
  - Выполнено: правки в `services/pdf_handler.py`; тест проходит.
- [x] 1.3 В `main.py::compare`: рассчитать `footer_a` / `footer_b` (конкатенация непустых `footer_text`) и `footer_diff = compute_diff(footer_a, footer_b)`; добавить `"footer_diff": footer_diff` в ответ JSON; обновить документацию модуля. Проверка: тест `tests/test_main.py::test_compare` — наличие `footer_diff` в `body`.
  - Выполнено: реализовано; тест зелёный.

## 2. Фронтенд: перемещённый текст — не изменение

- [x] 2.1 В `static/app.js::mapWordsToOps` добавить параметр `otherDocText = ""` и блок подавления после блокового маркирования (если маркер DELETE/INSERT и текст слова есть в `otherDocText` — маркер подавляется); обновить JSDoc. Проверка: `node --check static/app.js` — OK; тесты `tests/test_frontend_diff_mapping.py` — зелёные.
  - Выполнено: реализовано.
- [x] 2.2 В `static/app.js` добавить функцию `otherDocText(panelKey)` — возвращает `(panelKey === "A" ? state.coordsRight : state.coordsLeft).pages.map((p) => p.text || "").join("")`; подключить в `buildDiffWordsHtml` вместо прямого вызова. Проверка: `grep -n "otherDocText" static/app.js` — есть вызов в `buildDiffWordsHtml`; `node --check` — OK.
  - Выполнено: реализовано и подключено.
- [x] 2.3 В `static/app.js`: инициализировать `state.footerDiff = null` и заполнять в `comparePdfs` (`state.footerDiff = result.footer_diff || null`). Проверка: поле есть в структуре `state` и заполняется при сравнении.
  - Выполнено: реализовано.

## 3. Тесты

- [x] 3.1 `tests/test_pdf_handler.py`: `test_footer_text_recognized_and_excluded_from_main_text` (колонтильный текст — в `footer_text`, не в `text`/`full_text`) и `test_no_footer_text_when_absent` (без колонтилов — `footer_text == ""`). Проверка: `pytest tests/test_pdf_handler.py` — зелёные.
  - Выполнено: оба теста проходят в прогоне `pytest -q` (93 passed).
- [x] 3.2 `tests/test_frontend_diff_mapping.py`: синхронизация порта `map_words_to_ops` с параметром `other_doc_text` + подавлением; unit-тесты: `test_moved_word_suppressed_when_present_in_other_doc`, `test_insert_word_suppressed_when_present_in_other_doc`, `test_deleted_word_not_suppressed_when_absent_in_other_doc`, `test_insert_word_not_suppressed_when_absent_in_other_doc`, `test_no_other_doc_text_keeps_marking`; интеграционный тест `test_moved_text_between_pages_not_highlighted` (перенос со стр. 2 на стр. 3 — левая и правая панели содержат только EQUAL). Проверка: `pytest tests/test_frontend_diff_mapping.py` — зелёные.
  - Выполнено: все тесты проходят в прогоне `pytest -q` (93 passed).
- [x] 3.3 `tests/test_main.py::test_compare`: утверждение `"footer_diff" in body`. Проверка: прогон `pytest -q` — зелёный.
  - Выполнено: проходит.

## 4. Приёмка и архивация

Задачи закрываются после подтверждения приёмки (требование capability `change-lifecycle`): идентификатор PR, прогон проверки, локальный `pytest -q`. Пока приёмка не подтверждена — задачи остаются открытыми, а change — активным.

- [ ] 4.1 После подтверждения приёмка (PR + зелёный прогон) закрыть задачи приёмки в этом файле с фактами (ID PR, результат `pytest -q`).
