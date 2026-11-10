"""Тесты для движка diff `services/diff_engine.py`.

Проверяются:
- разделение операций EQUAL/INSERT/DELETE на левую (`EQUAL`+`DELETE`) и
  правую (`EQUAL`+`INSERT`) панели (Git Split Diff);
- что INSERT не попадает на левую панель, а DELETE — на правую;
- presenza полей `coords_left`/`coords_right` в `compute_diff_with_coords`.
"""

from services.diff_engine import compute_diff, compute_diff_with_coords


def test_identical_texts_only_equal():
    """Одинаковые тексты — только EQUAL в обеих панелях, нет вставок/удалений."""
    text = "Hello World\nSame document."
    result = compute_diff(text, text)

    left_ops = [b["op"] for b in result["left_panel"]["blocks"]]
    right_ops = [b["op"] for b in result["right_panel"]["blocks"]]

    assert set(left_ops) == {"EQUAL"}
    assert set(right_ops) == {"EQUAL"}
    assert "INSERT" not in left_ops
    assert "DELETE" not in right_ops
    assert result["summary"]["equal_chars"] == len(text)
    assert result["summary"]["inserted_chars"] == 0
    assert result["summary"]["deleted_chars"] == 0


def test_deletion_only_left_panel():
    """Удалённый текст есть только на левой панели (DELETE), не на правой."""
    text_a = "Hello World\nDeleted line.\nKeep this."
    text_b = "Hello World\nKeep this."
    result = compute_diff(text_a, text_b)

    left_ops = [b["op"] for b in result["left_panel"]["blocks"]]
    right_ops = [b["op"] for b in result["right_panel"]["blocks"]]

    assert "DELETE" in left_ops
    assert "DELETE" not in right_ops
    assert "INSERT" not in left_ops
    assert result["summary"]["deleted_chars"] > 0
    assert result["summary"]["inserted_chars"] == 0


def test_insertion_only_right_panel():
    """Добавленный текст есть только на правой панели (INSERT), не на левой."""
    text_a = "Hello World\nKeep this."
    text_b = "Hello World\nInserted line.\nKeep this."
    result = compute_diff(text_a, text_b)

    left_ops = [b["op"] for b in result["left_panel"]["blocks"]]
    right_ops = [b["op"] for b in result["right_panel"]["blocks"]]

    assert "INSERT" in right_ops
    assert "INSERT" not in left_ops
    assert "DELETE" not in left_ops
    assert result["summary"]["inserted_chars"] > 0
    assert result["summary"]["deleted_chars"] == 0


def test_mixed_changes():
    """Одновременные удаление и вставка разделяются по панелям корректно."""
    text_a = "Common start\nRemoved part.\nCommon end."
    text_b = "Common start\nAdded part.\nCommon end."
    result = compute_diff(text_a, text_b)

    left_text = result["left_panel"]["html"]
    right_text = result["right_panel"]["html"]

    # Удалённый фрагмент есть слева (diff-match-patch может разбивать слова,
    # поэтому проверяем фрагмент "Remov", а не всю строку "Removed part").
    assert "Remov" in left_text
    assert "bg-red-500/30" in left_text
    # Добавленный фрагмент есть справа
    assert "Add" in right_text
    assert "bg-green-500/30" in right_text
    # Неизменённый текст есть в обеих панелях
    assert "Common start" in left_text
    assert "Common start" in right_text
    assert "Common end" in left_text
    assert "Common end" in right_text


def test_empty_texts():
    """Пустые тексты возвращают пустые панели без ошибок."""
    result = compute_diff("", "")
    assert result["left_panel"]["blocks"] == []
    assert result["right_panel"]["blocks"] == []
    assert result["summary"]["equal_chars"] == 0
    assert result["summary"]["inserted_chars"] == 0
    assert result["summary"]["deleted_chars"] == 0


def test_text_only_in_b_is_insert():
    """Весь текст только во второй версии — всё это INSERT на правой панели."""
    result = compute_diff("", "New content here.")
    right_ops = [b["op"] for b in result["left_panel"]["blocks"]]
    assert right_ops == []
    right_panel_ops = [b["op"] for b in result["right_panel"]["blocks"]]
    assert "INSERT" in right_panel_ops
    assert "DELETE" not in right_panel_ops


def test_text_only_in_a_is_delete():
    """Весь текст только в первой версии — всё это DELETE на левой панели."""
    result = compute_diff("Old content here.", "")
    left_ops = [b["op"] for b in result["left_panel"]["blocks"]]
    assert "DELETE" in left_ops
    assert "INSERT" not in left_ops
    right_panel_ops = [b["op"] for b in result["right_panel"]["blocks"]]
    assert right_panel_ops == []


def test_compute_diff_with_coords_present():
    """`compute_diff_with_coords` возвращает поля coords_left и coords_right."""
    result = compute_diff_with_coords(
        "Hello World",
        "Hello World",
        coords_a={"page_count": 1, "pages": []},
        coords_b={"page_count": 1, "pages": []},
    )
    assert "coords_left" in result
    assert "coords_right" in result
    assert result["coords_left"] == {"page_count": 1, "pages": []}
    assert result["coords_right"] == {"page_count": 1, "pages": []}


def test_compute_diff_with_coords_defaults_empty():
    """Без переданных координат coords_left/coords_right — пустые словари."""
    result = compute_diff_with_coords("A", "B")
    assert result["coords_left"] == {}
    assert result["coords_right"] == {}
