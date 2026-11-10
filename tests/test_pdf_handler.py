"""Тесты для модуля обработки PDF `services/pdf_handler.py`.

Проверяются:
- `extract_text_and_coords`: возвращает плоский текст, координаты слов
  и блоков (X, Y, ширина, высота) через PyMuPDF;
- структура результата (page_count, pages, full_text);
- поля слов и блоков (x0, y0, x1, y1, global_char_start, global_char_end);
- поведение при отсутствии текстового слоя (PdfHandlerError, не ложные совпадения);
- `render_page_to_png` возвращает байты PNG.
"""

from services.pdf_handler import PdfHandlerError, extract_text_and_coords, render_page_to_png


def test_extract_text_and_coords_structure(pdf_a):
    """Результат содержит page_count, pages и full_text."""
    data = extract_text_and_coords(pdf_a)
    assert "page_count" in data
    assert "pages" in data
    assert "full_text" in data
    assert data["page_count"] >= 1
    assert isinstance(data["full_text"], str)
    assert len(data["full_text"]) > 0


def test_extract_text_and_coords_page_fields(pdf_a):
    """Каждая страница содержит text, width, height, words, blocks."""
    data = extract_text_and_coords(pdf_a)
    page = data["pages"][0]
    assert "page_number" in page
    assert "text" in page
    assert "width" in page
    assert "height" in page
    assert "words" in page
    assert "blocks" in page
    assert page["page_number"] == 1
    assert page["width"] > 0
    assert page["height"] > 0


def test_extract_text_and_coords_word_fields(pdf_a):
    """У каждого слова есть координаты и глобальные символьные индексы."""
    data = extract_text_and_coords(pdf_a)
    words = data["pages"][0]["words"]
    assert len(words) > 0
    word = words[0]
    for key in ("x0", "y0", "x1", "y1", "word", "block", "line", "word_no"):
        assert key in word
    assert isinstance(word["x0"], float)
    assert isinstance(word["y0"], float)
    assert isinstance(word["x1"], float)
    assert isinstance(word["y1"], float)
    assert word["x1"] > word["x0"]
    assert word["y1"] > word["y0"]
    assert isinstance(word["word"], str)
    assert len(word["word"]) > 0


def test_extract_text_and_coords_global_char_indices(pdf_a):
    """У каждого слова есть global_char_start и global_char_end."""
    data = extract_text_and_coords(pdf_a)
    words = data["pages"][0]["words"]
    for word in words:
        assert "global_char_start" in word
        assert "global_char_end" in word
        assert isinstance(word["global_char_start"], int)
        assert isinstance(word["global_char_end"], int)
        assert word["global_char_end"] > word["global_char_start"]


def test_extract_text_and_coords_block_fields(pdf_a):
    """У каждого текстового блока есть координаты и текст."""
    data = extract_text_and_coords(pdf_a)
    blocks = data["pages"][0]["blocks"]
    if len(blocks) > 0:
        block = blocks[0]
        for key in ("x0", "y0", "x1", "y1", "text", "block_no", "block_type"):
            assert key in block
        assert isinstance(block["text"], str)
        assert len(block["text"]) > 0


def test_full_text_contains_page_text(pdf_a):
    """full_text содержит текст каждой страницы."""
    data = extract_text_and_coords(pdf_a)
    for page in data["pages"]:
        assert page["text"] in data["full_text"]


def test_pdf_no_text_raises_error(pdf_no_text):
    """PDF без текстового слоя вызывает PdfHandlerError, а не ложные совпадения."""
    try:
        extract_text_and_coords(pdf_no_text)
    except PdfHandlerError:
        return
    raise AssertionError("Ожидалась PdfHandlerError для PDF без текстового слоя")


def test_render_page_to_png_returns_bytes(pdf_a):
    """render_page_to_png возвращает байты PNG-изображения."""
    png_bytes = render_page_to_png(pdf_a, 1)
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 0
    # PNG-сигнатура
    assert png_bytes[:4] == b"\x89PNG"


def test_render_page_to_png_invalid_page(pdf_a):
    """render_page_to_png вызывает PdfHandlerError для несуществующей страницы."""
    try:
        render_page_to_png(pdf_a, 999)
    except PdfHandlerError:
        return
    raise AssertionError("Ожидалась PdfHandlerError для несуществующей страницы")
