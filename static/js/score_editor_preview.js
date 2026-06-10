(function () {
  "use strict";

  const PREVIEW_FIRST_PAGE_NUM = 1;
  const PREVIEW_MIN_MOUNT_WIDTH_PX = 1;
  const PREVIEW_MAX_OUTPUT_SCALE = 2;
  const PREVIEW_LOADING_LABEL = "Loading…";
  const PREVIEW_ERROR_LABEL = "Preview unavailable";
  const PREVIEW_DEFAULT_TITLE = "New score";
  const PREVIEW_FLOAT_ID = "score-editor-preview-float";
  const PREVIEW_LABEL_FIELD_SELECTOR = '[data-field="title"], [data-field="composer"], [data-field="year"]';
  const PREVIEW_BASE_WIDTH_PX = 280;
  const PREVIEW_WIDTH_SCALE = 2;
  const PREVIEW_PREFERRED_WIDTH_PX = PREVIEW_BASE_WIDTH_PX * PREVIEW_WIDTH_SCALE;
  const PREVIEW_MIN_WIDTH_PX = 200;
  const PREVIEW_GAP_PX = 8;
  const PREVIEW_VIEWPORT_MARGIN_PX = 8;
  const PREVIEW_TAIL_SIZE_PX = 10;
  const PREVIEW_MAX_HEIGHT_VH_RATIO = 0.85;
  const PREVIEW_TAIL_MIN_PX = 16;
  const PREVIEW_TAIL_MAX_INSET_PX = 24;

  let pdfWorkerReady = false;
  let pdfWorkerUrl = "";
  const pdfDocCache = new Map();
  const resizeObservers = new WeakMap();
  let renderGeneration = 0;
  let activeItem = null;
  let floatPanel = null;
  let positionListenersBound = false;
  let editorResizeObserver = null;
  let repositionFrame = 0;
  let appliedPreviewWidthPx = 0;
  let previewLabelInputsItem = null;
  let activeItemObserver = null;

  function pdfLib() {
    return window.pdfjsLib || null;
  }

  function workerUrl() {
    if (pdfWorkerUrl) return pdfWorkerUrl;
    pdfWorkerUrl = document.getElementById("score-viewer-overlay")?.dataset.pdfWorker || "";
    return pdfWorkerUrl;
  }

  function ensurePdfWorker() {
    const lib = pdfLib();
    if (!lib || pdfWorkerReady) return lib;
    const src = workerUrl();
    if (!src) return null;
    lib.GlobalWorkerOptions.workerSrc = src;
    pdfWorkerReady = true;
    return lib;
  }

  function outputScale() {
    return Math.min(window.devicePixelRatio || 1, PREVIEW_MAX_OUTPUT_SCALE);
  }

  function scopedFileUrl(url) {
    return window.Csrf?.appendScopeParams?.(url) ?? url;
  }

  async function loadPdfDocument(url) {
    const scoped = scopedFileUrl(url);
    const cached = pdfDocCache.get(scoped);
    if (cached) return cached;
    const lib = ensurePdfWorker();
    if (!lib) throw new Error("PDF.js unavailable");
    const pdf = await lib.getDocument({ url: scoped, withCredentials: true }).promise;
    pdfDocCache.set(scoped, pdf);
    return pdf;
  }

  function previewUrl(item) {
    return item?.dataset?.previewPdfUrl || "";
  }

  function previewEligible(item) {
    if (!item?.isConnected) return false;
    if (!item.classList.contains("score-accordion-expanded")) return false;
    if (item.classList.contains("filter-hidden")) return false;
    const editor = editorElement(item);
    if (!editor || editor.classList.contains("hidden")) return false;
    return !!previewUrl(item);
  }

  function editorElement(item) {
    return item?.querySelector("[data-score-editor]") || null;
  }

  function floatMount() {
    return floatPanel?.querySelector(".score-editor-preview-mount") || null;
  }

  function previewSubtitleLine(composer, year) {
    if (composer && year) return `${composer} (${year})`;
    if (composer) return composer;
    if (year) return `(${year})`;
    return "";
  }

  function previewLabelForItem(item) {
    const title = item.querySelector('[data-field="title"]')?.value?.trim()
      || item.querySelector(".score-summary-title")?.textContent?.trim()
      || PREVIEW_DEFAULT_TITLE;
    const composer = item.querySelector('[data-field="composer"]')?.value?.trim() || "";
    const year = item.querySelector('[data-field="year"]')?.value?.trim() || "";
    const subtitle = previewSubtitleLine(composer, year)
      || item.querySelector(".score-summary-composer")?.textContent?.trim()
      || "";
    return { title, subtitle };
  }

  function updatePreviewLabel(item) {
    if (!floatPanel || !item) return;
    const { title, subtitle } = previewLabelForItem(item);
    const titleEl = floatPanel.querySelector(".score-editor-preview-title");
    const subtitleEl = floatPanel.querySelector(".score-editor-preview-composer");
    if (titleEl) titleEl.textContent = title;
    if (subtitleEl) {
      subtitleEl.textContent = subtitle;
      subtitleEl.classList.toggle("hidden", !subtitle);
    }
    const scoreId = item.dataset.scoreId || "";
    if (scoreId) floatPanel.dataset.scoreId = scoreId;
    else delete floatPanel.dataset.scoreId;
  }

  function onPreviewLabelInput() {
    if (!activeItem) return;
    updatePreviewLabel(activeItem);
  }

  function clearPreviewLabelInputs() {
    if (!previewLabelInputsItem) return;
    previewLabelInputsItem.querySelectorAll(PREVIEW_LABEL_FIELD_SELECTOR).forEach((el) => {
      el.removeEventListener("input", onPreviewLabelInput);
    });
    previewLabelInputsItem = null;
  }

  function bindPreviewLabelInputs(item) {
    clearPreviewLabelInputs();
    previewLabelInputsItem = item;
    item.querySelectorAll(PREVIEW_LABEL_FIELD_SELECTOR).forEach((el) => {
      el.addEventListener("input", onPreviewLabelInput);
    });
  }

  function setPreviewActiveItem(item) {
    document.querySelectorAll(".score-accordion-preview-active").forEach((el) => {
      el.classList.remove("score-accordion-preview-active");
    });
    if (item) item.classList.add("score-accordion-preview-active");
  }

  function ensureFloatPanel() {
    if (floatPanel) return floatPanel;
    floatPanel = document.createElement("aside");
    floatPanel.id = PREVIEW_FLOAT_ID;
    floatPanel.className = "score-editor-preview-float hidden";
    floatPanel.setAttribute("aria-hidden", "true");
    const bubble = document.createElement("div");
    bubble.className = "score-editor-preview-bubble";
    const header = document.createElement("div");
    header.className = "score-editor-preview-header";
    const titleEl = document.createElement("span");
    titleEl.className = "score-editor-preview-title";
    const subtitleEl = document.createElement("span");
    subtitleEl.className = "score-editor-preview-composer hidden";
    header.appendChild(titleEl);
    header.appendChild(subtitleEl);
    const mount = document.createElement("div");
    mount.className = "score-editor-preview-mount";
    bubble.appendChild(header);
    bubble.appendChild(mount);
    floatPanel.appendChild(bubble);
    document.body.appendChild(floatPanel);
    return floatPanel;
  }

  function clearResizeObserver(mount) {
    const observer = resizeObservers.get(mount);
    if (!observer) return;
    observer.disconnect();
    resizeObservers.delete(mount);
  }

  function clearEditorResizeObserver() {
    if (!editorResizeObserver) return;
    editorResizeObserver.disconnect();
    editorResizeObserver = null;
  }

  function clearActiveItemObserver() {
    if (!activeItemObserver) return;
    activeItemObserver.disconnect();
    activeItemObserver = null;
  }

  function bindActiveItemObserver(item) {
    clearActiveItemObserver();
    if (!item || typeof MutationObserver === "undefined") return;
    activeItemObserver = new MutationObserver(() => reconcile());
    activeItemObserver.observe(item, { attributes: true, attributeFilter: ["class"] });
    const editor = editorElement(item);
    if (editor) {
      activeItemObserver.observe(editor, { attributes: true, attributeFilter: ["class"] });
    }
  }

  function scheduleReposition() {
    if (!activeItem) return;
    if (repositionFrame) return;
    repositionFrame = requestAnimationFrame(() => {
      repositionFrame = 0;
      reconcile();
    });
  }

  function bindPositionListeners() {
    if (positionListenersBound) return;
    positionListenersBound = true;
    window.addEventListener("resize", scheduleReposition);
    document.addEventListener("scroll", scheduleReposition, true);
  }

  function bindEditorResizeObserver(item) {
    clearEditorResizeObserver();
    const editor = editorElement(item);
    if (!editor || typeof ResizeObserver === "undefined") return;
    editorResizeObserver = new ResizeObserver(scheduleReposition);
    editorResizeObserver.observe(editor);
  }

  function preferredPreviewWidthPx() {
    const value = getComputedStyle(document.documentElement).getPropertyValue("--score-editor-preview-width");
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : PREVIEW_PREFERRED_WIDTH_PX;
  }

  function previewWidthForEditor(editorRect, viewportWidth) {
    const spaceRight = viewportWidth - PREVIEW_VIEWPORT_MARGIN_PX - editorRect.right - PREVIEW_GAP_PX;
    return Math.max(PREVIEW_MIN_WIDTH_PX, Math.min(preferredPreviewWidthPx(), spaceRight));
  }

  function applyPreviewWidth(panel, widthPx) {
    if (appliedPreviewWidthPx === widthPx) return false;
    appliedPreviewWidthPx = widthPx;
    panel.style.width = `${widthPx}px`;
    return true;
  }

  function positionPanel(item) {
    if (!previewEligible(item)) {
      hideFloatPanel();
      return;
    }
    const panel = floatPanel;
    const editor = editorElement(item);
    if (!panel || panel.classList.contains("hidden") || !editor) return;
    const editorRect = editor.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const maxHeight = Math.floor(viewportHeight * PREVIEW_MAX_HEIGHT_VH_RATIO);
    panel.style.setProperty("--score-editor-preview-max-height", `${maxHeight}px`);
    const widthChanged = applyPreviewWidth(panel, previewWidthForEditor(editorRect, viewportWidth));
    const panelWidth = panel.offsetWidth;
    let left = editorRect.right + PREVIEW_GAP_PX;
    let top = editorRect.top;
    if (left + panelWidth > viewportWidth - PREVIEW_VIEWPORT_MARGIN_PX) {
      left = viewportWidth - panelWidth - PREVIEW_VIEWPORT_MARGIN_PX;
    }
    if (left < PREVIEW_VIEWPORT_MARGIN_PX) left = PREVIEW_VIEWPORT_MARGIN_PX;
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    const panelHeight = panel.offsetHeight;
    if (top + panelHeight > viewportHeight - PREVIEW_VIEWPORT_MARGIN_PX) {
      top = Math.max(
        PREVIEW_VIEWPORT_MARGIN_PX,
        viewportHeight - panelHeight - PREVIEW_VIEWPORT_MARGIN_PX
      );
      panel.style.top = `${top}px`;
    }
    const editorMid = editorRect.top + editorRect.height / 2 - top;
    const tailTop = Math.max(
      PREVIEW_TAIL_MIN_PX,
      Math.min(editorMid - PREVIEW_TAIL_SIZE_PX, panelHeight - PREVIEW_TAIL_MAX_INSET_PX)
    );
    panel.style.setProperty("--score-editor-preview-tail-top", `${tailTop}px`);
    if (widthChanged) {
      const mount = floatMount();
      if (mount?.dataset.pdfUrl) {
        renderGeneration += 1;
        renderFirstPage(mount, renderGeneration);
      }
    }
  }

  async function renderFirstPage(mount, generation) {
    const pdfUrl = mount.dataset.pdfUrl;
    if (!pdfUrl) return;
    mount.dataset.renderGen = String(generation);
    mount.replaceChildren();
    const loading = document.createElement("p");
    loading.className = "score-editor-preview-loading";
    loading.textContent = PREVIEW_LOADING_LABEL;
    mount.appendChild(loading);
    scheduleReposition();
    try {
      const pdf = await loadPdfDocument(pdfUrl);
      if (mount.dataset.renderGen !== String(generation)) return;
      const page = await pdf.getPage(PREVIEW_FIRST_PAGE_NUM);
      if (mount.dataset.renderGen !== String(generation)) return;
      const width = Math.max(mount.clientWidth, PREVIEW_MIN_MOUNT_WIDTH_PX);
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: width / base.width });
      const canvas = document.createElement("canvas");
      canvas.className = "score-editor-preview-canvas";
      const ctx = canvas.getContext("2d");
      const scale = outputScale();
      canvas.width = Math.floor(viewport.width * scale);
      canvas.height = Math.floor(viewport.height * scale);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      await page.render({ canvasContext: ctx, viewport }).promise;
      if (mount.dataset.renderGen !== String(generation)) return;
      mount.replaceChildren(canvas);
      scheduleReposition();
    } catch {
      if (mount.dataset.renderGen !== String(generation)) return;
      mount.replaceChildren();
      const err = document.createElement("p");
      err.className = "score-editor-preview-loading score-editor-preview-error";
      err.textContent = PREVIEW_ERROR_LABEL;
      mount.appendChild(err);
      scheduleReposition();
    }
  }

  function bindResize(mount, generation) {
    clearResizeObserver(mount);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (mount.dataset.renderGen !== String(generation)) return;
      renderFirstPage(mount, generation);
      scheduleReposition();
    });
    observer.observe(mount);
    resizeObservers.set(mount, observer);
  }

  function hideFloatPanel() {
    const mount = floatMount();
    if (mount) {
      renderGeneration += 1;
      mount.dataset.renderGen = String(renderGeneration);
      clearResizeObserver(mount);
      mount.replaceChildren();
      delete mount.dataset.pdfUrl;
    }
    clearEditorResizeObserver();
    clearActiveItemObserver();
    clearPreviewLabelInputs();
    setPreviewActiveItem(null);
    appliedPreviewWidthPx = 0;
    if (!floatPanel) return;
    floatPanel.classList.add("hidden");
    floatPanel.setAttribute("aria-hidden", "true");
    delete floatPanel.dataset.scoreId;
    activeItem = null;
  }

  function attachPreview(item) {
    const url = previewUrl(item);
    if (!url) {
      hideFloatPanel();
      return;
    }
    activeItem = item;
    bindPositionListeners();
    bindEditorResizeObserver(item);
    bindPreviewLabelInputs(item);
    bindActiveItemObserver(item);
    setPreviewActiveItem(item);
    const panel = ensureFloatPanel();
    const mount = floatMount();
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    updatePreviewLabel(item);
    mount.dataset.pdfUrl = url;
    renderGeneration += 1;
    const generation = renderGeneration;
    bindResize(mount, generation);
    positionPanel(item);
    renderFirstPage(mount, generation);
  }

  function reconcile(item) {
    if (item !== undefined) {
      if (previewEligible(item)) {
        attachPreview(item);
        return;
      }
      if (activeItem === item || !activeItem || !previewEligible(activeItem)) {
        hideFloatPanel();
      }
      return;
    }
    if (activeItem && previewEligible(activeItem)) {
      updatePreviewLabel(activeItem);
      positionPanel(activeItem);
      return;
    }
    hideFloatPanel();
  }

  window.ScoreEditorPreview = { reconcile };
})();
