/*!
 * file-compare-v2 — фронтенд (static/app.js)
 *
 * Логика:
 *   - загрузка двух PDF-файлов и отправка на /api/v1/compare
 *   - рендер страниц через pdf.js в <canvas> (визуальная подложка)
 *   - размещение текстовых элементов строго над своими координатами
 *     на прозрачном diff-слое (координаты слов/блоков из бэкенда, PyMuPDF)
 *   - подсветка: левая панель — удаленные (DELETE, красный + зачеркивание),
 *     правая панель — добавленные (INSERT, зеленый)
 *   - умный синхронный скроллинг (lock-step) с привязкой к текстовым якорям
 *   - боковая панель ИИ-аналитики со стримингом ответа (SSE)
 *   - кнопка "Сгенерировать ИИ-отчет по странице" (скриншот canvas -> vLLM)
 *
 * Комментарии на русском языке.
 */

const API_BASE = ""; // относительные пути — готово к Nginx/Docker

const state = {
  pdfDocA: null,
  pdfDocB: null,
  pageCountA: 0,
  pageCountB: 0,
  diffResult: null,
  coordsLeft: null,
  coordsRight: null,
  renderedPagesA: new Map(), // pageNum -> {canvas, container, diffLayer}
  renderedPagesB: new Map(),
  activePageA: 1,
  activePageB: 1,
  isScrolling: false, // защита от рекурсии при синхронном скроллинге
  scale: 1.0, // масштаб рендера страниц (1 PDF-пойнт = 1 пиксель canvas)
};

// -------------------- Инициализация --------------------

export function initApp() {
  const fileA = document.getElementById("fileA");
  const fileB = document.getElementById("fileB");
  const btnCompare = document.getElementById("btnCompare");
  const statusBar = document.getElementById("statusBar");

  function updateCompareButton() {
    btnCompare.disabled = !(fileA.files.length && fileB.files.length);
  }
  fileA.addEventListener("change", updateCompareButton);
  fileB.addEventListener("change", updateCompareButton);
  updateCompareButton();

  btnCompare.addEventListener("click", () => {
    comparePdfs(fileA.files[0], fileB.files[0]);
  });

  //.scroll панелей
  const panelA = document.getElementById("panelA");
  const panelB = document.getElementById("panelB");

  panelA.addEventListener("scroll", () =>
    syncScroll(panelA, panelB, "A")
  );
  panelB.addEventListener("scroll", () =>
    syncScroll(panelB, panelA, "B")
  );

  // ИИ-кнопки
  document.getElementById("btnAiAnalyze").addEventListener("click", () => {
    runAiAnalysis();
  });
  document.getElementById("btnAiPageReport").addEventListener("click", () => {
    generateAiPageReport();
  });

  statusBar.textContent = "Готово к загрузке двух PDF-файлов.";
}

// -------------------- Сравнение PDF --------------------

