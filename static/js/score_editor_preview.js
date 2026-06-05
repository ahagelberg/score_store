(function () {
  "use strict";

  const PREVIEW_FIRST_PAGE_NUM = 1;
  const PREVIEW_MIN_MOUNT_WIDTH_PX = 1;
  const PREVIEW_MAX_OUTPUT_SCALE = 2;
  const PREVIEW_LOADING_LABEL = "Loading…";
  const PREVIEW_ERROR_LABEL = "Preview unavailable";
  const PREVIEW_FLOAT_ID = "score-editor-preview-float";

  let pdfWorkerReady = false;
  let pdfWorkerUrl = "";
  const pdfDocCache = new Map();
  const resizeObservers = new WeakMap();
  let renderGeneration = 0;
  let activeItem = null;
  let floatPanel = null;

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

  async function loadPdfDocument(url) {
    const cached = pdfDocCache.get(url);
    if (cached) return cached;
    const lib = ensurePdfWorker();
    if (!lib) throw new Error("PDF.js unavailable");
    const pdf = await lib.getDocument({ url, withCredentials: true }).promise;
    pdfDocCache.set(url, pdf);
    return pdf;
  }

  function previewUrl(item) {
    return item?.dataset?.previewPdfUrl || "";
  }

  function floatMount() {
    return floatPanel?.querySelector(".score-editor-preview-mount") || null;
  }

  function ensureFloatPanel() {
    if (floatPanel) return floatPanel;
    floatPanel = document.createElement("aside");
    floatPanel.id = PREVIEW_FLOAT_ID;
    floatPanel.className = "score-editor-preview-float hidden";
    floatPanel.setAttribute("aria-hidden", "true");
    const mount = document.createElement("div");
    mount.className = "score-editor-preview-mount";
    floatPanel.appendChild(mount);
    document.body.appendChild(floatPanel);
    return floatPanel;
  }

  function clearResizeObserver(mount) {
    const observer = resizeObservers.get(mount);
    if (!observer) return;
    observer.disconnect();
    resizeObservers.delete(mount);
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
    } catch {
      if (mount.dataset.renderGen !== String(generation)) return;
      mount.replaceChildren();
      const err = document.createElement("p");
      err.className = "score-editor-preview-loading score-editor-preview-error";
      err.textContent = PREVIEW_ERROR_LABEL;
      mount.appendChild(err);
    }
  }

  function bindResize(mount, generation) {
    clearResizeObserver(mount);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (mount.dataset.renderGen !== String(generation)) return;
      renderFirstPage(mount, generation);
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
    if (!floatPanel) return;
    floatPanel.classList.add("hidden");
    floatPanel.setAttribute("aria-hidden", "true");
    activeItem = null;
  }

  function sync(item) {
    const url = previewUrl(item);
    if (!url) {
      if (activeItem === item) hideFloatPanel();
      return;
    }
    activeItem = item;
    const panel = ensureFloatPanel();
    const mount = floatMount();
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    mount.dataset.pdfUrl = url;
    renderGeneration += 1;
    const generation = renderGeneration;
    bindResize(mount, generation);
    renderFirstPage(mount, generation);
  }

  function clear(item) {
    if (activeItem !== item) return;
    hideFloatPanel();
  }

  window.ScoreEditorPreview = { sync, clear };
})();
