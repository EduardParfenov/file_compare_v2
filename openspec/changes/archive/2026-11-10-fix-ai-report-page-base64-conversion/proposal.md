## Why

Маршрут `/api/v1/ai-report-page` принимает изображение страницы как `UploadFile` (сырые байты), но передаёт их напрямую в `vllm_client.stream_analysis_with_image(...)`, который ожидает `image_base64: str`. Без кодирования в Base64 библиотека OpenAI отбрасывает запрос с ошибкой валидации схемы, и потоковый ответ падает с HTTP 500. Из-за этого функция ИИ-отчета по странице не работает end-to-end.

## What Changes

- В маршруте `/api/v1/ai-report-page` (`main.py`) прочитать байты изображения (`await image.read()`), закодировать их в строку Base64 (`base64.b64encode(image_bytes).decode("utf-8")`) и определить MIME-тип (`image.content_type or "image/png"`) перед вызовом клиента vLLM.
- Обрабатывать `VllmClientError` как HTTP 502, прочие ошибки — как HTTP 500 с понятным сообщением.

## Capabilities

### New Capabilities

(нет)

### Modified Capabilities

- `pdf-hybrid-comparison`: эндпоинт `/api/v1/ai-report-page` SHALL конвертировать загруженное изображение в строку Base64 перед передачей в `vllm_client.stream_analysis_with_image`, иначе Qwen3-VL-8B не может получить изображение (ошибка валидации схемы запроса OpenAI). Исправление гарантирует, что существующее требование о работающем ИИ-отчете по странице выполняется end-to-end.

## Impact

- `main.py` — маршрут `/api/v1/ai-report-page`: добавлено чтение байт, кодирование в Base64 и определение MIME-типа перед вызовом `vllm_client`.
- `services/vllm_client.py` — без изменений (уже ожидает `image_base64: str`).
- Внешний контракт API не меняется (те же поля `image` и `system_prompt`, тот же `StreamingResponse`).
