"""Тесты для роутов API в `main.py`.

Проверяются:
- `GET /api/v1/health` — возвращает `status: ok`, `vllm_api_url`, `vllm_model`.
- `POST /api/v1/compare` — с двумя тестовыми PDF возвращает
  `left_panel`/`right_panel`, координаты, `summary`.
- ИИ-маршруты (`/api/v1/analyze`, `/api/v1/ai-report-page`) с мокированием vLLM:
  возврат 502 при недоступности vLLM, корректная работа при моке.
"""

from __future__ import annotations

import base64

from services.vllm_client import VllmClientError


# ---------------------------------------------------------------------------
# Вспомогательный мок vLLM-клиента
# ---------------------------------------------------------------------------


class _MockStream:
    """Асинхронный итератор, отдающий заданные фрагменты строк."""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def __aiter__(self) -> "_MockStream":
        return self

    async def __anext__(self) -> str:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _MockVllmClient:
    """Мок vllm_client с настраиваемым поведением.

    Методы не являются async-функциями, а возвращают async-итератор напрямую,
    чтобы код в main.py (`async for text in events`) работал корректно.
    """

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.stream_analysis_called = False
        self.stream_analysis_with_image_called = False

    def stream_analysis(self, prompt: str, **kwargs) -> _MockStream:
        self.stream_analysis_called = True
        if self.should_fail:
            raise VllmClientError("vLLM недоступен")
        return _MockStream(["Часть 1 ответа ", "часть 2 ответа"])

    def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        **kwargs,
    ) -> _MockStream:
        self.stream_analysis_with_image_called = True
        if self.should_fail:
            raise VllmClientError("vLLM недоступен")
        return _MockStream(["Анализ страницы ", "завершён"])


# ---------------------------------------------------------------------------
# Тесты здоровья
# ---------------------------------------------------------------------------


def test_health(client):
    """GET /api/v1/health возвращает status: ok и безопасные сведения о конфигурации."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "vllm_model" in body
    assert body["vllm_model"] == "qwen3-vl-8b"
    assert isinstance(body["vllm_configured"], bool)
    # Внутренний адрес эндпоинта ИИ-модели не раскрывается.
    assert "vllm_api_url" not in body


# ---------------------------------------------------------------------------
# Тесты корневого маршрута и раздачи статики
# ---------------------------------------------------------------------------


def test_root_serves_user_interface(client):
    """GET / отдаёт HTML-документ пользовательского интерфейса, а не 404."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_static_and_root_work_from_any_working_directory(client, tmp_path, monkeypatch):
    """Корневой маршрут и статика не зависят от текущего рабочего каталога."""
    monkeypatch.chdir(tmp_path)

    assert client.get("/").status_code == 200

    static_response = client.get("/static/styles.css")
    assert static_response.status_code == 200
    assert "--diff-delete-bg" in static_response.text


# ---------------------------------------------------------------------------
# Тесты сравнения PDF
# ---------------------------------------------------------------------------


def test_compare(client, pdf_a, pdf_b):
    """POST /api/v1/compare с двумя PDF возвращает left_panel/right_panel."""
    with open(pdf_a, "rb") as f_a, open(pdf_b, "rb") as f_b:
        response = client.post(
            "/api/v1/compare",
            files={"file_a": ("a.pdf", f_a, "application/pdf"),
                   "file_b": ("b.pdf", f_b, "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "left_panel" in body
    assert "right_panel" in body
    assert "coords_left" in body
    assert "coords_right" in body
    assert "summary" in body
    assert "meta" in body
    assert body["meta"]["file_a"] == "a.pdf"
    assert body["meta"]["file_b"] == "b.pdf"


# ---------------------------------------------------------------------------
# Тесты ИИ-маршрутов с мокированием vLLM
# ---------------------------------------------------------------------------


def test_analyze_vllm_unavailable(monkeypatch, client):
    """POST /api/v1/analyze возвращает 502, когда vLLM недоступен."""
    mock = _MockVllmClient(should_fail=True)
    monkeypatch.setattr("main.vllm_client", mock)
    response = client.post("/api/v1/analyze", data={"prompt": "разбери изменения"})
    assert response.status_code == 502


def test_analyze_vllm_mocked(monkeypatch, client):
    """POST /api/v1/analyze работает с mocked vLLM и возвращает SSE-поток."""
    mock = _MockVllmClient(should_fail=False)
    monkeypatch.setattr("main.vllm_client", mock)
    response = client.post("/api/v1/analyze", data={"prompt": "разбери изменения"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert mock.stream_analysis_called is True


def test_ai_report_page_vllm_unavailable(monkeypatch, client):
    """POST /api/v1/ai-report-page возвращает 502, когда vLLM недоступен."""
    mock = _MockVllmClient(should_fail=True)
    monkeypatch.setattr("main.vllm_client", mock)
    image_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    response = client.post(
        "/api/v1/ai-report-page",
        files={"image": ("page.png", image_bytes, "image/png")},
        data={"system_prompt": "проанализируй страницу"},
    )
    assert response.status_code == 502


def test_ai_report_page_vllm_mocked(monkeypatch, client):
    """POST /api/v1/ai-report-page работает с mocked vLLM и возвращает SSE-поток."""
    mock = _MockVllmClient(should_fail=False)
    monkeypatch.setattr("main.vllm_client", mock)
    image_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    response = client.post(
        "/api/v1/ai-report-page",
        files={"image": ("page.png", image_bytes, "image/png")},
        data={"system_prompt": "проанализируй страницу"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert mock.stream_analysis_with_image_called is True
