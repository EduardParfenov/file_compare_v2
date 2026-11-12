"""Тесты контракта ошибок потоковых ИИ-маршрутов.

Проверяется:
- сбой до первого фрагмента (async-генератор, падающий при итерации)
  → HTTP 502 с понятным сообщением, а не HTTP 200 с пустым телом;
- сбой в середине стрима → HTTP 200 и кадр `event: error` в потоке,
  ранее переданные фрагменты сохраняются, поток закрывается штатно;
- успешный стрим → только кадры данных, кадра ошибки нет;
- заголовки SSE-ответа (`Cache-Control`, `X-Accel-Buffering`);
- внутренний адрес эндпоинта ИИ-модели и ключ доступа не попадают в ответ.

Моки повторяют поведение настоящего клиента: `stream_analysis` — async-генератор,
поэтому ошибка возникает при итерации, а не при создании потока.
"""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
from openai import APIConnectionError, APIStatusError

from main import _stream_sse
from services.vllm_client import VllmClient, VllmClientError, sanitize_error_text

#: Внутренние сведения, которые не должны попасть к пользователю.
INTERNAL_API_URL = "http://vllm.internal.local:8000/v1"
INTERNAL_API_KEY = "secret-vllm-key"

#: Минимальный валидный PNG (1x1 пиксель) для загрузки в /api/v1/ai-report-page.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# ---------------------------------------------------------------------------
# Моки клиента vLLM
# ---------------------------------------------------------------------------


def _safe_message(detail: str) -> str:
    """Собрать текст ошибки так же, как это делает настоящий клиент:
    внутренний адрес и ключ заменяются, а не показываются пользователю."""
    return sanitize_error_text(
        f"Ошибка при потоковом анализе через ИИ-модель: {detail}",
        api_url=INTERNAL_API_URL,
        api_key=INTERNAL_API_KEY,
    )


class _FailingBeforeFirstChunkClient:
    """Мок реального клиента: async-генератор, падающий при итерации
    до первого фрагмента (как при недоступном vLLM)."""

    def __init__(self, message: str):
        self.message = message

    async def stream_analysis(self, prompt: str, **kwargs):
        raise VllmClientError(self.message)
        yield  # pragma: no cover — недостижимо: делает функцию async-генератором

    async def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        **kwargs,
    ):
        raise VllmClientError(self.message)
        yield  # pragma: no cover — недостижимо: делает функцию async-генератором


class _FailingMidStreamClient:
    """Мок реального клиента: отдаёт первый фрагмент, затем падает при итерации."""

    def __init__(self, message: str, chunk: str = "Первый фрагмент ответа"):
        self.message = message
        self.chunk = chunk

    async def stream_analysis(self, prompt: str, **kwargs):
        yield self.chunk
        raise VllmClientError(self.message)

    async def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        **kwargs,
    ):
        yield self.chunk
        raise VllmClientError(self.message)


class _OkStreamClient:
    """Мок успешного стрима."""

    async def stream_analysis(self, prompt: str, **kwargs):
        yield "Часть 1 ответа "
        yield "часть 2 ответа"

    async def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        **kwargs,
    ):
        yield "Анализ страницы "
        yield "завершён"


def _sse_frames(body: str) -> list[dict]:
    """Разобрать тело SSE-ответа на кадры: {event, data}."""
    frames = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        frames.append({"event": event, "data": data})
    return frames


# ---------------------------------------------------------------------------
# Сбой до первого фрагмента → HTTP 502
# ---------------------------------------------------------------------------


