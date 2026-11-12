"""Асинхронный клиент для взаимодействия с vLLM (Qwen3-VL-8B).

Использует_openai_ клиент, настроенный на эндпоинт vLLM (OpenAI-совместимый API).
Все настройки берутся из переменных окружения через ``config.settings``.
Поддерживает потоковую передачу ответа (streaming), которую бэкенд отдает
пользователю в реальном времени через FastAPI ``StreamingResponse`` (SSE)
в боковую панель "AI Аналитика".

Функции:
- analyze_changes(text_diff, coords) -> потоковый текстовый разбор изменений
- analyze_page(image_bytes, system_prompt) -> потоковый визуальный анализ страницы
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from config import settings


class VllmClientError(Exception):
    """Базовая ошибка взаимодействия с vLLM."""


class VllmClient:
    """Асинхронный клиент vLLM с поддержкой стриминга ответов."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_url = api_url or settings.VLLM_API_URL
        self.api_key = api_key or settings.VLLM_API_KEY or ""
        self.model = model or settings.VLLM_MODEL_NAME

        # OpenAI-совместимый клиент, указывающий на эндпоинт vLLM.
        # base_url указывает на /v1 эндпоинт vLLM, api_key — ключ из .env.
        self.client = AsyncOpenAI(
            base_url=self.api_url,
            api_key=self.api_key,
        )

    async def stream_analysis(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Потоково получить ответ от vLLM по текстовому промпту.

        Yields части ответа по мере генерации моделью, чтобы бэкенд мог
        передавать их пользователю в реальном времени (SSE) без полной
        буферизации.

        Args:
            prompt: Системный + пользовательский промпт для анализа.
            temperature: Температура генерации.
            max_tokens: Максимальное число токенов в ответе.

        Yields:
            Строковые фрагменты текстового ответа модели.

        Raises:
            VllmClientError: При ошибке связи с vLLM.
        """
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None) or ""
                if content:
                    yield content
        except Exception as exc:  # noqa: BLE001
            raise VllmClientError(
                f"Ошибка при потоковом анализе через vLLM ({self.api_url}): {exc}"
            ) from exc

    async def stream_analysis_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        image_mime_type: str = "image/png",
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Потоково получить ответ от VL-модели с изображением страницы.

        Используется для ИИ-отчета по странице: снимок canvas (или PNG,
        срендеренный бэкендом через PyMuPDF) отправляется вместе с
        системным промптом, чтобы Qwen3-VL проанализировала изменения с
        учетом визуального контекста (таблиц, сдвигов верстки).

        Args:
            system_prompt: Системный промпт для VL-модели.
            image_base64: Изображение страницы в base64.
            image_mime_type: MIME-тип изображения (по умолчанию image/png).
            temperature: Температура генерации.
            max_tokens: Максимальное число токенов в ответе.

        Yields:
            Строковые фрагменты текстового ответа модели.

        Raises:
            VllmClientError: При ошибке связи с vLLM.
        """
        image_url = f"data:{image_mime_type};base64,{image_base64}"
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": system_prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None) or ""
                if content:
                    yield content
        except Exception as exc:  # noqa: BLE001
            raise VllmClientError(
                f"Ошибка при потоковом визуальном анализе через vLLM ({self.api_url}): {exc}"
            ) from exc


# Синглтон клиента (инициализируется из окружения при первом импорте).
vllm_client = VllmClient()
