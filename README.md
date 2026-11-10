# file-compare-v2

Веб-приложение для гибридного сравнения двух версий PDF-документов:
визуальное сравнение в стиле Git Split Diff + ИИ-анализ изменений через
локальную VL-модель Qwen3-VL-8B (vLLM).

## Стек

- Бэкенд: Python 3.11, FastAPI (асинхронный), Uvicorn
- Обработка PDF: PyMuPDF (`fitz`)
- Алгоритм diff: Google `diff-match-patch`
- ИИ-анализ: асинхронный клиент `openai` к vLLM с потоковым ответом (StreamingResponse / SSE)
- Фронтенд: HTML5, TailwindCSS, Vanilla JavaScript, pdf.js (через CDN)

## Структура проекта

```
file_compare_v2/
├── main.py              # Точка входа FastAPI, CORS, роуты (включая SSE для стриминга vLLM)
├── config.py            # Чтение настроек из .env с дефолтными значениями
├── requirements.txt     # Зависимости Python
├── .env.example         # Публичный шаблон переменных окружения
├── .env                 # Реальные секреты (создаётся локально, не попадает в Git)
├── .gitignore           # Игнорируемые пути (в т.ч. .venv/, .env, input/)
├── README.md            # Этот файл
├── services/
│   ├── __init__.py
│   ├── pdf_handler.py   # Извлечение текста и координат через PyMuPDF
│   ├── diff_engine.py   # Логика Git Split Diff (деление EQUAL/INSERT/DELETE)
│   └── vllm_client.py   # Асинхронный клиент vLLM со стримингом
├── static/
│   ├── index.html       # Интерфейс (две панели Split Diff + боковая панель ИИ)
│   ├── app.js           # Логика загрузки файлов, DOM diff, скроллинг, стриминг ИИ
│   └── styles.css       # Стили (Tailwind + кастомные для подсветки)
├── .venv/               # Изолированное виртуальное окружение (игнорируется в Git)
└── input/               # Папка пользовательских файлов (игнорируется проектом)
```

> **Папка `input/` содержит пользовательские файлы PDF для сравнения.**
> Она не является частью кода проекта и игнорируется в `.gitignore` и в документации.

## Установка и запуск

### 1. Создать виртуальное окружение `.venv/`

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Unix/macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Настроить переменные окружения

Скопируйте шаблон и заполните реальные значения:

```bash
cp .env.example .env
# отредактируйте .env, указав VLLM_API_URL, VLLM_API_KEY и т.д.
```

Файл `.env` с реальными секретами не попадает в Git (записан в `.gitignore`).
Если `.env` отсутствует, приложение использует значения по умолчанию из `config.py`.

### 4. Запустить приложение

```bash
uvicorn main:app --reload
```

Приложение будет доступно по адресу `http://localhost:8000` (или по настройкам
`FASTAPI_HOST` / `FASTAPI_PORT` из `.env`).

## Docker-совместимость

Код разработан так, чтобы быть готовым к контейнеризации (Docker) и работе
за реверс-прокси Nginx:
- все настройки берутся из `.env`;
- на фронтенде используются только относительные пути AJAX-запросов (`/api/v1/...`);
- статические файлы лежат в `static/`.

Dockerfile, docker-compose и конфиги Nginx добавляются отдельно (позже).

## Правила ветвления и Pull-Request (обязательно для всего проекта)

**Не коммитить напрямую в `main`.** Ветка `main` защищена — вливание в неё возможно
только через pull-request.

1. **Каждое изменение — в новую ветку** от `main` (`feature/...`, `fix/...`,
   `docs/...`, `chore/...`).
2. **Pull-request обязателен** перед вливанием в `main`.
3. **Вливание только после прохождения PR** (код-ревью и успешные проверки).
4. **После вливания PR побочная ветка удаляется** (локально и на удалённом сервере).

Пример рабочего процесса:

```bash
git checkout main
git pull origin main
git checkout -b feature/новая-задача
# ... изменения ...
git add -A
git commit -m "Описание изменений"
git push origin feature/новая-задача
# Создать PR в main, пройти ревью и проверки, влить
# После вливания:
git checkout main
git pull origin main
git branch -d feature/новая-задача
git push origin --delete feature/новая-задача
```

Подробные правила для агентов и разработчиков см. в `AGENTS.md`.
