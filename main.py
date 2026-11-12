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

import asyncio
import base64
import json
import logging
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
from services.vllm_client import VllmClientError, sanitize_error_text, vllm_client

logger = logging.getLogger(__name__)

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


# --- Контракт потоковых ответов (SSE) ---

#: Заголовки SSE-ответа: запрещаем буферизацию на реверс-прокси (Nginx),
#: иначе кадры ответа (в том числе кадр ошибки) приходят с задержкой.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse_data(text: str) -> bytes:
    """Собрать SSE-кадр с фрагментом текста ответа модели."""
    return f"data: {json.dumps(text, ensure_ascii=False)}\n\n".encode("utf-8")


def _sse_error(message: str) -> bytes:
    """Собрать SSE-кадр с ошибкой: именованное событие `error` и JSON-полезная нагрузка."""
    payload = json.dumps({"error": message}, ensure_ascii=False)
    return f"event: error\ndata: {payload}\n\n".encode("utf-8")


def _public_error_message(exc: Exception) -> str:
    """Сообщение об ошибке для пользователя — без внутренних сведений.

    Текст ошибки, формируемый клиентом, уже безопасный; дополнительная
    маскировка на границе ответа защищает от утечки, если источник ошибки
    изменится (например, появится новый тип исключения).
    """
    return sanitize_error_text(
        str(exc),
        api_url=settings.VLLM_API_URL,
        api_key=settings.VLLM_API_KEY,
    )


async def _open_sse_stream(
    events: AsyncIterator[str],
) -> tuple[AsyncIterator[str], str | None]:
    """«Прогреть» поток ИИ-модели: получить первый фрагмент до отправки заголовков.

    Позволяет представить сбой до начала генерации кодом ответа HTTP 502:
    маршрут вызывает помощник до создания `StreamingResponse`, поэтому ошибка
    ещё не «ушла» в тело ответа.

    Args:
        events: Асинхронный итератор фрагментов ответа модели.

    Returns:
        Кортеж (итератор, первый фрагмент). Первый фрагмент — None, если
        модель не вернула ни одного фрагмента (пустой, но успешный ответ).

    Raises:
        Любое исключение, возникшее при установлении соединения или при
        получении первого фрагмента: вызывающий код превращает его в 502.
    """
    try:
        first = await anext(events)
    except StopAsyncIteration:
        # Модель не вернула ни одного фрагмента — пустой, но успешный ответ.
        return events, None
    return events, first


async def _stream_sse(
    events: AsyncIterator[str],
    first: str | None = None,
) -> AsyncIterator[bytes]:
    """Оборачивать асинхронный итератор строк в SSE-формат (data: ...\\n\\n).

    Ошибка во время стрима передаётся кадром `event: error`, после чего поток
    закрывается штатно. Проброс исключения наружу оборвал бы HTTP-ответ:
    клиент не получил бы ни причины сбоя, ни ранее переданных фрагментов.

    Args:
        events: Асинхронный итератор фрагментов ответа модели.
        first: Первый фрагмент, уже полученный при «прогреве» потока.

    Yields:
        Байты SSE-кадров: `data: <фрагмент>` либо `event: error` + `data: {...}`.
    """
    try:
        if first is not None:
            yield _sse_data(first)
        async for text in events:
            yield _sse_data(text)
    except VllmClientError as exc:
        logger.exception("Сбой ИИ-модели во время потоковой генерации")
        yield _sse_error(_public_error_message(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Непредвиденный сбой во время потоковой генерации")
        yield _sse_error("Непредвиденная ошибка при формировании ответа ИИ-модели")
    finally:
        # Закрываем upstream-поток при отмене запроса или обрыве соединения:
        # иначе соединение с ИИ-моделью удерживается до сборки мусора.
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            try:
                # shield: отмена задачи не должна помешать закрытию потока.
                await asyncio.shield(aclose())
            except Exception:  # noqa: BLE001
                logger.debug("Не удалось закрыть поток ИИ-модели", exc_info=True)


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
    Ответ: JSON со структурой left_panel/right_panel (HTML + блоки + координаты).
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

    Контракт ошибок: сбой до первого фрагмента — HTTP 502 (заголовки ответа
    ещё не отправлены), сбой во время стрима — HTTP 200 и кадр `event: error`
    в потоке, после которого поток закрывается штатно.
    """
    try:
        events = vllm_client.stream_analysis(prompt)
        # «Прогрев»: первый фрагмент читается до отправки заголовков ответа,
        # поэтому сбой на этапе подключения к модели становится HTTP 502.
        events, first = await _open_sse_stream(events)
    except VllmClientError as exc:
        raise HTTPException(status_code=502, detail=_public_error_message(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Непредвиденная ошибка при подготовке ответа ИИ-модели")
        raise HTTPException(status_code=500, detail="Ошибка при обращении к ИИ-модели")
    return StreamingResponse(
        _stream_sse(events, first),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


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

    Контракт ошибок тот же, что у `/api/v1/analyze`: сбой до первого
    фрагмента — HTTP 502, сбой во время стрима — кадр `event: error`.
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
        # «Прогрев»: первый фрагмент читается до отправки заголовков ответа.
        events, first = await _open_sse_stream(events)
    except VllmClientError as exc:
        raise HTTPException(status_code=502, detail=_public_error_message(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка при формировании отчета по странице")
        raise HTTPException(
            status_code=500, detail="Ошибка при формировании отчета по странице"
        )
    return StreamingResponse(
        _stream_sse(events, first),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
