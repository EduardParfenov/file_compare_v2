"""Извлечение текста и координат из PDF-файлов через PyMuPDF (fitz).

Отвечает за:
- извлечение плоского текста каждой страницы;
- извлечение координат слов и текстовых блоков (X, Y, ширина, высота)
  через page.get_text("words") и page.get_text("blocks") для наложения
  прозрачного diff-слоя поверх виртуальной подложки страниц;
- рендер конкретной страницы в PNG (байты) для ИИ-отчета по странице
  с визуальным контекстом (таблицы, сдвиги верстки).

Все функции работают с путями к файлам и возвращают структуры, удобные для
передачи на фронтенд вместе с результатом diff.
"""

from __future__ import annotations

import fitz  # PyMuPDF


class PdfHandlerError(Exception):
    """Базовая ошибка обработки PDF."""


def extract_text_and_coords(pdf_path: str) -> dict:
    """Извлечь текст и координаты всех элементов со страниц PDF.

    Args:
        pdf_path: Путь к PDF-файлу.

    Returns:
        Словарь со структурой:
        {
            "page_count": int,
            "pages": [
                {
                    "page_number": int,      # 1-based
                    "text": str,             # плоский текст страницы
                    "width": float,          # ширина страницы (pt)
                    "height": float,         # высота страницы (pt)
                    "words": [               # координаты отдельных слов
                        {
                            "x0": float, "y0": float, "x1": float, "y1": float,
                            "word": str,
                            "block": int, "line": int, "word_no": int
                        },
                        ...
                    ],
                    "blocks": [              # координаты текстовых блоков
                        {
                            "x0": float, "y0": float, "x1": float, "y1": float,
                            "text": str,
                            "block_no": int, "block_type": int
                        },
                        ...
                    ]
                },
                ...
            ],
            "full_text": str                 # конкатенация текста всех страниц
        }

    Raises:
        PdfHandlerError: Если файл не может быть открыт или не содержит
            текстового слоя (отсканированный документ).
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        raise PdfHandlerError(f"Не удалось открыть PDF '{pdf_path}': {exc}") from exc

    pages_data = []
    full_text_parts = []
    global_char_offset = 0  # накопленное смещение символов от начала документа

    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        rect = page.rect
        text = page.get_text("text") or ""
        full_text_parts.append(text)

        # Координаты отдельных слов (для точного размещения diff-слоя)
        # Каждое слово получает глобальные символьные индексы global_char_start /
        # global_char_end — абсолютное смещение от начала документа сквозь все страницы.
        raw_words = page.get_text("words") or []
        words = []
        page_char_offset = 0  # позиция внутри текста текущей страницы
        for entry in raw_words:
            # fitz возвращает (x0, y0, x1, y1, word, block, line, word_no)
            word_text = entry[4]
            # Ищем слово в тексте страницы, начиная с текущего позиции,
            # чтобы корректно обрабатывать повторяющиеся слова.
            idx = text.find(word_text, page_char_offset)
            if idx == -1:
                # слово не найдено — используем приблизительное смещение
                idx = page_char_offset
            global_char_start = global_char_offset + idx
            global_char_end = global_char_start + len(word_text)
            page_char_offset = idx + len(word_text)
            words.append(
                {
                    "x0": float(entry[0]),
                    "y0": float(entry[1]),
                    "x1": float(entry[2]),
                    "y1": float(entry[3]),
                    "word": word_text,
                    "block": int(entry[5]),
                    "line": int(entry[6]),
                    "word_no": int(entry[7]),
                    "global_char_start": int(global_char_start),
                    "global_char_end": int(global_char_end),
                }
            )

        # Сдвигаем глобальное смещение на длину текста страницы плюс разделитель "\n"
        global_char_offset += len(text) + 1

        # Координаты текстовых блоков (для привязки скроллинга к якорям)
        raw_blocks = page.get_text("blocks") or []
        blocks = []
        for entry in raw_blocks:
            # fitz возвращает (x0, y0, x1, y1, text, block_no, block_type)
            blocks.append(
                {
                    "x0": float(entry[0]),
                    "y0": float(entry[1]),
                    "x1": float(entry[2]),
                    "y1": float(entry[3]),
                    "text": entry[4],
                    "block_no": int(entry[5]),
                    "block_type": int(entry[6]),
                }
            )

        pages_data.append(
            {
                "page_number": page_number,
                "text": text,
                "width": float(rect.width),
                "height": float(rect.height),
                "words": words,
                "blocks": blocks,
            }
        )

    doc.close()

    full_text = "\n".join(full_text_parts)

    if not full_text.strip():
        raise PdfHandlerError(
            f"PDF '{pdf_path}' не содержит текстового слоя (вероятно, отсканированный документ)."
        )

    return {
        "page_count": len(pages_data),
        "pages": pages_data,
        "full_text": full_text,
    }


def render_page_to_png(pdf_path: str, page_number: int) -> bytes:
    """Рендер указанной страницы PDF в PNG (байты) для ИИ-отчета по странице.

    Args:
        pdf_path: Путь к PDF-файлу.
        page_number: Номер страницы (1-based).

    Returns:
        Байты PNG-изображения страницы.

    Raises:
        PdfHandlerError: Если страница не существует или не удалось отрендерить.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        raise PdfHandlerError(f"Не удалось открыть PDF '{pdf_path}': {exc}") from exc

    if page_number < 1 or page_number > len(doc):
        page_count = len(doc)
        doc.close()
        raise PdfHandlerError(
            f"Страница {page_number} вне диапазона 1..{page_count} для '{pdf_path}'."
        )

    page = doc[page_number - 1]
    # Матрица масштаба 2.0 для достаточного разрешения изображения
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes
