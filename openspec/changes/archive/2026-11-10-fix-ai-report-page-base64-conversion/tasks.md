## 1. Бэкенд: конвертация изображения в Base64 в ai_report_page

- [x] 1.1 В маршруте `/api/v1/ai-report-page` (`main.py`) добавить чтение байт изображения (`await image.read()`), кодирование в строку Base64 (`base64.b64encode(image_bytes).decode("utf-8")`) и определение MIME-типа (`image.content_type or "image/png"`) перед вызовом `vllm_client.stream_analysis_with_image`. Проверка: маршрут импортируется и aplikция стартует без ошибок.
- [x] 1.2 Убедиться, что `VllmClientError` обрабатывается как HTTP 502, а прочие ошибки — как HTTP 500 с понятным сообщением. Проверка: блок `try/except` в `ai_report_page` покрывает оба случаи.

## 2. Проверка и приемка

- [x] 2.1 Запустить приложение локально (`uvicorn main:app`) и проверить `GET /api/v1/health` возвращает `{"status": "ok", ...}`. Проверка: сервер стартует без `.env` (дефолтные значения).
- [x] 2.2 Проверить, что внешний контракт `/api/v1/ai-report-page` не изменился (поля `image`, `system_prompt`, ответ `StreamingResponse` с `text/event-stream`). Проверка: сигнатура маршрута и возвращаемый тип соответствуют спецификации.
