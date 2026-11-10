"""Дифф-движок в стиле Git Split Diff на базе Google diff-match-patch.

Сравнивает текст А (исходная версия) и текст Б (измененная версия) и
разделяет операции EQUAL / INSERT / DELETE на два параллельных потока
отображения:

* Левая панель (исходный файл): только EQUAL (обычный текст) и DELETE
  (удаленный текст). Операции INSERT игнорируются, чтобы структура не
  разъезжалась.
* Правая панель (измененный файл): только EQUAL (обычный текст) и INSERT
  (добавленный текст). Операции DELETE игнорируются.

Возвращает JSON-структуру с двумя раздельными массивами/строками с
HTML-разметкой и метаданными для левой и правой панели соответственно.

Подсветка (классы Tailwind):
* Удаленные фрагменты (левая панель): `<span class="bg-red-500/30 line-through">`.
* Добавленные фрагменты (правая панель): `<span class="bg-green-500/30">`.
"""

from __future__ import annotations

import html
from dataclasses import asdict, dataclass
from typing import List

import diff_match_patch as dmp_module

# Константы операций diff_match_patch:
# DIFF_EQUAL = 0, DIFF_INSERT = 1, DIFF_DELETE = -1
DIFF_EQUAL = 0
DIFF_INSERT = 1
DIFF_DELETE = -1


@dataclass
class DiffBlock:
    """Один блок результата diff с типом операции и текстом."""

    op: str  # "EQUAL" | "INSERT" | "DELETE"
    text: str
    html: str  # HTML-разметка для вставки в соответствующую панель
    char_start: int  # Абсолютное смещение от начала текста этой панели
    char_end: int  # Абсолютное смещение от начала текста этой панели (конец)


def _escape(text: str) -> str:
    """Экранировать HTML-спецсимволы для безопасной вставки в DOM."""
    return html.escape(text, quote=False)


def _wrap_deleted(text: str) -> str:
    """Обернуть удаленный текст в подсветку красной с зачеркиванием (левая панель)."""
    return f'<span class="bg-red-500/30 line-through">{_escape(text)}</span>'


def _wrap_inserted(text: str) -> str:
    """Обернуть добавленный текст в подсветку зеленой (правая панель)."""
    return f'<span class="bg-green-500/30">{_escape(text)}</span>'


def compute_diff(text_a: str, text_b: str) -> dict:
    """Вычислить diff между текстом А и текстом Б в формате Git Split Diff.

    Args:
        text_a: Исходный текст (старая версия).
        text_b: Измененный текст (новая версия).

    Returns:
        Словарь со структурой:
        {
            "left_panel": {          # Исходная версия (левое окно)
                "blocks": [DiffBlock],  # только EQUAL и DELETE
                "html": str          # собранная HTML-разметка левой панели
            },
            "right_panel": {         # Измененная версия (правое окно)
                "blocks": [DiffBlock],  # только EQUAL и INSERT
                "html": str          # собранная HTML-разметка правой панели
            },
            "summary": {
                "equal_chars": int,
                "inserted_chars": int,
                "deleted_chars": int
            }
        }

    Левая панель содержит EQUAL и DELETE (INSERT игнорируется).
    Правая панель содержит EQUAL и INSERT (DELETE игнорируется).
    Неизмененный текст (EQUAL) присутствует в обеих панелях без подсветки.
    """
    dmp = dmp_module.diff_match_patch()
    diffs: List = dmp.diff_main(text_a, text_b)

    left_blocks: List[DiffBlock] = []
    right_blocks: List[DiffBlock] = []

    equal_chars = 0
    inserted_chars = 0
    deleted_chars = 0

    # Сквозные символьные смещения для каждой панели (независимые).
    left_char_offset = 0
    right_char_offset = 0

    for op_code, text in diffs:
        text_len = len(text)
        if op_code == DIFF_EQUAL:
            # Неизмененный текст — присутствует в обеих панелях без подсветки.
            escaped = _escape(text)
            left_blocks.append(
                DiffBlock(
                    op="EQUAL",
                    text=text,
                    html=escaped,
                    char_start=left_char_offset,
                    char_end=left_char_offset + text_len,
                )
            )
            right_blocks.append(
                DiffBlock(
                    op="EQUAL",
                    text=text,
                    html=escaped,
                    char_start=right_char_offset,
                    char_end=right_char_offset + text_len,
                )
            )
            equal_chars += text_len
            left_char_offset += text_len
            right_char_offset += text_len
        elif op_code == DIFF_DELETE:
            # Удаленный текст — только левая панель, красная подсветка + зачеркивание.
            left_blocks.append(
                DiffBlock(
                    op="DELETE",
                    text=text,
                    html=_wrap_deleted(text),
                    char_start=left_char_offset,
                    char_end=left_char_offset + text_len,
                )
            )
            deleted_chars += text_len
            left_char_offset += text_len
            # Правая панель: игнорируем.
        elif op_code == DIFF_INSERT:
            # Добавленный текст — только правая панель, зеленая подсветка.
            right_blocks.append(
                DiffBlock(
                    op="INSERT",
                    text=text,
                    html=_wrap_inserted(text),
                    char_start=right_char_offset,
                    char_end=right_char_offset + text_len,
                )
            )
            inserted_chars += text_len
            right_char_offset += text_len
            # Левая панель: игнорируем.

    left_html = "".join(block.html for block in left_blocks)
    right_html = "".join(block.html for block in right_blocks)

    return {
        "left_panel": {
            "blocks": [asdict(block) for block in left_blocks],
            "html": left_html,
        },
        "right_panel": {
            "blocks": [asdict(block) for block in right_blocks],
            "html": right_html,
        },
        "summary": {
            "equal_chars": equal_chars,
            "inserted_chars": inserted_chars,
            "deleted_chars": deleted_chars,
        },
    }


def compute_diff_with_coords(
    text_a: str,
    text_b: str,
    coords_a: dict | None = None,
    coords_b: dict | None = None,
) -> dict:
    """Вычислить diff с привязкой к координатам текстовых блоков.

    Расширяет compute_diff, добавляя координаты блоков из pdf_handler для
    каждой панели. Используется фронтендом для размещения текстовых элементов
    строго над своими визуальными позициями на странице (прозрачный diff-слой
    поверх подложки pdf.js).

    Args:
        text_a: Исходный текст.
        text_b: Измененный текст.
        coords_a: Координаты блоков исходного документа (из pdf_handler).
        coords_b: Координаты блоков измененного документа (из pdf_handler).

    Returns:
        Словарь, совместимый с compute_diff, плюс поля coords_left/coords_right.
    """
    result = compute_diff(text_a, text_b)
    result["coords_left"] = coords_a or {}
    result["coords_right"] = coords_b or {}
    return result
