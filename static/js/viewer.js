(function () {
  "use strict";

  const SWIPE_THRESHOLD_PX = 50;
  const SWIPE_HORIZONTAL_DOMINANCE = 1.5;
  const PDF_MIN_CONTAINER_WIDTH_PX = 1;
  const PDF_MAX_OUTPUT_SCALE = 2;
  const PDF_PAGE_LOADING_LABEL = "Loading…";
  const PDF_PAGE_SLOT_MIN_HEIGHT_PX = 120;
  const PDF_RENDER_BUFFER_PAGES = 1;
  const PDF_SCROLL_MODE_VERTICAL = "vertical";
  const PDF_SCROLL_MODE_VERTICAL_PAGES = "vertical-pages";
  const PDF_SCROLL_MODE_HORIZONTAL = "horizontal";
  const PDF_SCROLL_MODE_STORAGE_KEY = "scorestore-pdf-scroll-mode";
  const PDF_CAROUSEL_SPACER_START_CLASS = "viewer-pdf-carousel-spacer-start";
  const PDF_CAROUSEL_SPACER_END_CLASS = "viewer-pdf-carousel-spacer-end";
  const PDF_SCROLL_MODES = [
    PDF_SCROLL_MODE_VERTICAL,
    PDF_SCROLL_MODE_VERTICAL_PAGES,
    PDF_SCROLL_MODE_HORIZONTAL,
  ];
  const PDF_SCROLL_MODE_LABELS = {
    [PDF_SCROLL_MODE_VERTICAL]: "Continuous scroll",
    [PDF_SCROLL_MODE_VERTICAL_PAGES]: "Vertical pages",
    [PDF_SCROLL_MODE_HORIZONTAL]: "Horizontal pages",
  };
  const VIEWER_FILE_ICON_CLASS = "viewer-file-icon-svg";
  const VIEWER_FILE_ICONS = {
    pdf: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6"/><path d="M9 17h4"/></svg>`,
    youtube: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M10 9.5v5l5-2.5-5-2.5z"/></svg>`,
    audio: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
    video: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="6" width="14" height="12" rx="2"/><path d="M16 10l6-3v10l-6-3z"/></svg>`,
    image: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10.5" r="1.5"/><path d="M21 17l-5-5L5 19"/></svg>`,
    musescore: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
    file: `<svg class="${VIEWER_FILE_ICON_CLASS}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>`,
  };

  let overlay = null;
  let panel = null;
  let toolbar = null;
  let content = null;
  let titleEl = null;
  let navEl = null;
  let posEl = null;
  let prevBtn = null;
  let nextBtn = null;
  let downloadEl = null;
  let printBtn = null;
  let fullscreenBtn = null;
  let pdfPageNavEl = null;
  let pdfScrollModeBtn = null;
  let pdfWorkerUrl = "";
  let pdfWorkerReady = false;
  let pdfDocCache = new Map();
  let pdfScrollListeners = new WeakMap();
  let pdfRenderGeneration = 0;
  let pdfRelayoutScheduled = false;
  let context = { scoreIds: [], navQuery: {}, ctx: "" };

  function scoreViewPage() {
    return document.getElementById("score-view-page");
  }

  function isStandaloneViewPage() {
    return !!scoreViewPage();
  }

  function viewPageNavQuery() {
    const page = scoreViewPage();
    if (!page) return {};
    return parseJsonAttr(page, "viewNav", {});
  }

  function viewPageCtx() {
    const page = scoreViewPage();
    if (!page) return "";
    const fromData = page.dataset.ctx || "";
    if (fromData) return fromData;
    return new URLSearchParams(window.location.search).get("ctx") || "";
  }

  function ctxFromViewUrl(href) {
    if (!href) return "";
    try {
      return new URL(href, window.location.origin).searchParams.get("ctx") || "";
    } catch {
      return "";
    }
  }

  function updateViewPageUrl(scoreId) {
    const page = scoreViewPage();
    if (!page) return;
    const params = new URLSearchParams();
    Object.entries(context.navQuery).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    if (context.ctx) params.set("ctx", context.ctx);
    const qs = params.toString();
    const url = qs
      ? `/scores/${scoreId}/view?${qs}`
      : `/scores/${scoreId}/view`;
    window.history.replaceState(null, "", url);
    page.dataset.scoreId = scoreId;
  }

  function redirectLegacyViewScoreParam() {
    const params = new URLSearchParams(window.location.search);
    const viewScore = params.get("view_score");
    if (!viewScore || isStandaloneViewPage()) return false;
    params.delete("view_score");
    const qs = params.toString();
    const url = qs
      ? `/scores/${viewScore}/view?${qs}`
      : `/scores/${viewScore}/view`;
    window.location.replace(url);
    return true;
  }

  function workspaceFrom(el) {
    return el.closest(".library-workspace");
  }

  function parseJsonAttr(el, name, fallback) {
    if (!el) return fallback;
    try {
      return JSON.parse(el.dataset[name] || "");
    } catch {
      return fallback;
    }
  }

  function viewerQuery(scoreId) {
    const params = new URLSearchParams();
    Object.entries(context.navQuery).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    if (context.ctx) params.set("ctx", context.ctx);
    return `/scores/${scoreId}/viewer?${params.toString()}`;
  }

  async function mintViewerCtx(scoreId, scoreIds) {
    const res = await window.Csrf.fetch(`/scores/${scoreId}/viewer-ctx`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score_ids: scoreIds }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not open score");
    return data.ctx || "";
  }

  async function resolveViewerCtx(scoreId, scoreIds, explicitCtx) {
    if (context.ctx && context.scoreIds.includes(scoreId)) {
      return context.ctx;
    }
    if (scoreIds?.length) {
      return mintViewerCtx(scoreId, scoreIds);
    }
    if (explicitCtx) return explicitCtx;
    if (context.ctx) return context.ctx;
    return viewPageCtx();
  }

  function pdfLib() {
    return window.pdfjsLib || null;
  }

  function ensurePdfWorker() {
    const lib = pdfLib();
    if (!lib || pdfWorkerReady) return lib;
    lib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
    pdfWorkerReady = true;
    return lib;
  }

  function clearPdfCache() {
    pdfRenderGeneration += 1;
    pdfDocCache.forEach((pdf) => {
      pdf.destroy?.();
    });
    pdfDocCache.clear();
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

  function loadPdfScrollMode() {
    const mode = localStorage.getItem(PDF_SCROLL_MODE_STORAGE_KEY);
    return PDF_SCROLL_MODES.includes(mode) ? mode : PDF_SCROLL_MODE_VERTICAL;
  }

  function savePdfScrollMode(mode) {
    localStorage.setItem(PDF_SCROLL_MODE_STORAGE_KEY, mode);
  }

  function nextPdfScrollMode(mode) {
    const index = PDF_SCROLL_MODES.indexOf(mode);
    return PDF_SCROLL_MODES[(index + 1) % PDF_SCROLL_MODES.length];
  }

  function isFitScreenPdfScrollMode(mode) {
    return mode === PDF_SCROLL_MODE_HORIZONTAL || mode === PDF_SCROLL_MODE_VERTICAL_PAGES;
  }

  function togglePdfScrollMode() {
    const next = nextPdfScrollMode(loadPdfScrollMode());
    savePdfScrollMode(next);
    updatePdfScrollModeUi();
    rerenderVisiblePdfPane();
  }

  function updatePdfScrollModeUi() {
    if (!pdfScrollModeBtn) return;
    const current = loadPdfScrollMode();
    pdfScrollModeBtn.querySelector(".viewer-icon-pdf-scroll-vertical").classList.toggle("hidden", current !== PDF_SCROLL_MODE_VERTICAL);
    pdfScrollModeBtn.querySelector(".viewer-icon-pdf-scroll-vertical-pages").classList.toggle("hidden", current !== PDF_SCROLL_MODE_VERTICAL_PAGES);
    pdfScrollModeBtn.querySelector(".viewer-icon-pdf-scroll-horizontal").classList.toggle("hidden", current !== PDF_SCROLL_MODE_HORIZONTAL);
    const label = PDF_SCROLL_MODE_LABELS[current];
    pdfScrollModeBtn.setAttribute("aria-label", `Scroll mode: ${label}. Click to change.`);
    pdfScrollModeBtn.title = label;
  }

  function setPdfScrollModeBtnVisible(show) {
    pdfScrollModeBtn?.classList.toggle("hidden", !show);
  }

  function applyMountScrollMode(mount) {
    const mode = loadPdfScrollMode();
    mount.classList.add("viewer-pdf-scroll");
    mount.classList.toggle("viewer-pdf-scroll-vertical", mode === PDF_SCROLL_MODE_VERTICAL);
    mount.classList.toggle("viewer-pdf-scroll-vertical-pages", mode === PDF_SCROLL_MODE_VERTICAL_PAGES);
    mount.classList.toggle("viewer-pdf-scroll-horizontal", mode === PDF_SCROLL_MODE_HORIZONTAL);
    if (mode !== PDF_SCROLL_MODE_HORIZONTAL) {
      mount.querySelectorAll(".viewer-pdf-carousel-spacer").forEach((el) => el.remove());
    }
  }

  function mountFitKey(mount, mode) {
    const fit = mountFitSize(mount, mode);
    const heightKey = fit.height == null ? "a" : String(Math.round(fit.height));
    return `${Math.round(fit.width)}:${heightKey}:${mode}`;
  }

  function orderedPageNums(totalPages, focusPage) {
    const focus = Math.max(1, Math.min(totalPages, focusPage || 1));
    const lo = Math.max(1, focus - PDF_RENDER_BUFFER_PAGES);
    const hi = Math.min(totalPages, focus + PDF_RENDER_BUFFER_PAGES);
    const order = [];
    for (let pageNum = lo; pageNum <= hi; pageNum += 1) order.push(pageNum);
    for (let pageNum = 1; pageNum <= totalPages; pageNum += 1) {
      if (!order.includes(pageNum)) order.push(pageNum);
    }
    return order;
  }

  async function renderPdfPagesForMount(mount, pdf, slots, fit, mode, totalPages, pageOrder, generation) {
    for (const pageNum of pageOrder) {
      if (generation !== pdfRenderGeneration) return;
      const slot = slots[pageNum - 1];
      if (!slot) continue;
      slot.replaceChildren(createPageLoadingLabel());
      const { page, viewport } = await pageViewportForMode(pdf, pageNum, fit, mode);
      slot.dataset.minH = String(Math.round(viewport.height));
      await renderPdfPageToSlot(slot, page, viewport, pageNum, totalPages);
    }
  }

  function horizontalCarouselSpacer(mount, kind) {
    const selector = kind === "start"
      ? `.${PDF_CAROUSEL_SPACER_START_CLASS}`
      : `.${PDF_CAROUSEL_SPACER_END_CLASS}`;
    let spacer = mount.querySelector(selector);
    if (spacer) return spacer;
    spacer = document.createElement("div");
    spacer.className = `viewer-pdf-carousel-spacer ${kind === "start" ? PDF_CAROUSEL_SPACER_START_CLASS : PDF_CAROUSEL_SPACER_END_CLASS}`;
    spacer.setAttribute("aria-hidden", "true");
    if (kind === "start") mount.prepend(spacer);
    else mount.append(spacer);
    return spacer;
  }

  function setHorizontalCarouselSpacerWidth(spacer, widthPx) {
    const width = `${Math.round(widthPx)}px`;
    spacer.style.flex = `0 0 ${width}`;
    spacer.style.width = width;
  }

  function horizontalCarouselPageSlots(mount) {
    return mount.querySelectorAll(".viewer-pdf-page-slot");
  }

  function syncHorizontalCarousel(mount, pageNum, smooth) {
    if (!mount.classList.contains("viewer-pdf-scroll-horizontal")) return;
    const viewportW = mount.clientWidth;
    const slots = horizontalCarouselPageSlots(mount);
    const firstSlot = slots[0];
    const lastSlot = slots[slots.length - 1];
    const padStart = firstSlot ? Math.max(0, (viewportW - firstSlot.offsetWidth) / 2) : 0;
    const padEnd = lastSlot ? Math.max(0, (viewportW - lastSlot.offsetWidth) / 2) : 0;
    setHorizontalCarouselSpacerWidth(horizontalCarouselSpacer(mount, "start"), padStart);
    setHorizontalCarouselSpacerWidth(horizontalCarouselSpacer(mount, "end"), padEnd);
    const targetPage = pageNum || currentPdfPage(mount);
    const slot = mount.querySelector(`.viewer-pdf-page-slot[data-page-num="${targetPage}"]`);
    if (!slot) return;
    const slotCenter = slot.offsetLeft + slot.offsetWidth / 2;
    const maxScroll = Math.max(0, mount.scrollWidth - viewportW);
    const scrollLeft = Math.max(0, Math.min(slotCenter - viewportW / 2, maxScroll));
    if (smooth && mount.scrollTo) {
      mount.scrollTo({ left: scrollLeft, behavior: "smooth" });
      return;
    }
    mount.scrollLeft = scrollLeft;
  }

  function mountFitSize(mount, mode) {
    const frame = mount.closest(".viewer-pdf-frame");
    const width = Math.max(
      mount.clientWidth || frame?.clientWidth || content.clientWidth,
      PDF_MIN_CONTAINER_WIDTH_PX,
    );
    if (!isFitScreenPdfScrollMode(mode)) {
      return { width, height: null };
    }
    const height = Math.max(
      mount.clientHeight || frame?.clientHeight || content.clientHeight,
      PDF_MIN_CONTAINER_WIDTH_PX,
    );
    return { width, height };
  }

  function outputScale() {
    return Math.min(window.devicePixelRatio || 1, PDF_MAX_OUTPUT_SCALE);
  }

  async function pageViewportForMode(pdf, pageNum, fit, mode) {
    const page = await pdf.getPage(pageNum);
    const base = page.getViewport({ scale: 1 });
    let scale;
    if (mode === PDF_SCROLL_MODE_HORIZONTAL) {
      scale = fit.height / base.height;
    } else if (mode === PDF_SCROLL_MODE_VERTICAL_PAGES) {
      scale = Math.min(fit.width / base.width, fit.height / base.height);
    } else {
      scale = fit.width / base.width;
    }
    return { page, viewport: page.getViewport({ scale }) };
  }

  function createPageLoadingLabel() {
    const label = document.createElement("p");
    label.className = "viewer-pdf-page-loading";
    label.textContent = PDF_PAGE_LOADING_LABEL;
    return label;
  }

  function createPageSlot(pageNum, height) {
    const slot = document.createElement("div");
    slot.className = "viewer-pdf-page-slot";
    slot.dataset.pageNum = String(pageNum);
    slot.dataset.minH = String(Math.round(height));
    slot.appendChild(createPageLoadingLabel());
    return slot;
  }

  async function renderPdfPageToSlot(slot, page, viewport, pageNum, totalPages) {
    try {
      const canvas = document.createElement("canvas");
      canvas.className = "viewer-pdf-page";
      const ctx = canvas.getContext("2d");
      const scale = outputScale();
      canvas.width = Math.floor(viewport.width * scale);
      canvas.height = Math.floor(viewport.height * scale);
      canvas.style.width = `${Math.round(viewport.width)}px`;
      canvas.style.height = `${Math.round(viewport.height)}px`;
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      await page.render({ canvasContext: ctx, viewport }).promise;
      slot.replaceChildren(canvas);
      if (totalPages > 1) {
        const badge = document.createElement("span");
        badge.className = "viewer-pdf-page-num";
        badge.textContent = String(pageNum);
        slot.appendChild(badge);
      }
    } catch {
      slot.replaceChildren();
      const err = document.createElement("p");
      err.className = "viewer-pdf-page-loading viewer-pdf-error";
      err.textContent = "Could not render page";
      slot.appendChild(err);
    }
  }

  function currentPdfPage(mount) {
    const horizontal = mount.classList.contains("viewer-pdf-scroll-horizontal");
    const viewMid = horizontal
      ? mount.scrollLeft + mount.clientWidth / 2
      : mount.scrollTop + mount.clientHeight / 2;
    let current = 1;
    let closestDistance = Infinity;
    mount.querySelectorAll(".viewer-pdf-page-slot").forEach((slot) => {
      const start = horizontal ? slot.offsetLeft : slot.offsetTop;
      const size = horizontal ? slot.offsetWidth : slot.offsetHeight;
      const center = start + size / 2;
      const distance = Math.abs(viewMid - center);
      if (distance < closestDistance) {
        closestDistance = distance;
        current = Number(slot.dataset.pageNum) || current;
      }
    });
    return current;
  }

  function printablePaneTarget(pane) {
    if (!pane) return null;
    const media = pane.dataset.media;
    if (media === "pdf") {
      const url = pane.querySelector(".viewer-pdf-mount")?.dataset.pdfUrl;
      return url ? { url, media: "pdf" } : null;
    }
    if (media === "image") {
      const url = pane.querySelector("img")?.src;
      return url ? { url, media: "image" } : null;
    }
    return null;
  }

  function updatePrintButton(pane) {
    if (!printBtn) return;
    const printable = printablePaneTarget(pane);
    printBtn.classList.toggle("hidden", !printable);
  }

  function printVisiblePane() {
    const pane = content.querySelector(".viewer-pane:not(.hidden)");
    const printable = printablePaneTarget(pane);
    if (!printable) {
      showToast("Cannot print this file type", true);
      return;
    }
    window.ScorePrint?.printFile(printable.url, printable.media);
  }

  function updatePdfPageArrows(mount) {
    const frame = mount?.closest(".viewer-pdf-frame");
    if (!frame) return;
    const arrows = frame.querySelector(".viewer-pdf-page-arrows");
    if (!arrows) return;
    const horizontal = mount.classList.contains("viewer-pdf-scroll-horizontal");
    const verticalPages = mount.classList.contains("viewer-pdf-scroll-vertical-pages");
    const paged = horizontal || verticalPages;
    const total = Number(mount.dataset.pdfPageTotal) || 0;
    const show = paged && total > 1 && mount.dataset.rendered === "true";
    arrows.classList.toggle("hidden", !show);
    arrows.classList.toggle("viewer-pdf-page-arrows-horizontal", show && horizontal);
    arrows.classList.toggle("viewer-pdf-page-arrows-vertical", show && verticalPages);
    arrows.setAttribute("aria-hidden", show ? "false" : "true");
    if (!show) {
      arrows.classList.remove("viewer-pdf-page-arrows-horizontal", "viewer-pdf-page-arrows-vertical");
      return;
    }
    const current = currentPdfPage(mount);
    const atStart = current <= 1;
    const atEnd = current >= total;
    const prevArrow = arrows.querySelector(".viewer-pdf-page-arrow-prev");
    const nextArrow = arrows.querySelector(".viewer-pdf-page-arrow-next");
    const upArrow = arrows.querySelector(".viewer-pdf-page-arrow-up");
    const downArrow = arrows.querySelector(".viewer-pdf-page-arrow-down");
    prevArrow.classList.toggle("viewer-pdf-page-arrow-disabled", atStart);
    nextArrow.classList.toggle("viewer-pdf-page-arrow-disabled", atEnd);
    upArrow.classList.toggle("viewer-pdf-page-arrow-disabled", atStart);
    downArrow.classList.toggle("viewer-pdf-page-arrow-disabled", atEnd);
    prevArrow.disabled = atStart;
    nextArrow.disabled = atEnd;
    upArrow.disabled = atStart;
    downArrow.disabled = atEnd;
  }

  function updatePdfPageNav(current, total) {
    if (!pdfPageNavEl || total < 1) return;
    pdfPageNavEl.textContent = `${current} / ${total}`;
    pdfPageNavEl.classList.remove("hidden");
  }

  function hidePdfPageNav() {
    pdfPageNavEl?.classList.add("hidden");
  }

  function unbindPdfPageNav(mount) {
    const onScroll = pdfScrollListeners.get(mount);
    if (!onScroll) return;
    mount.removeEventListener("scroll", onScroll);
    pdfScrollListeners.delete(mount);
  }

  function bindPdfPageNav(mount, totalPages) {
    unbindPdfPageNav(mount);
    mount.dataset.pdfPageTotal = String(totalPages);
    updatePdfPageNav(1, totalPages);
    const onScroll = () => {
      updatePdfPageNav(currentPdfPage(mount), totalPages);
      updatePdfPageArrows(mount);
    };
    mount.addEventListener("scroll", onScroll, { passive: true });
    pdfScrollListeners.set(mount, onScroll);
    onScroll();
  }

  function syncPdfPageNavFromVisiblePane() {
    const pane = content.querySelector('.viewer-pane[data-media="pdf"]:not(.hidden)');
    if (!pane) {
      hidePdfPageNav();
      return;
    }
    const mount = pane.querySelector(".viewer-pdf-mount");
    if (!mount || mount.dataset.rendered !== "true") {
      hidePdfPageNav();
      return;
    }
    const total = Number(mount.dataset.pdfPageTotal) || 1;
    updatePdfPageNav(currentPdfPage(mount), total);
  }

  async function setupPdfMount(mount, pdf, options) {
    const opts = options || {};
    const mode = loadPdfScrollMode();
    applyMountScrollMode(mount);
    const fit = mountFitSize(mount, mode);
    const totalPages = pdf.numPages;
    const focusPage = opts.focusPage || 1;
    let slots;
    const existing = mount.querySelectorAll(".viewer-pdf-page-slot");
    if (opts.reuseSlots && existing.length === totalPages) {
      slots = Array.from(existing);
    } else {
      mount.replaceChildren();
      slots = [];
      for (let pageNum = 1; pageNum <= totalPages; pageNum += 1) {
        const slot = createPageSlot(pageNum, PDF_PAGE_SLOT_MIN_HEIGHT_PX);
        mount.appendChild(slot);
        slots.push(slot);
      }
      bindPdfPageNav(mount, totalPages);
    }
    setPdfScrollModeBtnVisible(true);
    updatePdfScrollModeUi();
    const generation = ++pdfRenderGeneration;
    const pageOrder = orderedPageNums(totalPages, focusPage);
    await renderPdfPagesForMount(mount, pdf, slots, fit, mode, totalPages, pageOrder, generation);
    if (generation !== pdfRenderGeneration) return;
    mount.dataset.rendered = "true";
    mount.dataset.fitKey = mountFitKey(mount, mode);
    if (mode === PDF_SCROLL_MODE_HORIZONTAL) {
      syncHorizontalCarousel(mount, focusPage, false);
    } else {
      scrollPdfToPage(mount, focusPage, false);
    }
    syncPdfPageNavFromVisiblePane();
    updatePdfPageArrows(mount);
  }

  async function renderPdfMount(mount) {
    const url = mount.dataset.pdfUrl;
    if (!url || mount.dataset.rendered === "true") return;
    const lib = ensurePdfWorker();
    if (!lib) {
      mount.textContent = "PDF viewer unavailable";
      return;
    }
    mount.classList.add("viewer-pdf-scroll");
    applyMountScrollMode(mount);
    setPdfScrollModeBtnVisible(true);
    updatePdfScrollModeUi();
    const loading = document.createElement("p");
    loading.className = "viewer-pdf-loading";
    loading.textContent = PDF_PAGE_LOADING_LABEL;
    mount.appendChild(loading);
    try {
      const pdf = await loadPdfDocument(url);
      await setupPdfMount(mount, pdf);
    } catch {
      mount.replaceChildren();
      const err = document.createElement("p");
      err.className = "viewer-pdf-error";
      err.textContent = "Could not load PDF";
      mount.appendChild(err);
      setPdfScrollModeBtnVisible(false);
    }
  }

  function scrollPdfToPage(mount, pageNum, smooth) {
    const slot = mount.querySelector(`.viewer-pdf-page-slot[data-page-num="${pageNum}"]`);
    if (!slot) return;
    if (mount.classList.contains("viewer-pdf-scroll-horizontal")) {
      syncHorizontalCarousel(mount, pageNum, smooth);
      return;
    }
    const top = slot.offsetTop;
    if (smooth && mount.scrollTo) {
      mount.scrollTo({ top, behavior: "smooth" });
      return;
    }
    mount.scrollTop = top;
  }

  function navigatePdfPage(mount, delta) {
    const total = Number(mount.dataset.pdfPageTotal) || 1;
    const current = currentPdfPage(mount);
    const target = Math.max(1, Math.min(total, current + delta));
    if (target === current) return;
    scrollPdfToPage(mount, target, true);
    updatePdfPageNav(target, total);
    updatePdfPageArrows(mount);
  }

  function resetPdfMount(mount) {
    pdfRenderGeneration += 1;
    unbindPdfPageNav(mount);
    delete mount.dataset.rendered;
    delete mount.dataset.pdfPageTotal;
    delete mount.dataset.fitKey;
    mount.classList.remove(
      "viewer-pdf-scroll",
      "viewer-pdf-scroll-vertical",
      "viewer-pdf-scroll-vertical-pages",
      "viewer-pdf-scroll-horizontal",
    );
    mount.replaceChildren();
    updatePdfPageArrows(mount);
  }

  function schedulePdfPaneRelayout() {
    if (pdfRelayoutScheduled) return;
    pdfRelayoutScheduled = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        pdfRelayoutScheduled = false;
        rerenderVisiblePdfPane();
      });
    });
  }

  async function rerenderVisiblePdfPane() {
    const pane = content.querySelector('.viewer-pane[data-media="pdf"]:not(.hidden)');
    if (!pane) return;
    const mount = pane.querySelector(".viewer-pdf-mount");
    if (!mount) return;
    const url = mount.dataset.pdfUrl;
    if (!url) return;
    const mode = loadPdfScrollMode();
    if (mount.dataset.rendered === "true") {
      const fitKey = mountFitKey(mount, mode);
      if (mount.dataset.fitKey === fitKey) return;
    }
    const currentPage = mount.dataset.rendered === "true" ? currentPdfPage(mount) : 1;
    setPdfScrollModeBtnVisible(true);
    updatePdfScrollModeUi();
    try {
      const pdf = await loadPdfDocument(url);
      const reuseSlots = mount.dataset.rendered === "true"
        && mount.querySelectorAll(".viewer-pdf-page-slot").length === pdf.numPages;
      await setupPdfMount(mount, pdf, { focusPage: currentPage, reuseSlots });
      if (mount.dataset.rendered !== "true") return;
      scrollPdfToPage(mount, currentPage);
      syncPdfPageNavFromVisiblePane();
      updatePdfPageArrows(mount);
    } catch {
      resetPdfMount(mount);
      const err = document.createElement("p");
      err.className = "viewer-pdf-error";
      err.textContent = "Could not load PDF";
      mount.appendChild(err);
      setPdfScrollModeBtnVisible(false);
    }
  }

  async function ensurePdfPaneRendered(pane) {
    const mount = pane.querySelector(".viewer-pdf-mount");
    if (!mount) return;
    await renderPdfMount(mount);
  }

  function showPane(fileId) {
    content.querySelectorAll("[data-pane]").forEach((pane) => {
      pane.classList.toggle("hidden", pane.dataset.pane !== fileId);
    });
    toolbar.querySelectorAll(".viewer-toolbar-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.fileId === fileId);
    });
    const pane = content.querySelector(`[data-pane="${fileId}"]`);
    updatePrintButton(pane);
    if (pane?.dataset.media === "pdf") {
      setPdfScrollModeBtnVisible(true);
      updatePdfScrollModeUi();
      ensurePdfPaneRendered(pane);
    } else {
      hidePdfPageNav();
      setPdfScrollModeBtnVisible(false);
    }
  }

  function paneHtml(file) {
    const media = file.media;
    if (media === "pdf") {
      return `<div class="viewer-pdf-frame">
        <div class="viewer-pdf-mount" data-pdf-url="${file.serve_url}"></div>
        <div class="viewer-pdf-page-arrows hidden" aria-hidden="true">
          <button type="button" class="viewer-pdf-page-arrow viewer-pdf-page-arrow-prev" aria-label="Previous page">
            <span class="viewer-pdf-page-arrow-symbol" aria-hidden="true">‹</span>
          </button>
          <button type="button" class="viewer-pdf-page-arrow viewer-pdf-page-arrow-next" aria-label="Next page">
            <span class="viewer-pdf-page-arrow-symbol" aria-hidden="true">›</span>
          </button>
          <button type="button" class="viewer-pdf-page-arrow viewer-pdf-page-arrow-up" aria-label="Previous page">
            <span class="viewer-pdf-page-arrow-symbol" aria-hidden="true">‹</span>
          </button>
          <button type="button" class="viewer-pdf-page-arrow viewer-pdf-page-arrow-down" aria-label="Next page">
            <span class="viewer-pdf-page-arrow-symbol" aria-hidden="true">‹</span>
          </button>
        </div>
      </div>`;
    }
    if (media === "image") {
      return `<img src="${file.serve_url}" alt="${file.display_name}">`;
    }
    if (media === "audio") {
      return `<div class="viewer-audio-bar"><audio controls src="${file.serve_url}"></audio></div>`;
    }
    if (media === "video") {
      return `<video controls src="${file.serve_url}"></video>`;
    }
    if (media === "youtube" && file.embed_url) {
      return `<iframe class="viewer-embed-frame" src="${file.embed_url}" allowfullscreen title="${file.display_name}"></iframe>`;
    }
    if (media === "musescore") {
      return `<div class="viewer-download-hint"><p>${file.display_name} — MuseScore file</p><a class="btn btn-primary" href="${file.serve_url}" download>Download</a></div>`;
    }
    if (file.serve_url) {
      return `<div class="viewer-download-hint"><a class="btn btn-primary" href="${file.serve_url}" download>Download ${file.display_name}</a></div>`;
    }
    return `<div class="viewer-download-hint"><p>${file.display_name}</p></div>`;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function viewerFileIcon(media) {
    return VIEWER_FILE_ICONS[media] || VIEWER_FILE_ICONS.file;
  }

  function renderToolbar(files, selectedFileId) {
    if (files.length <= 1) {
      toolbar.classList.add("hidden");
      toolbar.replaceChildren();
      return;
    }
    toolbar.classList.remove("hidden");
    toolbar.replaceChildren();
    files.forEach((file) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "viewer-toolbar-item";
      if (file.id === selectedFileId) btn.classList.add("active");
      btn.dataset.fileId = file.id;
      btn.dataset.media = file.media || "file";
      const label = file.type_label || file.display_name;
      btn.title = label;
      btn.innerHTML = `<span class="viewer-file-icon" aria-hidden="true">${viewerFileIcon(file.media)}</span><span class="viewer-file-label">${escapeHtml(file.display_name)}</span>`;
      btn.addEventListener("click", () => showPane(file.id));
      toolbar.appendChild(btn);
    });
  }

  function renderContent(files, selectedFileId) {
    hidePdfPageNav();
    setPdfScrollModeBtnVisible(false);
    content.replaceChildren();
    files.forEach((file) => {
      const pane = document.createElement("div");
      pane.className = "viewer-pane";
      pane.dataset.pane = file.id;
      pane.dataset.media = file.media || "";
      if (file.id !== selectedFileId) pane.classList.add("hidden");
      pane.innerHTML = paneHtml(file);
      content.appendChild(pane);
    });
    const selected = content.querySelector(`[data-pane="${selectedFileId}"]`);
    updatePrintButton(selected);
    if (selected?.dataset.media === "pdf") {
      setPdfScrollModeBtnVisible(true);
      updatePdfScrollModeUi();
      ensurePdfPaneRendered(selected);
    }
  }

  function renderNav(nav) {
    if (!nav.total || nav.total <= 1) {
      navEl.classList.add("hidden");
      return;
    }
    navEl.classList.remove("hidden");
    posEl.textContent = `${nav.index} / ${nav.total}`;
    prevBtn.disabled = !nav.prev_id;
    prevBtn.title = nav.prev_title || "";
    nextBtn.disabled = !nav.next_id;
    nextBtn.title = nav.next_title || "";
    prevBtn.classList.toggle("viewer-score-nav-btn-disabled", !nav.prev_id);
    nextBtn.classList.toggle("viewer-score-nav-btn-disabled", !nav.next_id);
    prevBtn.dataset.targetId = nav.prev_id || "";
    nextBtn.dataset.targetId = nav.next_id || "";
  }

  function scoreSubtitleLine(score) {
    if (score.subtitle) return score.subtitle;
    const composer = (score.composer || "").trim();
    const arranger = (score.arranger || "").trim();
    const year = (score.year || "").trim();
    const creditParts = [];
    if (composer) creditParts.push(composer);
    if (arranger) creditParts.push(`arr. ${arranger}`);
    const line = creditParts.join(" · ");
    if (year) return line ? `${line} (${year})` : `(${year})`;
    return line;
  }

  function renderTitle(score) {
    titleEl.textContent = score.title || "Score";
    const subtitleEl = document.getElementById("score-viewer-subtitle");
    if (!subtitleEl) return;
    const subtitle = scoreSubtitleLine(score);
    subtitleEl.textContent = subtitle;
    subtitleEl.classList.toggle("hidden", !subtitle);
  }

  function renderDownload(downloadUrl) {
    if (downloadUrl) {
      downloadEl.href = downloadUrl;
      downloadEl.classList.remove("hidden");
    } else {
      downloadEl.classList.add("hidden");
      downloadEl.removeAttribute("href");
    }
  }

  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  function updateFullscreenIcon() {
    if (!fullscreenBtn) return;
    const inFs = fullscreenElement() === panel;
    fullscreenBtn.querySelector(".viewer-icon-fullscreen-enter").classList.toggle("hidden", inFs);
    fullscreenBtn.querySelector(".viewer-icon-fullscreen-exit").classList.toggle("hidden", !inFs);
    fullscreenBtn.setAttribute("aria-label", inFs ? "Exit fullscreen" : "Enter fullscreen");
  }

  function exitFullscreenIfNeeded() {
    if (fullscreenElement() === panel && document.exitFullscreen) {
      document.exitFullscreen();
    }
  }

  async function open(scoreId, scoreIds, navQuery, explicitCtx) {
    try {
      const ctx = await resolveViewerCtx(scoreId, scoreIds, explicitCtx);
      context = { scoreIds: scoreIds || [], navQuery: navQuery || {}, ctx };
    } catch (err) {
      showToast(err.message || "Could not open score", true);
      return;
    }
    clearPdfCache();
    const res = await fetch(viewerQuery(scoreId));
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Could not open score", true);
      return;
    }
    context.scoreIds = data.score_ids || context.scoreIds;
    renderTitle(data.score);
    renderNav(data.nav);
    renderDownload(data.download_url);
    renderToolbar(data.files, data.selected_file_id);
    renderContent(data.files, data.selected_file_id);
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("score-viewer-open");
    if (isStandaloneViewPage()) updateViewPageUrl(scoreId);
  }

  function close() {
    exitFullscreenIfNeeded();
    hidePdfPageNav();
    setPdfScrollModeBtnVisible(false);
    const page = scoreViewPage();
    if (page?.dataset.backUrl) {
      window.location.href = page.dataset.backUrl;
      return;
    }
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("score-viewer-open");
    content.replaceChildren();
    toolbar.replaceChildren();
    clearPdfCache();
  }

  function openFromButton(btn) {
    const workspace = workspaceFrom(btn);
    const scoreId = btn.dataset.scoreId;
    if (!scoreId) return;
    const scoreIds = parseJsonAttr(workspace, "scoreIds", []);
    const navQuery = parseJsonAttr(workspace, "viewNav", {});
    const ctx = ctxFromViewUrl(btn.getAttribute("href") || btn.href);
    open(scoreId, scoreIds, navQuery, ctx);
  }

  function bindSwipe() {
    let startX = null;
    let startY = null;
    let swipeTarget = null;
    content.addEventListener("touchstart", (e) => {
      startX = e.changedTouches[0].screenX;
      startY = e.changedTouches[0].screenY;
      swipeTarget = e.target;
    }, { passive: true });
    content.addEventListener("touchend", (e) => {
      if (startX === null || startY === null) return;
      const dx = e.changedTouches[0].screenX - startX;
      const dy = e.changedTouches[0].screenY - startY;
      startX = null;
      startY = null;
      if (swipeTarget?.closest(".viewer-pdf-frame")) return;
      if (Math.abs(dx) < SWIPE_THRESHOLD_PX) return;
      if (Math.abs(dx) < Math.abs(dy) * SWIPE_HORIZONTAL_DOMINANCE) return;
      if (dx > 0 && prevBtn.dataset.targetId) open(prevBtn.dataset.targetId, context.scoreIds, context.navQuery);
      if (dx < 0 && nextBtn.dataset.targetId) open(nextBtn.dataset.targetId, context.scoreIds, context.navQuery);
      swipeTarget = null;
    }, { passive: true });
  }

  function bindOverlay() {
    if (redirectLegacyViewScoreParam()) return;
    overlay = document.getElementById("score-viewer-overlay");
    if (!overlay) return;
    pdfWorkerUrl = overlay.dataset.pdfWorker || "";
    panel = document.getElementById("score-viewer-panel");
    toolbar = document.getElementById("score-viewer-toolbar");
    content = document.getElementById("score-viewer-content");
    titleEl = document.getElementById("score-viewer-title");
    navEl = document.getElementById("score-viewer-nav");
    posEl = document.getElementById("score-viewer-pos");
    prevBtn = document.getElementById("score-viewer-prev");
    nextBtn = document.getElementById("score-viewer-next");
    downloadEl = document.getElementById("score-viewer-download");
    printBtn = document.getElementById("score-viewer-print");
    fullscreenBtn = document.getElementById("score-viewer-fullscreen");
    pdfPageNavEl = document.getElementById("score-viewer-pdf-page");
    pdfScrollModeBtn = document.getElementById("score-viewer-pdf-scroll-mode");
    document.getElementById("score-viewer-close").addEventListener("click", close);
    pdfScrollModeBtn?.addEventListener("click", togglePdfScrollMode);
    printBtn?.addEventListener("click", printVisiblePane);
    updatePdfScrollModeUi();
    prevBtn.addEventListener("click", () => {
      if (prevBtn.dataset.targetId) open(prevBtn.dataset.targetId, context.scoreIds, context.navQuery);
    });
    nextBtn.addEventListener("click", () => {
      if (nextBtn.dataset.targetId) open(nextBtn.dataset.targetId, context.scoreIds, context.navQuery);
    });
    fullscreenBtn.addEventListener("click", () => {
      if (fullscreenElement() === panel) {
        document.exitFullscreen?.() || document.webkitExitFullscreen?.();
        return;
      }
      panel.requestFullscreen?.() || panel.webkitRequestFullscreen?.();
    });
    const onFullscreenChange = () => {
      updateFullscreenIcon();
      schedulePdfPaneRelayout();
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("webkitfullscreenchange", onFullscreenChange);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !overlay.classList.contains("hidden")) close();
    });
    bindSwipe();
    content.addEventListener("click", (e) => {
      const prevArrow = e.target.closest(".viewer-pdf-page-arrow-prev");
      const nextArrow = e.target.closest(".viewer-pdf-page-arrow-next");
      const upArrow = e.target.closest(".viewer-pdf-page-arrow-up");
      const downArrow = e.target.closest(".viewer-pdf-page-arrow-down");
      const arrow = prevArrow || nextArrow || upArrow || downArrow;
      if (!arrow) return;
      const mount = arrow.closest(".viewer-pdf-frame")?.querySelector(".viewer-pdf-mount");
      if (!mount) return;
      if ((prevArrow || nextArrow) && !mount.classList.contains("viewer-pdf-scroll-horizontal")) return;
      if ((upArrow || downArrow) && !mount.classList.contains("viewer-pdf-scroll-vertical-pages")) return;
      e.preventDefault();
      e.stopPropagation();
      const delta = (prevArrow || upArrow) ? -1 : 1;
      navigatePdfPage(mount, delta);
    });
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".score-view-btn");
      if (!btn) return;
      if (isStandaloneViewPage()) return;
      e.preventDefault();
      e.stopPropagation();
      openFromButton(btn);
    });
    const page = scoreViewPage();
    if (page) {
      const scoreId = page.dataset.scoreId;
      if (scoreId) open(scoreId, [], viewPageNavQuery(), viewPageCtx());
    }
  }

  window.ScoreViewer = { open, close, openFromButton };

  document.addEventListener("DOMContentLoaded", bindOverlay);
})();
