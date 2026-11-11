"""Точка входа FastAPI для гибридного сравнения двух версий PDF-документов.

Маршруты:
- GET  /                    — пользовательский интерфейс (static/index.html)
- GET  /api/v1/health      — проверка работоспособности (без .env стартует)
- POST /api/v1/compare     — прием двух PDF, извлечение текста и координат
                              (PyMuPDF), вычисление Git Split Diff
                              (diff-match-patch), возврат JSON для левой и
                              правой панелей.
- POST /api/v1/analyze     — потоковый ИИ-анализ изменений через vLLM
                              (SSE / StreamingResponse) в боковую панель.
- POST /api/v1/ai-report-page — ИИ-отчет по странице: изображение + системный
                              промпт -> vLLM (Qwen3-VL-8B) -> потоковый ответ.

Все AJAX-пути относительные (/api/v1/...), приложение готово к работе за
реверс-прокси Nginx и в Docker-контейнерах.

Настройки строго берутся из переменных окружения (.env) через config.settings
с безопасным fallback на значения по умолчанию.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from services.diff_engine import compute_diff_with_coords
from services.pdf_handler import PdfHandlerError, extract_text_and_coords
from services.vllm_client import VllmClientError, vllm_client

#: Каталог статических файлов фронтенда — всегда рядом с main.py,
#: независимо от текущего рабочего каталога процесса.
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="file-compare-v2",
    description="Гибридное сравнение версий PDF: Git Split Diff + ИИ-анализ (vLLM Qwen3-VL-8B)",
    version="0.1.0",
)

# --- CORS: настраивается через переменную окружения CORS_ORIGINS ---
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача статических файлов фронтенда (каталог определяется от __file__).
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Роут: корневой маршрут приложения ---


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Отдать пользовательский интерфейс приложения.

    Тот же документ, что и статический файл `static/index.html`, — чтобы
    приложение открывалось по корневому адресу без 404.
    """
    return FileResponse(STATIC_DIR / "index.html")


# --- Вспомогательные функции ---


async def _save_upload_to_tmp(upload: UploadFile) -> str:
    """Сохранить загруженный файл во временный файл и вернуть путь к нему."""
    suffix = os.path.splitext(upload.filename or "upload")[1] or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(upload.file, tmp)
    finally:
        tmp.close()
    return tmp.name


async def _stream_sse(events: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Оборачивать асинхронный итератор строк в SSE-формат (data: ...\n\n)."""
    async for text in events:
        yield f"data: {json.dumps(text, ensure_ascii=False)}\n\n".encode("utf-8")


# --- Роут: проверка работоспособности ---


@app.get("/api/v1/health")
async def health() -> dict:
    """Проверка того, что бэкенд запущен и конфигурация прочитана.

    Не требует доступности vLLM endpoint — используется для подтверждения
    старта приложения без .env (дефолтные значения).

    Внутренний адрес эндпоинта ИИ-модели не раскрывается: вместо него
    возвращается признак наличия настройки подключения.
    """
    return {
        "status": "ok",
        "vllm_model": settings.VLLM_MODEL_NAME,
        "vllm_configured": settings.vllm_configured,
    }


# --- Роут: сравнение двух версий PDF ---


@app.post("/api/v1/compare")
async def compare(
    file_a: UploadFile = File(..., description="Исходная версия PDF"),
    file_b: UploadFile = File(..., description="Измененная версия PDF"),
) -> JSONResponse:
    """Сравнить два PDF-файла и вернуть Git Split Diff для двух панелей.

    Тело запроса: multipart/form-data с полями file_a и file_b.
    Ответ: JSON со结构ой left_panel/right_panel (HTML + блоки + координаты).
    """
    tmp_paths = []
    try:
        path_a = await _save_upload_to_tmp(file_a)
        path_b = await _save_upload_to_tmp(file_b)
        tmp_paths.extend([path_a, path_b])

        # Извлекаем текст и координаты слов/блоков для обеих версий.
        data_a = extract_text_and_coords(path_a)
        data_b = extract_text_and_coords(path_b)

        # Вычисляем diff с привязкой к координатам.
        result = compute_diff_with_coords(
            text_a=data_a["full_text"],
            text_b=data_b["full_text"],
            coords_a={"page_count": data_a["page_count"], "pages": data_a["pages"]},
            coords_b={"page_count": data_b["page_count"], "pages": data_b["pages"]},
        )

        return JSONResponse(
            {
                "ok": True,
                "left_panel": result["left_panel"],
                "right_panel": result["right_panel"],
                "coords_left": result["coords_left"],
                "coords_right": result["coords_right"],
                "summary": result["summary"],
                "meta": {
                    "file_a": file_a.filename,
                    "file_b": file_b.filename,
                    "page_count_a": data_a["page_count"],
                    "page_count_b": data_b["page_count"],
                },
            }
        )
    except PdfHandlerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка при сравнении: {exc}"
        )
    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except OSError:
                pass


# --- Роут: потоковый ИИ-анализ изменений (текстовый diff) ---


@app.post("/api/v1/analyze")
async def analyze(
    prompt: str = Form(..., description="Системный + пользовательский промпт для анализа"),
) -> StreamingResponse:
    """Потоковый ИИ-анализ изменений через vLLM (SSE).

    Ответ передается по частям по мере генерации моделью — пользователь видит
    разбор в реальном времени в боковой панели "AI Аналитика".
    """
    try:
        events = vllm_client.stream_analysis(prompt)
        return StreamingResponse(
            _stream_sse(events),
            media_type="text/event-stream",
        )
    except VllmClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# --- Роут: ИИ-отчет по странице (визуальный контекст) ---


@app.post("/api/v1/ai-report-page")
async def ai_report_page(
    image: UploadFile = File(..., description="Изображение страницы (PNG/JPEG)"),
    system_prompt: str = Form(
        ...,
        description="Системный промпт для VL-модели Qwen3-VL-8B",
    ),
) -> StreamingResponse:
    """ИИ-отчет по текущей странице с визуальным контекстом.

    Принимает снимок canvas (или PNG, срендеренный бэкендом через PyMuPDF)
    и системный промпт, отправляет изображение в vLLM (Qwen3-VL-8B) и
    возвращает текстовый разбор изменений с учетом таблиц и сдвигов верстки.
    """
    try:
        image_bytes = await image.read()
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        mime = image.content_type or "image/png"
        events = vllm_client.stream_analysis_with_image(
            system_prompt=system_prompt,
            image_base64=image_b64,
            image_mime_type=mime,
        )
        return StreamingResponse(
            _stream_sse(events),
            media_type="text/event-stream",
        )
    except VllmClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Ошибка при формировании отчета по странице: {exc}"
        )