def test_analyze_failure_before_first_chunk_returns_502(monkeypatch, client):
    """Сбой до первого фрагмента: HTTP 502, а не 200 с пустым телом."""
    message = _safe_message(f"соединение отклонено ({INTERNAL_API_URL})")
    monkeypatch.setattr("main.vllm_client", _FailingBeforeFirstChunkClient(message))

    response = client.post("/api/v1/analyze", data={"prompt": "разбери изменения"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ИИ-модель" in detail
    assert INTERNAL_API_URL not in detail
    assert INTERNAL_API_KEY not in detail


def test_ai_report_page_failure_before_first_chunk_returns_502(monkeypatch, client):
    """Сбой до первого фрагмента на отчёте по странице: HTTP 502."""
    message = _safe_message(f"соединение отклонено ({INTERNAL_API_URL})")
    monkeypatch.setattr("main.vllm_client", _FailingBeforeFirstChunkClient(message))

    response = client.post(
        "/api/v1/ai-report-page",
        files={"image": ("page.png", TINY_PNG, "image/png")},
        data={"system_prompt": "проанализируй страницу"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ИИ-модель" in detail
    assert INTERNAL_API_URL not in detail


# ---------------------------------------------------------------------------
# Сбой в середине стрима → кадр `event: error`
# ---------------------------------------------------------------------------


def test_analyze_failure_mid_stream_sends_error_event(monkeypatch, client):
    """Обрыв в середине стрима: HTTP 200, кадр `event: error`, фрагмент сохранён."""
    message = _safe_message("соединение оборвано")
    monkeypatch.setattr("main.vllm_client", _FailingMidStreamClient(message))

    response = client.post("/api/v1/analyze", data={"prompt": "разбери изменения"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = _sse_frames(response.text)
    data_frames = [f for f in frames if f["event"] is None]
    error_frames = [f for f in frames if f["event"] == "error"]

    assert len(data_frames) == 1
    assert json.loads(data_frames[0]["data"]) == "Первый фрагмент ответа"

    assert len(error_frames) == 1
    payload = json.loads(error_frames[0]["data"])
    assert payload["error"] == message
    assert INTERNAL_API_URL not in response.text
    assert "Traceback" not in response.text


def test_ai_report_page_failure_mid_stream_sends_error_event(monkeypatch, client):
    """Обрыв в середине стрима на отчёте по странице: кадр `event: error`."""
    message = _safe_message("соединение оборвано")
    monkeypatch.setattr("main.vllm_client", _FailingMidStreamClient(message))

    response = client.post(
        "/api/v1/ai-report-page",
        files={"image": ("page.png", TINY_PNG, "image/png")},
        data={"system_prompt": "проанализируй страницу"},
    )

    assert response.status_code == 200
    frames = _sse_frames(response.text)
    error_frames = [f for f in frames if f["event"] == "error"]
    assert len(error_frames) == 1
    assert json.loads(error_frames[0]["data"])["error"] == message
    assert INTERNAL_API_URL not in response.text


# ---------------------------------------------------------------------------
# Успешный стрим: только кадры данных + заголовки SSE
# ---------------------------------------------------------------------------


def test_analyze_success_stream_has_only_data_frames(monkeypatch, client):
    """Успешный стрим: только кадры данных, кадра `event: error` нет."""
    monkeypatch.setattr("main.vllm_client", _OkStreamClient())

    response = client.post("/api/v1/analyze", data={"prompt": "разбери изменения"})

    assert response.status_code == 200
    assert "event: error" not in response.text

    frames = _sse_frames(response.text)
    assert [json.loads(f["data"]) for f in frames] == [
        "Часть 1 ответа ",
        "часть 2 ответа",
    ]


def test_sse_responses_disable_proxy_buffering(monkeypatch, client):
    """SSE-ответы содержат заголовки против буферизации реверс-прокси."""
    monkeypatch.setattr("main.vllm_client", _OkStreamClient())

    analyze_response = client.post(
        "/api/v1/analyze", data={"prompt": "разбери изменения"}
    )
    report_response = client.post(
        "/api/v1/ai-report-page",
        files={"image": ("page.png", TINY_PNG, "image/png")},
        data={"system_prompt": "проанализируй страницу"},
    )

    for response in (analyze_response, report_response):
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"


# ---------------------------------------------------------------------------
# Жизненный цикл upstream-потока
# ---------------------------------------------------------------------------


class _TrackedStream:
    """Async-итератор, отслеживающий явное закрытие (`aclose`).

    Обычный async-генератор закрывается сборщиком мусора недетерминированно,
    поэтому для проверки используется объект с явным методом `aclose`.
    """

    def __init__(self, chunks: list[str]):
        self._chunks = list(chunks)
        self.closed = False

    def __aiter__(self) -> "_TrackedStream":
        return self

    async def __anext__(self) -> str:
        if not self._chunks:
            await asyncio.sleep(10)  # имитация долгой генерации
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def aclose(self) -> None:
        self.closed = True


def test_upstream_stream_is_closed_after_stream():
    """Upstream-поток закрывается после завершения стрима."""
    upstream = _TrackedStream(["chunk-1", "chunk-2"])

    async def scenario():
        return [frame async for frame in _stream_sse(upstream)]

    frames = asyncio.run(scenario())

    assert len(frames) == 2
    assert upstream.closed is True


def test_upstream_stream_is_closed_on_cancellation():
    """Upstream-поток закрывается при отмене запроса (обрыв клиента)."""
    upstream = _TrackedStream(["chunk-1"])

    async def scenario():
        stream = _stream_sse(upstream)
        first = await stream.__anext__()
        pending = asyncio.create_task(stream.__anext__())
        await asyncio.sleep(0)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        return first

    first = asyncio.run(scenario())

    assert first == b'data: "chunk-1"\n\n'
    assert upstream.closed is True


# ---------------------------------------------------------------------------
# Конфиденциальность сообщений об ошибках
# ---------------------------------------------------------------------------


def test_client_error_message_hides_internal_endpoint_and_key():
    """Текст ошибки клиента не содержит внутренний адрес, ключ и сырой текст сбоя."""
    client = VllmClient(api_url=INTERNAL_API_URL, api_key=INTERNAL_API_KEY)

    try:
        raise RuntimeError(f"нет связи с {INTERNAL_API_URL}, ключ {INTERNAL_API_KEY}")
    except RuntimeError as exc:
        error = client._user_error("потоковом анализе", exc)

    text = str(error)
    assert INTERNAL_API_URL not in text
    assert INTERNAL_API_KEY not in text
    # Сырое описание сбоя пользователю не показывается — только безопасная причина.
    assert "нет связи с" not in text
    assert "Непредвиденная ошибка при обращении к ИИ-модели" in text


def test_client_error_does_not_relay_upstream_response_body():
    """Тело ответа vLLM не попадает в сообщение пользователю.

    `APIStatusError` в openai-клиенте содержит тело ответа сервера — там
    могут быть внутренние пути, хосты и ключи.
    """
    client = VllmClient(api_url=INTERNAL_API_URL, api_key=INTERNAL_API_KEY)
    request = httpx.Request(
        "POST", "http://vllm.internal.local:8000/v1/chat/completions"
    )
    response = httpx.Response(
        500,
        request=request,
        json={
            "error": f"internal failure at {INTERNAL_API_URL} key={INTERNAL_API_KEY}"
        },
    )
    exc = APIStatusError(
        f"Error code: 500 - {response.text}", response=response, body=response.text
    )

    text = str(client._user_error("потоковом анализе", exc))

    assert INTERNAL_API_URL not in text
    assert INTERNAL_API_KEY not in text
    assert "internal failure" not in text
    assert "vllm.internal.local" not in text
    assert "ИИ-модель вернула ошибку" in text


def test_client_error_describes_connection_failure():
    """Недоступность ИИ-модели описывается понятной фразой без деталей."""
    client = VllmClient(api_url=INTERNAL_API_URL, api_key=INTERNAL_API_KEY)
    request = httpx.Request(
        "POST", "http://vllm.internal.local:8000/v1/chat/completions"
    )
    exc = APIConnectionError(message="Connection error.", request=request)

    text = str(client._user_error("потоковом анализе", exc))

    assert "ИИ-модель недоступна" in text
    assert "vllm.internal.local" not in text


def test_sanitize_error_text_masks_all_url_forms():
    """Маскируются все распространённые формы внутреннего адреса."""
    variants = [
        INTERNAL_API_URL,
        INTERNAL_API_URL.removesuffix("/v1"),
        INTERNAL_API_URL.removeprefix("http://"),
        "vllm.internal.local",
    ]
    for variant in variants:
        text = sanitize_error_text(
            f"соединение с {variant} не установлено",
            api_url=INTERNAL_API_URL,
            api_key=INTERNAL_API_KEY,
        )
        assert "vllm.internal.local" not in text, variant
        assert "internal.local" not in text, variant


def test_sanitize_error_text_keeps_short_key_intact():
    """Короткие значения не маскируются — иначе портится обычный текст."""
    text = sanitize_error_text(
        "последняя модель доступна",
        api_url=INTERNAL_API_URL,
        api_key="test",
    )
    assert "последняя модель доступна" == text
