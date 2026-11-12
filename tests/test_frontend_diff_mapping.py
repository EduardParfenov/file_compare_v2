"""Тесты для логики маппинга слов на операции diff во фронтенде (`static/app.js`).

Проверяется алгоритм `mapWordsToOps`:
- использование реальных имён полей бэкенда (`global_char_start`,
  `global_char_end`, `word`);
- сквозной итератор `blockIdx`, не сбрасывающийся в 0 в начале каждой
  страницы (переносится между страницами);
- пересечение диапазонов слова и блока diff (`wStart < b.char_end &&
  wEnd > b.char_start`);
- приоритет не-EQUAL операций (DELETE/INSERT над EQUAL);
- формирование CSS-классов `.diff-word.delete` / `.diff-word.insert` /
  `.diff-word.equal` для совместимости с `insertDiffSpacers`.

Реализация алгоритма портирована на Python для тестирования под pytest,
так как `static/app.js` — ES-модуль браузера и не запускается напрямую в
pytest.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Порт алгоритма mapWordsToOps на Python (аналогично static/app.js)
# ---------------------------------------------------------------------------

def map_words_to_ops(words, blocks, start_block_idx=0):
    """Сопоставить каждое слово с операцией diff (порт JS-функции).

    Args:
        words: список словарей с полями global_char_start, global_char_end, word
        blocks: список словарей с полями char_start, char_end, op
        start_block_idx: стартовый индекс блока (сквозной итератор)

    Returns:
        (updated_words, end_block_idx) — слова с полем op и обновлённый blockIdx
    """
    block_idx = start_block_idx
    for w in words:
        word_global_start = w["global_char_start"]
        word_global_end = w["global_char_end"]
        word_op = "EQUAL"

        # Пропускаем блоки, которые заканчиваются до начала слова.
        while (
            block_idx < len(blocks)
            and blocks[block_idx]["char_end"] <= word_global_start
        ):
            block_idx += 1

        # Проверяем все блоки, которые пересекаются с диапазоном слова.
        # Приоритет отдаём не-EQUAL операциям (DELETE/INSERT над EQUAL).
        probe_idx = block_idx
        while (
            probe_idx < len(blocks)
            and blocks[probe_idx]["char_start"] < word_global_end
        ):
            block = blocks[probe_idx]
            if block["op"] != "EQUAL":
                word_op = block["op"]
            probe_idx += 1

        w["op"] = word_op

    return block_idx


def diff_class(op: str) -> str:
    """Аналог выбора CSS-класса в buildDiffWordsHtml (static/app.js)."""
    if op == "DELETE":
        return "diff-word delete"
    if op == "INSERT":
        return "diff-word insert"
    return "diff-word equal"


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

def test_map_words_to_ops_uses_backend_field_names():
    """Реальные имена полей бэкенда: global_char_start, global_char_end, word."""
    words = [
        {"global_char_start": 0, "global_char_end": 5, "word": "Hello"},
        {"global_char_start": 6, "global_char_end": 11, "word": "World"},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 11},
    ]
    end_idx = map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "EQUAL"
    assert words[1]["op"] == "EQUAL"
    # blockIdx не продвигается, так как один блок перекрывает оба слова
    # (char_end=11 не <= word_global_start=6 для второго слова)
    assert end_idx == 0


def test_map_words_to_ops_delete_highlighted():
    """Слово, попадающее в блок DELETE, помечается как DELETE."""
    words = [
        {"global_char_start": 0, "global_char_end": 7, "word": "Removed"},
    ]
    blocks = [
        {"op": "DELETE", "char_start": 0, "char_end": 7},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "DELETE"
    assert diff_class(words[0]["op"]) == "diff-word delete"


def test_map_words_to_ops_insert_highlighted():
    """Слово, попадающее в блок INSERT, помечается как INSERT."""
    words = [
        {"global_char_start": 0, "global_char_end": 7, "word": "Added"},
    ]
    blocks = [
        {"op": "INSERT", "char_start": 0, "char_end": 7},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "INSERT"
    assert diff_class(words[0]["op"]) == "diff-word insert"


def test_map_words_to_ops_equal_not_transparent():
    """EQUAL-слово имеет класс .equal (текст видимый, не text-transparent)."""
    words = [
        {"global_char_start": 0, "global_char_end": 5, "word": "Keep"},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 5},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "EQUAL"
    assert diff_class(words[0]["op"]) == "diff-word equal"


def test_block_idx_not_reset_between_pages():
    """blockIdx переносится между страницами, не сбрасывается в 0."""
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 5},
        {"op": "DELETE", "char_start": 5, "char_end": 10},
        {"op": "EQUAL", "char_start": 10, "char_end": 15},
    ]

    # Страница 1: слово в конце диапазона блоков — blockIdx продвигается вперёд
    words_page1 = [
        {"global_char_start": 10, "global_char_end": 15, "word": "Page1Word"},
    ]
    end_idx_p1 = map_words_to_ops(words_page1, blocks, 0)
    # blockIdx продвинулся на 2 (мимо первых двух блоков, которые заканчиваются до 10)
    assert end_idx_p1 == 2
    assert words_page1[0]["op"] == "EQUAL"

    # Страница 2: начинаем с end_idx_p1=2, не с 0
    words_page2 = [
        {"global_char_start": 16, "global_char_end": 20, "word": "Page2Word"},
    ]
    end_idx_p2 = map_words_to_ops(words_page2, blocks, end_idx_p1)
    # blockIdx продолжил с 2, а не сбросился в 0
    assert end_idx_p2 == 3
    assert words_page2[0]["op"] == "EQUAL"


def test_block_idx_advances_past_blocks_on_first_page():
    """На первой странице blockIdx продвигается мимо пройденных блоков."""
    words = [
        {"global_char_start": 10, "global_char_end": 15, "word": "Target"},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 5},
        {"op": "DELETE", "char_start": 5, "char_end": 10},
        {"op": "EQUAL", "char_start": 10, "char_end": 15},
    ]
    end_idx = map_words_to_ops(words, blocks, 0)
    # blockIdx продвинулся на 2 (мимо EQUAL[0,5] и DELETE[5,10], которые заканчиваются до 10)
    assert end_idx == 2
    assert words[0]["op"] == "EQUAL"


def test_intersection_partial_overlap_delete():
    """Частичное пересечение слова с блоком DELETE — слово помечается DELETE."""
    # Слово охватывает символы 5-15, блок DELETE охватывает 8-12
    words = [
        {"global_char_start": 5, "global_char_end": 15, "word": "PartialMatch"},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 5},
        {"op": "DELETE", "char_start": 8, "char_end": 12},
        {"op": "EQUAL", "char_start": 12, "char_end": 20},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "DELETE"
    assert diff_class(words[0]["op"]) == "diff-word delete"


def test_intersection_partial_overlap_insert():
    """Частичное пересечение слова с блоком INSERT — слово помечается INSERT."""
    words = [
        {"global_char_start": 5, "global_char_end": 15, "word": "PartialMatch"},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 5},
        {"op": "INSERT", "char_start": 8, "char_end": 12},
        {"op": "EQUAL", "char_start": 12, "char_end": 20},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "INSERT"
    assert diff_class(words[0]["op"]) == "diff-word insert"


def test_delete_priority_over_equal():
    """Если слово пересекает EQUAL и DELETE — приоритет у DELETE."""
    words = [
        {"global_char_start": 5, "global_char_end": 15, "word": "Mixed"},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 10},
        {"op": "DELETE", "char_start": 8, "char_end": 12},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "DELETE"
    assert diff_class(words[0]["op"]) == "diff-word delete"


def test_no_intersection_remains_equal():
    """Если слово не пересекает никакой блок — остаётся EQUAL."""
    words = [
        {"global_char_start": 20, "global_char_end": 25, "word": "Isolated"},
    ]
    blocks = [
        {"op": "DELETE", "char_start": 0, "char_end": 10},
    ]
    map_words_to_ops(words, blocks, 0)
    assert words[0]["op"] == "EQUAL"
    assert diff_class(words[0]["op"]) == "diff-word equal"


def test_diff_class_insert_found_by_spacers():
    """Селектор .diff-word.insert находит элементы с классом insert."""
    assert "insert" in diff_class("INSERT")
    assert "delete" not in diff_class("INSERT")


def test_diff_class_delete_found_by_spacers():
    """Селектор .diff-word.delete находит элементы с классом delete."""
    assert "delete" in diff_class("DELETE")
    assert "insert" not in diff_class("DELETE")


def test_diff_class_equal_not_transparent():
    """Класс .equal не делает текст прозрачным."""
    cls = diff_class("EQUAL")
    assert "equal" in cls
    assert "delete" not in cls
    assert "insert" not in cls


# ---------------------------------------------------------------------------
# Порт buildDiffWordsHtml из static/app.js (после hide-diff-text-layer)
# ---------------------------------------------------------------------------

def build_diff_words_html(words, blocks, start_block_idx=0):
    """Порт buildDiffWordsHtml (статику app.js) на Python для тестирования.

    После изменения: EQUAL не рендерится, DELETE/INSERT — пустой div без текста.
    """
    block_idx = start_block_idx
    html_parts = []
    for w in words:
        word_global_start = w["global_char_start"]
        word_global_end = w["global_char_end"]
        word_op = "EQUAL"

        while (
            block_idx < len(blocks)
            and blocks[block_idx]["char_end"] <= word_global_start
        ):
            block_idx += 1

        probe_idx = block_idx
        while (
            probe_idx < len(blocks)
            and blocks[probe_idx]["char_start"] < word_global_end
        ):
            block = blocks[probe_idx]
            if block["op"] != "EQUAL":
                word_op = block["op"]
            probe_idx += 1

        w["op"] = word_op

        if w["op"] == "EQUAL":
            continue

        cls = f"diff-word {'delete' if w['op'] == 'DELETE' else 'insert'}"
        left = round(w["x0"])
        top = round(w["y0"])
        width = round(w["x1"] - w["x0"])
        height = round(w["y1"] - w["y0"])
        html_parts.append(
            f'<div class="{cls}" style="left:{left}px;top:{top}px;width:{width}px;height:{height}px" title="{w["op"]}"></div>'
        )

    return "".join(html_parts), block_idx


# ---------------------------------------------------------------------------
# Тесты hide-diff-text-layer
# ---------------------------------------------------------------------------

def test_build_diff_words_html_equal_not_rendered():
    """EQUAL-слова не рендерятся на diff-слое (пустой HTML, текста нет)."""
    words = [
        {"global_char_start": 0, "global_char_end": 5, "word": "Keep", "x0": 10, "y0": 20, "x1": 40, "y1": 30},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 5},
    ]
    html, end_idx = build_diff_words_html(words, blocks, 0)
    assert html == ""
    assert words[0]["op"] == "EQUAL"


def test_build_diff_words_html_delete_rendered_without_text():
    """DELETE-слово рендерится как div с классом delete, без текстового contenuto."""
    words = [
        {"global_char_start": 0, "global_char_end": 7, "word": "Removed", "x0": 10, "y0": 20, "x1": 60, "y1": 30},
    ]
    blocks = [
        {"op": "DELETE", "char_start": 0, "char_end": 7},
    ]
    html, end_idx = build_diff_words_html(words, blocks, 0)
    assert "diff-word delete" in html
    assert "Removed" not in html  # текст слова не вставляется в DOM
    assert "left:10px" in html
    assert "top:20px" in html
    assert "width:50px" in html
    assert "height:10px" in html
    assert 'title="DELETE"' in html


def test_build_diff_words_html_insert_rendered_without_text():
    """INSERT-слово рендерится как div с классом insert, без текстового contenuto."""
    words = [
        {"global_char_start": 0, "global_char_end": 6, "word": "Added", "x0": 10, "y0": 20, "x1": 50, "y1": 30},
    ]
    blocks = [
        {"op": "INSERT", "char_start": 0, "char_end": 6},
    ]
    html, end_idx = build_diff_words_html(words, blocks, 0)
    assert "diff-word insert" in html
    assert "Added" not in html  # текст слова не вставляется в DOM
    assert "left:10px" in html
    assert 'title="INSERT"' in html


def test_build_diff_words_html_mixed_ops_no_text():
    """Смешанные операции: EQUAL пропускается, DELETE/INSERT рендерятся без текста."""
    words = [
        {"global_char_start": 0, "global_char_end": 4, "word": "Keep", "x0": 0, "y0": 0, "x1": 20, "y1": 10},
        {"global_char_start": 5, "global_char_end": 11, "word": "Removed", "x0": 25, "y0": 0, "x1": 60, "y1": 10},
        {"global_char_start": 12, "global_char_end": 16, "word": "Add", "x0": 65, "y0": 0, "x1": 85, "y1": 10},
    ]
    blocks = [
        {"op": "EQUAL", "char_start": 0, "char_end": 4},
        {"op": "DELETE", "char_start": 5, "char_end": 11},
        {"op": "INSERT", "char_start": 12, "char_end": 16},
    ]
    html, end_idx = build_diff_words_html(words, blocks, 0)
    assert "Keep" not in html
    assert "Removed" not in html
    assert "Add" not in html
    assert "diff-word delete" in html
    assert "diff-word insert" in html