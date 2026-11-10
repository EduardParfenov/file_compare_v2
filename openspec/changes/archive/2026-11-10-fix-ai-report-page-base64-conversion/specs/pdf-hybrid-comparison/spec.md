## ADDED Requirements

### Requirement: Кодирование изображения в Base64 перед отправкой в vLLM
Эндпоинт `/api/v1/ai-report-page` SHALL принимать изображение страницы как загруженный файл (UploadFile), читать его байты, кодировать в строку Base64 и передавать в клиент vLLM вместе с системным промптом и MIME-типом, чтобы Qwen3-VL-8B могла получить изображение для анализа.

#### Scenario: Изображение конвертируется в Base64 перед вызовом vLLM
- **WHEN** клиент отправляет POST-запрос на `/api/v1/ai-report-page` с полем `image` (PNG/JPEG) и полем `system_prompt`
- **THEN** бэкенд читает байты изображения, кодирует их в строку Base64 и вызывает `stream_analysis_with_image` с параметрами `image_base64`, `image_mime_type` и `system_prompt`, возвращая потоковый ответ (StreamingResponse)

#### Scenario: Ошибка vLLM возвращается как HTTP 502
- **WHEN** vLLM endpoint недоступен или возвращает ошибку при обработке изображения
- **THEN** бэкенд возвращает HTTP 502 с понятным сообщением об ошибке, а пользователь может продолжить работу с обычным diff

### Requirement: Внешний контракт API `/api/v1/ai-report-page` не меняется
Эндпоинт `/api/v1/ai-report-page` SHALL по-прежнему принимать поля `image` (UploadFile) и `system_prompt` (Form) и возвращать `StreamingResponse` с MIME-типом `text/event-stream` после исправления.

#### Scenario: Контракт запроса сохраняется
- **WHEN** клиент вызывает `/api/v1/ai-report-page` с теми же полями, что до исправления
- **THEN** запрос принимается без изменений в сигнатуре endpoints, а ответ по-прежнему является потоковым SSE