async function comparePdfs(fileA, fileB) {
  const statusBar = document.getElementById("statusBar");
  const formData = new FormData();
  formData.append("file_a", fileA);
  formData.append("file_b", fileB);

  try {
    document.getElementById("btnCompare").disabled = true;
    statusBar.textContent = "Сравнение документов...";

    const response = await fetch(`${API_BASE}/api/v1/compare`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Ошибка ${response.status}`);
    }

    const result = await response.json();
    state.diffResult = result;
    state.coordsLeft = result.coords_left;
    state.coordsRight = result.coords_right;
    state.pageCountA = result.meta.page_count_a;
    state.pageCountB = result.meta.page_count_b;

    statusBar.textContent = `Сравнено: ${result.meta.file_a} ↔ ${result.meta.file_b} (стр. ${state.pageCountA} / ${state.pageCountB})`;

    // Загружаем PDF-документы в pdf.js и рендерим страницы
    await loadAndRenderPdf(fileA, "A");
    await loadAndRenderPdf(fileB, "B");

    // Наносим diff на оба окна
    applyDiffToPanel("A");
    applyDiffToPanel("B");

    // Вставляем спейсеры для синхронизации скроллинга противоположных окон
    insertDiffSpacers();

    // Активируем ИИ-кнопки
    document.getElementById("btnAiAnalyze").disabled = false;
    document.getElementById("btnAiPageReport").disabled = false;

    // Прокручиваем к первой странице
    scrollToPage("A", 1);
    scrollToPage("B", 1);
  } catch (err) {
    console.error(err);
    alert("Ошибка при сравнении: " + err.message);
    statusBar.textContent = "Ошибка при сравнении документов.";
  } finally {
    document.getElementById("btnCompare").disabled = !(document.getElementById("fileA").files.length && document.getElementById("fileB").files.length);
  }
}

async function loadAndRenderPdf(file, panelKey) {
  const arrayBuffer = await file.arrayBuffer();
  const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
  const pdfDoc = await loadingTask.promise;

  if (panelKey === "A") {
    state.pdfDocA = pdfDoc;
  } else {
    state.pdfDocB = pdfDoc;
  }

  const containerId = `canvasContainer${panelKey}`;
  const renderedMap = panelKey === "A" ? state.renderedPagesA : state.renderedPagesB;
  const pageCount = panelKey === "A" ? state.pageCountA : state.pageCountB;

  const container = document.getElementById(containerId);
  container.innerHTML = "";

  for (let i = 1; i <= pageCount; i++) {
    await renderPage(pdfDoc, i, container, panelKey, renderedMap);
  }
}

async function renderPage(pdfDoc, pageNum, container, panelKey, renderedMap) {
  const page = await pdfDoc.getPage(pageNum);
  const viewport = page.getViewport({ scale: state.scale });

  // Контейнер страницы
  const pageWrap = document.createElement("div");
  pageWrap.className = "page-wrap relative";
  pageWrap.dataset.pageNum = pageNum;

  // Canvas — визуальная подложка страницы (pdf.js)
  const canvas = document.createElement("canvas");
  canvas.className = "page-canvas";
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  // Отображаем в натуральную величину (1:1 с PDF-пойнтами при scale=1)
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;

  // Прозрачный diff-слой поверх canvas
  const diffLayer = document.createElement("div");
  diffLayer.className = "diff-layer";
  diffLayer.style.width = `${viewport.width}px`;
  diffLayer.style.height = `${viewport.height}px`;

  pageWrap.appendChild(canvas);
  pageWrap.appendChild(diffLayer);
  container.appendChild(pageWrap);

  // Рендер страницы на canvas
  const renderContext = {
    canvasContext: canvas.getContext("2d"),
    viewport,
  };
  await page.render(renderContext).promise;

  renderedMap.set(pageNum, { canvas, diffLayer, pageWrap, viewport, page });
}

// -------------------- Нанесение diff на панель --------------------

/**
 * Сопоставить каждое слово с операцией diff (EQUAL/DELETE/INSERT),
 * используя сквозные символьные индексы слов (global_char_start /
 * global_char_end) и сквозные символьные индексы блоков diff
 * (char_start / char_end).
 *
 * Слова на странице и блоки diff идут по возрастания своих start-индексов,
 * поэтому один проход с двумя указателями достаточно. Указатель блока
 * только двигается вперёд — без сброса на каждой странице.
 *
 * Параметр startBlockIdx позволяет переносить позицию итератора между
 * страницами: вместо сброса в 0 в начале каждой страницы мы продолжаем
 * с того же места в глобальном массиве блоков diffResult.
 *
 * Блоки diff (left_panel.blocks / right_panel.blocks) и слова имеют
 * согласованные системы координат: char_start/char_end блока измеряются
 * от начала текста панели, global_char_start/global_char_end слова — от
 * начала того же документа. Поэтому прямое сравнение диапазонов корректно.
 *
 * Возвращает обновлённое значение blockIdx для передачи на следующую страницу.
 *
 * @param {Array} words - слова страницы (с полями global_char_start, global_char_end, word)
 * @param {Array} blocks - блоки diff панели (с полями char_start, char_end, op)
 * @param {number} startBlockIdx - стартовый индекс блока (сквозной итератор)
 * @returns {number} обновлённый blockIdx
 */
function mapWordsToOps(words, blocks, startBlockIdx = 0) {
  let blockIdx = startBlockIdx;

  for (const w of words) {
    const wordGlobalStart = w.global_char_start;
    const wordGlobalEnd = w.global_char_end;
    let wordOp = "EQUAL";

    // Пропускаем блоки, которые заканчиваются до начала слова.
    while (
      blockIdx < blocks.length &&
      blocks[blockIdx].char_end <= wordGlobalStart
    ) {
      blockIdx++;
    }

    // Проверяем все блоки, которые пересекаются с диапазоном слова.
    // Приоритет отдаём не-EQUAL операциям (DELETE/INSERT над EQUAL).
    let probeIdx = blockIdx;
    while (
      probeIdx < blocks.length &&
      blocks[probeIdx].char_start < wordGlobalEnd
    ) {
      const block = blocks[probeIdx];
      if (block.op !== "EQUAL") {
        wordOp = block.op;
      }
      probeIdx++;
    }

    w.op = wordOp;
  }

  return blockIdx;
}

/**
 * Построить HTML-размещение слов на diff-слое для одной страницы одной панели.
 *
 * blockIdx — сквозной итератор по глобальному массиву блоков diffResult.
 * Он передаётся из applyDiffToPanel и возвращается обновлённым, чтобы
 * не сбрасываться в 0 на каждой странице.
 *
 * Генерация HTML сохраняет CSS-классы .diff-word.delete / .diff-word.insert /
 * .diff-word.equal, чтобы insertDiffSpacers мог находить селекторы
 * `.diff-word.delete` и `.diff-word.insert`, а текст EQUAL оставался
 * видимым (color: #111827 через .diff-word.equal).
 *
 * @param {number} pageNum - номер страницы (1-based)
 * @param {string} panelKey - "A" или "B"
 * @param {number} startBlockIdx - стартовый индекс блока (сквозной итератор)
 * @returns {{html: string, blockIdx: number}} HTML-разметка и обновлённый blockIdx
 */
function buildDiffWordsHtml(pageNum, panelKey, startBlockIdx = 0) {
  const coords = panelKey === "A" ? state.coordsLeft : state.coordsRight;
  const blocks = panelKey === "A"
    ? state.diffResult.left_panel.blocks
    : state.diffResult.right_panel.blocks;

  const pageInfo = coords.pages.find((p) => p.page_number === pageNum);
  if (!pageInfo) return { html: "", blockIdx: startBlockIdx };

  const words = pageInfo.words.slice(); // копия, чтобы не мутировать исходное
  // computeWordOffsets больше не нужен: глобальные индексы уже есть в словах
  // из ответа бэкенда (global_char_start / global_char_end).
  const endBlockIdx = mapWordsToOps(words, blocks, startBlockIdx);

  const vp = state.renderedPagesA.get(pageNum) ||
             state.renderedPagesB.get(pageNum);
  if (!vp) return { html: "", blockIdx: endBlockIdx };

  // Масштаб координат слов: 1 PDF-пойнт = 1 пиксель canvas при state.scale=1.
  // vp.viewport.width / 1 даёт ширину всей страницы в пунктах, а не коэффициент
  // масштаба, что переносит текст за пределы экрана.
  const scaleX = state.scale;
  const scaleY = state.scale;

  let html = "";
  for (const w of words) {
    // EQUAL не рендерится на diff-слое — текст уже нарисован на canvas подложкой pdf.js.
    if (w.op === "EQUAL") continue;
    const cls = `diff-word ${w.op === "DELETE" ? "delete" : "insert"}`;
    const left = Math.round(w.x0 * scaleX);
    const top = Math.round(w.y0 * scaleY);
    const width = Math.round((w.x1 - w.x0) * scaleX);
    const height = Math.round((w.y1 - w.y0) * scaleY);
    // Пустой бокс подсветки без текстового contenuto — дублирование букв поверх canvas убирается.
    html += `<div class="${cls}" style="left:${left}px;top:${top}px;width:${width}px;height:${height}px" title="${escapeHtml(w.op)}"></div>`;
  }
  return { html, blockIdx: endBlockIdx };
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function applyDiffToPanel(panelKey) {
  const renderedMap = panelKey === "A" ? state.renderedPagesA : state.renderedPagesB;
  const container = document.getElementById(`canvasContainer${panelKey}`);

  // Сквозной итератор по глобальному массиву блоков diffResult.
  // Переносится между страницами — не сбрасывается в 0 в начале каждой.
  let blockIdx = 0;

  // Проходим по всем page-wrap и наполняем их diff-слои
  container.querySelectorAll(".page-wrap").forEach((pageWrap) => {
    const pageNum = parseInt(pageWrap.dataset.pageNum, 10);
    const diffLayer = pageWrap.querySelector(".diff-layer");

    const { html, blockIdx: nextBlockIdx } = buildDiffWordsHtml(
      pageNum,
      panelKey,
      blockIdx
    );
    diffLayer.innerHTML = html;

    // Переносим обновлённый blockIdx на следующую страницу
    blockIdx = nextBlockIdx;
  });
}

/**
 * Вставляет блоки-заглушки (spacer) в противоположное окно при крупных
 * блоках вставки (INSERT) или удаления (DELETE), чтобы неизмененные
 * абзацы оставались на одной горизонтальной линии.
 *
 * DELETE слева → спейсер справа (чтобы правое окно "замирало" на месте удаления).
 * INSERT справа → спейсер слева (чтобы левое окно "замирало" на месте вставки).
 */
function insertDiffSpacers() {
  const pageCount = Math.max(state.pageCountA, state.pageCountB);

  for (let pageNum = 1; pageNum <= pageCount; pageNum++) {
    const entryA = state.renderedPagesA.get(pageNum);
    const entryB = state.renderedPagesB.get(pageNum);
    if (!entryA || !entryB) continue;

    const diffLayerA = entryA.pageWrap.querySelector(".diff-layer");
    const diffLayerB = entryB.pageWrap.querySelector(".diff-layer");
    if (!diffLayerA || !diffLayerB) continue;

    // Удаляем старые спейсеры (для возможности повторного вызова)
    diffLayerA.querySelectorAll(".diff-spacer").forEach((el) => el.remove());
    diffLayerB.querySelectorAll(".diff-spacer").forEach((el) => el.remove());

    // DELETE слева → спейсер справа
    insertSpacersForOps(diffLayerA, diffLayerB, "delete");
    // INSERT справа → спейсер слева
    insertSpacersForOps(diffLayerB, diffLayerA, "insert");
  }
}

/**
 * Находит serie слов с заданным классом операции в sourceLayer и вставляет
 * соответствующий спейсер в targetLayer на тех же вертикальных позициях.
 *
 * @param {HTMLElement} sourceLayer - diff-слой исходного окна (ищем слова операции)
 * @param {HTMLElement} targetLayer - diff-слой противоположного окна (куда вставляем спейсер)
 * @param {string} opClass - "delete" или "insert"
 */
function insertSpacersForOps(sourceLayer, targetLayer, opClass) {
  const words = Array.from(sourceLayer.querySelectorAll(`.diff-word.${opClass}`));
  if (words.length === 0) return;

  // Группируем соседние слова в серии (runs) по вертикальной близости
  const runs = [];
  let currentRun = [words[0]];

  for (let i = 1; i < words.length; i++) {
    const prev = currentRun[currentRun.length - 1];
    const curr = words[i];
    const prevBottom = parseFloat(prev.style.top) + parseFloat(prev.style.height);
    const currTop = parseFloat(curr.style.top);
    // Если следующее слово идет сразу после предыдущего (зазор < 5 px) — одна серия
    if (currTop - prevBottom < 5) {
      currentRun.push(curr);
    } else {
      runs.push(currentRun);
      currentRun = [curr];
    }
  }
  runs.push(currentRun);

  // Вставляем спейсер для каждой серии
  for (const run of runs) {
    insertSpacerForRun(targetLayer, run);
  }
}

/**
 * Вставляет один div.diff-spacer в targetLayer, охватывающий вертикальный
 * диапазон заданной серии слов.
 *
 * @param {HTMLElement} targetLayer - diff-слой противоположного окна
 * @param {Array<HTMLElement>} run - серия слов одной операции
 */
function insertSpacerForRun(targetLayer, run) {
  if (run.length === 0) return;

  const first = run[0];
  const last = run[run.length - 1];
  const top = parseFloat(first.style.top);
  const bottom = parseFloat(last.style.top) + parseFloat(last.style.height);
  const height = bottom - top;

  const spacer = document.createElement("div");
  spacer.className = "diff-spacer";
  spacer.style.position = "absolute";
  spacer.style.left = "0";
  spacer.style.top = `${Math.round(top)}px`;
  spacer.style.width = "100%";
  spacer.style.height = `${Math.round(height)}px`;
  spacer.style.pointerEvents = "none";
  spacer.style.overflow = "visible";

  targetLayer.appendChild(spacer);
}

// -------------------- Синхронный скроллинг (lock-step) --------------------

function syncScroll(sourcePanel, targetPanel, sourceKey) {
  if (state.isScrolling) return;
  state.isScrolling = true;

  try {
    const targetKey = sourceKey === "A" ? "B" : "A";
    const sourceContainer = document.getElementById(
      `canvasContainer${sourceKey}`
    );
    const targetContainer = document.getElementById(
      `canvasContainer${targetKey}`
    );

    const pageWraps = Array.from(
      sourceContainer.querySelectorAll(".page-wrap")
    );
    const panelRect = sourcePanel.getBoundingClientRect();
    const absoluteScrollTop = sourcePanel.scrollTop + panelRect.top;

    // Находим страницу, которая сейчас находится в верхней части области просмотра исходной панели.
    // Якорь — страница (блок EQUAL), а не процент от общей высоты прокрутки.
    let currentPage = null;
    for (const pw of pageWraps) {
      const pwTop = pw.offsetTop;
      const pwBottom = pwTop + pw.offsetHeight;
      if (pwTop <= absoluteScrollTop && pwBottom > absoluteScrollTop) {
        currentPage = pw;
        break;
      }
    }

    if (!currentPage) return;

    const pageNum = currentPage.dataset.pageNum;
    const relativeScroll = absoluteScrollTop - currentPage.offsetTop;

    // Находим соответствующую страницу в целевой панели и прокручиваем её
    // к тому же относительному положению внутри страницы.
    const targetPage = targetContainer.querySelector(
      `.page-wrap[data-page-num="${pageNum}"]`
    );
    if (!targetPage) return;

    const targetPanelRect = targetPanel.getBoundingClientRect();
    targetPanel.scrollTop =
      targetPage.offsetTop - targetPanelRect.top + relativeScroll;
  } finally {
    state.isScrolling = false;
  }
}

function scrollToPage(panelKey, pageNum) {
  const renderedMap = panelKey === "A" ? state.renderedPagesA : state.renderedPagesB;
  const entry = renderedMap.get(pageNum);
  if (!entry) return;
  const panel = document.getElementById(`panel${panelKey}`);
  const pageTop = entry.pageWrap.offsetTop;
  const panelTop = panel.offsetTop || 0;
  panel.scrollTop = pageTop - panelTop - 40; // небольшой отступ сверху
}

// -------------------- ИИ-анализ (стриминг, SSE) --------------------

async function runAiAnalysis() {
  const systemPrompt = document.getElementById("aiSystemPrompt").value ||
    "Проанализируй изменения между двумя версиями PDF-документа. Опиши, что было удалено, что добавлено и какие значения это имеет для смысла документа. Пиши по-русски, кратко и по существу.";
  const aiOutput = document.getElementById("aiOutput");
  const aiError = document.getElementById("aiError");
  const btn = document.getElementById("btnAiAnalyze");

  aiOutput.textContent = "";
  aiError.classList.add("ui-hidden");
  btn.disabled = true;

  try {
    const response = await fetch(`${API_BASE}/api/v1/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `prompt=${encodeURIComponent(systemPrompt)}`,
    });

    if (!response.ok) {
      throw new Error(`Ошибка ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Разбираем SSE-сообщения (data: ...\n\n)
      let newlineIdx;
      while ((newlineIdx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 2);
        const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
        if (dataLine) {
          try {
            const chunk = JSON.parse(dataLine.slice(6));
            appendAiChunk(chunk);
          } catch (_) {
            // не JSON — выводим как есть
            appendAiChunk(dataLine.slice(6));
          }
        }
      }
    }
  } catch (err) {
    console.error(err);
    aiError.textContent = "Ошибка ИИ-анализа: " + err.message;
    aiError.classList.remove("ui-hidden");
  } finally {
    btn.disabled = false;
  }
}

function appendAiChunk(text) {
  const aiOutput = document.getElementById("aiOutput");
  const span = document.createElement("span");
  span.className = "ai-chunk";
  span.textContent = text;
  aiOutput.appendChild(span);
  aiOutput.scrollTop = aiOutput.scrollHeight;
}

// -------------------- ИИ-отчет по странице --------------------

async function generateAiPageReport() {
  const aiOutput = document.getElementById("aiOutput");
  const aiError = document.getElementById("aiError");
  const btn = document.getElementById("btnAiPageReport");
  const systemPrompt = document.getElementById("aiSystemPrompt").value ||
    "Проанализируй изображение страницы PDF с учетом визуального контекста: таблиц, сдвигов верстки, логотипов и шрифтов. Опиши, что изменилось на этой странице между версиями документа. Пиши по-русски.";

  aiOutput.textContent = "";
  aiError.classList.add("ui-hidden");
  btn.disabled = true;

  try {
    // Берем снимок текущей видимой страницы из левого окна (оригинал).
    const pageNum = state.activePageA || 1;
    const entry = state.renderedPagesA.get(pageNum);
    if (!entry) throw new Error("Страница не отрендерена");

    const imageDataUrl = entry.canvas.toDataURL("image/png");
    const base64 = imageDataUrl.split(",")[1];

    const formData = new FormData();
    // Отправляем как файл (бэкенд принимает UploadFile + system_prompt)
    const blob = await (await fetch(imageDataUrl)).blob();
    formData.append("image", blob, `page-${pageNum}.png`);
    formData.append("system_prompt", systemPrompt);

    const response = await fetch(`${API_BASE}/api/v1/ai-report-page`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Ошибка ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIdx;
      while ((newlineIdx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 2);
        const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
        if (dataLine) {
          try {
            const chunk = JSON.parse(dataLine.slice(6));
            appendAiChunk(chunk);
          } catch (_) {
            appendAiChunk(dataLine.slice(6));
          }
        }
      }
    }
  } catch (err) {
    console.error(err);
    aiError.textContent = "Ошибка отчета по странице: " + err.message;
    aiError.classList.remove("ui-hidden");
  } finally {
    btn.disabled = false;
  }
}

// -------------------- Боковая панель ИИ (сворачивание) --------------------

function toggleAiPanel() {
  const content = document.getElementById("aiPanelContent");
  const toggle = document.getElementById("aiPanelToggle");
  const hidden = content.classList.toggle("ui-hidden");
  toggle.textContent = hidden ? "▼" : "▲";
}

// Отслеживаем активную страницу (для отчета по странице)
document.getElementById("panelA").addEventListener("scroll", () => {
  state.activePageA = nearestVisiblePage("A");
});
document.getElementById("panelB").addEventListener("scroll", () => {
  state.activePageB = nearestVisiblePage("B");
});

function nearestVisiblePage(panelKey) {
  const renderedMap = panelKey === "A" ? state.renderedPagesA : state.renderedPagesB;
  const panel = document.getElementById(`panel${panelKey}`);
  const scrollTop = panel.scrollTop;
  const clientHeight = panel.clientHeight;
  let nearest = 1;
  let nearestDist = Infinity;
  for (const [pageNum, entry] of renderedMap.entries()) {
    const top = entry.pageWrap.offsetTop;
    const bottom = top + entry.pageWrap.offsetHeight;
    const center = (top + bottom) / 2;
    const viewCenter = scrollTop + clientHeight / 2;
    const dist = Math.abs(center - viewCenter);
    if (dist < nearestDist) {
      nearestDist = dist;
      nearest = pageNum;
    }
  }
  return nearest;
}
