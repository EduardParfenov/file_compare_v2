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

function initApp() {
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
    btnCompare.disabled = true;
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
    btnCompare.disabled = !(fileA.files.length && fileB.files.length);
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
 * Вычислить символ-смещения каждого слова в тексте страницы,
 * чтобы сопоставить слова с координатами и операциями diff.
 */
function computeWordOffsets(pageText, words) {
  let offset = 0;
  for (const w of words) {
    const idx = pageText.indexOf(w.word, offset);
    if (idx === -1) {
      // слово не найдено — aproximативное смещение
      w.start = offset;
      w.end = offset + w.word.length;
      offset = w.end;
    } else {
      w.start = idx;
      w.end = idx + w.word.length;
      offset = w.end;
    }
  }
}

/**
 * Сопоставить каждое слово с операцией diff (EQUAL/DELETE/INSERT),
 * пройдя по блокам diff в порядке следования.
 */
function mapWordsToOps(words, blocks) {
  let blockIdx = 0;
  let blockPos = 0; // позиция внутри текущего блока (в символах)
  for (const w of words) {
    const wordLen = w.word.length;
    let wordOp = "EQUAL";
    let consumed = 0;

    while (consumed < wordLen && blockIdx < blocks.length) {
      const block = blocks[blockIdx];
      const blockText = block.text;
      const remainingInBlock = blockText.length - blockPos;
      const need = wordLen - consumed;
      const take = Math.min(remainingInBlock, need);

      // Операция блока применяется к символам слова в этом диапазоне.
      // Для слова берем операцию первого покрывающего его блока (приоритет DELETE/INSERT над EQUAL).
      if (block.op !== "EQUAL") {
        wordOp = block.op;
      }

      blockPos += take;
      consumed += take;

      if (blockPos >= blockText.length) {
        blockIdx++;
        blockPos = 0;
      }
    }
    w.op = wordOp;
  }
}

/**
 * Построить HTML-размещение слов на diff-слое для одной страницы одной панели.
 */
function buildDiffWordsHtml(pageNum, panelKey) {
  const coords = panelKey === "A" ? state.coordsLeft : state.coordsRight;
  const blocks = panelKey === "A"
    ? state.diffResult.left_panel.blocks
    : state.diffResult.right_panel.blocks;

  const pageInfo = coords.pages.find((p) => p.page_number === pageNum);
  if (!pageInfo) return "";

  const pageText = pageInfo.text;
  const words = pageInfo.words.slice(); // копия, чтобы не мутировать исходное
  computeWordOffsets(pageText, words);
  mapWordsToOps(words, blocks);

  const vp = state.renderedPagesA.get(pageNum) ||
             state.renderedPagesB.get(pageNum);
  if (!vp) return "";

  const scaleX = vp.viewport.width / 1; // scale=1 => 1:1 пойнт→пиксель
  const scaleY = vp.viewport.height / 1;

  let html = "";
  for (const w of words) {
    const cls = `diff-word ${w.op === "DELETE" ? "delete" : w.op === "INSERT" ? "insert" : "equal"}`;
    const left = Math.round(w.x0 * scaleX);
    const top = Math.round(w.y0 * scaleY);
    const width = Math.round((w.x1 - w.x0) * scaleX);
    const height = Math.round((w.y1 - w.y0) * scaleY);
    const escaped = escapeHtml(w.word);
    html += `<span class="${cls}" style="left:${left}px;top:${top}px;width:${width}px;height:${height}px" title="${escapeHtml(w.op)}">${escaped}</span>`;
  }
  return html;
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

  // Проходим по всем page-wrap и наполняем их diff-слои
  container.querySelectorAll(".page-wrap").forEach((pageWrap) => {
    const pageNum = parseInt(pageWrap.dataset.pageNum, 10);
    const diffLayer = pageWrap.querySelector(".diff-layer");
    diffLayer.innerHTML = buildDiffWordsHtml(pageNum, panelKey);
  });
}

// -------------------- Синхронный скроллинг (lock-step) --------------------

function syncScroll(sourcePanel, targetPanel, sourceKey) {
  if (state.isScrolling) return;
  state.isScrolling = true;

  try {
    const sourceMax = sourcePanel.scrollHeight - sourcePanel.clientHeight;
    const targetMax = targetPanel.scrollHeight - targetPanel.clientHeight;
    if (sourceMax <= 0 || targetMax <= 0) return;

    const ratio = sourcePanel.scrollTop / sourceMax;
    const targetTop = ratio * targetMax;

    targetPanel.scrollTop = targetTop;
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

initApp();
