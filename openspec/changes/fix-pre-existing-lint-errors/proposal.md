## Why

Добавление шагов `ruff check` и `ruff format --check` в конвейер CI (change `ci-pipeline-completeness-review`, backlog пункт P2.11b) раскрыло пред-existing нарушения стиля в существующем коде: неиспользуемые импорты и переменные. Пока они не исправлены, проверка `pytest` на PR #10 проваливается на этапе `ruff check`, а ruleset ветки `main` требует статус SUCCESS перед слиянием. Нужно привести код в соответствие с линтером, чтобы конвейер прошёл и PR можно было слить.

## What Changes

- `services/vllm_client.py`: удалить неиспользуемый импорт `os` (F401).
- `tests/test_frontend_diff_mapping.py`: удалить неиспользуемый импорт `pytest` (F401) и неиспользуемые присваивания переменной `end_idx` (F841, 6 мест).
- `tests/test_main.py`: удалить неиспользуемые импорты `types.SimpleNamespace`, `typing.AsyncIterator`, `pytest` (F401).
- `ruff.toml`: снять временные `per-file-ignores` для этих трёх файлов, так как нарушения устранены (игноры были временными, см. комментарии в файле и backlog P2.11b).
- Проверить: `ruff check .` проходит без ошибок; `pytest` зелёный.

## Capabilities

Это чистая очистка кода / tooling-изменение: поведение системы не меняется, новых возможностей и изменений требований нет. Соответственно спецификации поведения не требуются — `.openspec.yaml` помечает `skip_specs: true`.

### New Capabilities

(отсутствуют)

### Modified Capabilities

(отсутствуют)

## Impact

Затронуты файлы: `services/vllm_client.py`, `tests/test_frontend_diff_mapping.py`, `tests/test_main.py`, `ruff.toml`.

Публичное API и поведение не меняются. Конвейер CI (`pytest` + `ruff check`) должен стать зелёным, что разблокирует слияние PR #10. Внешне заметного поведения не меняется (внутренний URL vLLM по-прежнему не раскрывается, CORS и маршруты без изменений).
