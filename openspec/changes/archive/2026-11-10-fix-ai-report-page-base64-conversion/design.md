## Context

Маршрут `/api/v1/ai-report-page` в `main.py` принимает изображение страницы как `UploadFile` и вызывает `vllm_client.stream_analysis_with_image(system_prompt=..., image_base64=..., image_mime_type=...)`. Клиент vLLM (`services/vllm_client.py`) уже ожидает изображение в виде строки Base64 и формирует из него `data:{mime};base64,{base64}` URL для Qwen3-VL-8B. Модуль `base64` уже импортирован в `main.py`. Внешний контракт API (поля `image`, `system_prompt`, ответ `StreamingResponse`) сохраняется. См. мотивацию в `proposal.md` — Why.

## Goals / Non-Goals

**Goals:**
- Добавить чтение байт изображения (`await image.read()`), кодирование в строку Base64 и определение MIME-типа перед вызовом `vllm_client.stream_analysis_with_image` в маршруте `/api/v1/ai-report-page`.
- Обрабатывать `VllmClientError` как HTTP 502, прочие ошибки — как HTTP 500 с понятным сообщением.
- Не менять внешний контракт API и не трогать `services/vllm_client.py`.

**Non-Goals:**
- Изменение сигнатуры endpoints `/api/v1/ai-report-page` или `/api/v1/analyze`.
- Конвертация PDF в Markdown или иные форматы.
- Изменение алгоритма diff или работы с координатами PyMuPDF.

## Decisions

**Кодирование в Base64 внутри `main.py`.**
- Решение: в `ai_report_page` прочитать `await image.read()`, затем `base64.b64encode(image_bytes).decode("utf-8")`, определить `image.content_type or "image/png"` и передать в `stream_analysis_with_image`.
- Обоснование: клиент vLLM уже ждёт `image_base64: str`; кодирование на уровне маршрута не меняет контракт API и не требует правки `services/vllm_client.py`.
- Альтернатива: кодировать внутри `vllm_client.stream_analysis_with_image` — отвергнуто, так как клиент должен оставаться независимым от источника байт (он может принимать Base64 из любого источника).

## Risks / Trade-offs

- [Большие изображения] → Base64 увеличивает размер примерно на 33% → приемлемо для снимков одной страницы canvas; потоковый ответ SSE всё равно передаётся фрагментами.
- [Неверный MIME-тип] → если `content_type` отсутствует, по умолчанию используется `image/png` → некритично, так как vLLM чаще определяет формат по заголовку файла.

## Migration Plan

- Изменения локальны в `main.py` (маршрут `/api/v1/ai-report-page`).
- Откат возможен в рамках одного коммита, так как внешний контракт API не меняется и нет изменений в схеме данных.
