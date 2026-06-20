(function () {
  "use strict";

  const TOOL_TEXT = "text";
  const TOOL_PEN = "pen";
  const TOOL_HIGHLIGHT = "highlight";
  const TOOL_SYMBOL = "symbol";
  const TOOL_ERASER = "eraser";
  const TOOLS = [TOOL_TEXT, TOOL_PEN, TOOL_HIGHLIGHT, TOOL_SYMBOL, TOOL_ERASER];
  const TOOL_LABELS = {
    [TOOL_TEXT]: "Text",
    [TOOL_PEN]: "Pen",
    [TOOL_HIGHLIGHT]: "Highlight",
    [TOOL_SYMBOL]: "Symbol",
    [TOOL_ERASER]: "Eraser",
  };
  const STORAGE_LOCAL_PREFIX = "scorestore-score-notes-";
  const SAVE_DEBOUNCE_MS = 500;
  const MARK_SIZE_RATIOS = [0.018, 0.022, 0.025, 0.030, 0.036];
  const NOTE_MARK_SIZE_RATIOS = [0.014, 0.016, 0.018, 0.021, 0.025];
  const DEFAULT_MARK_SIZE_INDEX = 2;
  const NOTE_SYMBOL_DRAW_HEIGHT = 20;
  const NOTE_HEAD_RX = 5;
  const NOTE_HEAD_RY = 3.5;
  const NOTE_STEM_ATTACH_ANGLE = -0.7;
  const NOTE_STEM_TOP = -17;
  const NOTE_STEM_WIDTH = 1.2;
  const NOTE_STROKE_WIDTH = 1.3;
  const NOTE_FLAG_CURVE_X = 1.6;
  const NOTE_FLAG_CURVE_Y = 1.3;
  const NOTE_FLAG_END_X = 4;
  const NOTE_FLAG_END_Y = 6.5;
  const NOTE_FLAG_MID_Y_RATIO = 0.55;
  const SYMBOL_ANCHOR_CENTER = "center";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const DRAG_MOVE_SYMBOL = "move-symbol";
  const PEN_WIDTH_RATIOS = [0.0008, 0.0015, 0.0025, 0.004, 0.006];
  const DEFAULT_PEN_WIDTH_INDEX = 1;
  const MIN_PEN_POINT_DISTANCE = 0.002;
  const ERASER_HIT_PADDING_PX = 4;
  const COLOR_RED = "#dc2626";
  const COLOR_YELLOW = "#facc15";
  const COLOR_BLUE = "#2563eb";
  const COLOR_GREEN = "#16a34a";
  const COLOR_BLACK = "#171717";
  const COLOR_PALETTE = [COLOR_RED, COLOR_YELLOW, COLOR_BLUE, COLOR_GREEN, COLOR_BLACK];
  const TOOL_DEFAULT_COLORS = {
    [TOOL_TEXT]: COLOR_RED,
    [TOOL_PEN]: COLOR_RED,
    [TOOL_HIGHLIGHT]: COLOR_YELLOW,
    [TOOL_SYMBOL]: COLOR_RED,
  };
  const TEXT_SYMBOLS = [
    "♭", "♮", "♯", "<", ">",
    "p", "pp", "mp", "mf", "f", "ff", "sfz", "cresc", "dim", "rit", "accel", "𝄐",
  ];
  const DYNAMIC_SYMBOLS = new Set(["p", "pp", "mp", "mf", "f", "ff"]);
  const NOTE_SYMBOL_IDS = ["note-whole", "note-half", "note-quarter", "note-eighth"];
  const NOTE_SYMBOL_LABELS = {
    "note-whole": "Whole note",
    "note-half": "Half note",
    "note-quarter": "Quarter note",
    "note-eighth": "Eighth note",
  };

  let overlay = null;
  let notesToolbar = null;
  let notesToggleBtn = null;
  let userId = "";
  let storageMode = "none";
  let notesModeActive = false;
  let activeTool = TOOL_PEN;
  let activeColor = COLOR_RED;
  let activePenWidth = PEN_WIDTH_RATIOS[DEFAULT_PEN_WIDTH_INDEX];
  let activeMarkSizeIndex = DEFAULT_MARK_SIZE_INDEX;
  let activeSymbolId = TEXT_SYMBOLS[0];
  let scoreId = "";
  let fileId = "";
  let scoreNotes = { files: {} };
  let saveTimer = null;
  let savePending = false;
  let localNotesCache = null;
  let dragState = null;
  let textInputEl = null;
  let slotObservers = new WeakMap();

  function notesEnabled() {
    return storageMode === "server" || storageMode === "local";
  }

  function localStorageKey() {
    return `${STORAGE_LOCAL_PREFIX}${userId}`;
  }

  function loadLocalNotesStore() {
    if (localNotesCache) return localNotesCache;
    try {
      localNotesCache = JSON.parse(localStorage.getItem(localStorageKey()) || "{}");
    } catch {
      localNotesCache = {};
    }
    if (!localNotesCache.scores) localNotesCache.scores = {};
    return localNotesCache;
  }

  function writeLocalNotesStore() {
    if (storageMode !== "local" || !userId) return;
    localStorage.setItem(localStorageKey(), JSON.stringify(loadLocalNotesStore()));
  }

  function currentFileNotes() {
    if (!scoreNotes.files[fileId]) scoreNotes.files[fileId] = { pages: {} };
    return scoreNotes.files[fileId];
  }

  function pageAnnotations(pageNum) {
    const fileNotes = currentFileNotes();
    const key = String(pageNum);
    if (!fileNotes.pages[key]) fileNotes.pages[key] = [];
    return fileNotes.pages[key];
  }

  function annotationId() {
    return `n-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function slotMetrics(slot) {
    const canvas = slot.querySelector(".viewer-pdf-page");
    const rect = (canvas || slot).getBoundingClientRect();
    return {
      width: Math.max(rect.width, 1),
      height: Math.max(rect.height, 1),
    };
  }

  function normFromEvent(slot, clientX, clientY) {
    const canvas = slot.querySelector(".viewer-pdf-page") || slot;
    const rect = canvas.getBoundingClientRect();
    return {
      x: (clientX - rect.left) / rect.width,
      y: (clientY - rect.top) / rect.height,
    };
  }

  function clampNorm(value) {
    return Math.max(0, Math.min(1, value));
  }

  function scheduleSave() {
    savePending = true;
    if (saveTimer) clearTimeout(saveTimer);
    if (storageMode === "local") {
      persistNotes();
      savePending = false;
      return;
    }
    saveTimer = setTimeout(() => {
      saveTimer = null;
      persistNotes();
    }, SAVE_DEBOUNCE_MS);
  }

  function flushSave() {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    if (savePending || storageMode === "server") persistNotes();
  }

  async function persistNotes() {
    if (!notesEnabled() || !scoreId) return;
    savePending = false;
    if (storageMode === "local") {
      const store = loadLocalNotesStore();
      const hasFiles = scoreNotes.files && Object.keys(scoreNotes.files).length > 0;
      if (hasFiles) store.scores[scoreId] = scoreNotes;
      else delete store.scores[scoreId];
      writeLocalNotesStore();
      return;
    }
    const fetchFn = window.Csrf?.fetch || fetch;
    const url = window.Csrf?.appendScopeParams
      ? window.Csrf.appendScopeParams(`/scores/${scoreId}/notes`)
      : `/scores/${scoreId}/notes`;
    try {
      await fetchFn(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: scoreNotes.files }),
      });
    } catch {
      /* save failure is silent; notes remain in memory */
    }
  }

  async function loadNotesForScore(id) {
    scoreNotes = { files: {} };
    if (!notesEnabled()) return;
    if (storageMode === "local") {
      const store = loadLocalNotesStore();
      const entry = store.scores?.[id];
      if (entry?.files) scoreNotes = { files: structuredClone(entry.files) };
      return;
    }
    const fetchFn = window.Csrf?.fetch || fetch;
    const url = window.Csrf?.appendScopeParams
      ? window.Csrf.appendScopeParams(`/scores/${id}/notes`)
      : `/scores/${id}/notes`;
    try {
      const res = await fetchFn(url);
      if (!res.ok) return;
      const data = await res.json();
      if (data?.files) scoreNotes = { files: data.files };
    } catch {
      /* keep empty notes */
    }
  }

  function symbolId(ann) {
    return ann.symbol || ann.text || "";
  }

  function isNoteSymbolId(id) {
    return NOTE_SYMBOL_IDS.includes(id);
  }

  function isDynamicSymbol(id) {
    return DYNAMIC_SYMBOLS.has(id);
  }

  function noteKindFromId(id) {
    return id.replace(/^note-/, "");
  }

  function annotationById(pageNum, annId) {
    return pageAnnotations(pageNum).find((item) => item.id === annId) || null;
  }

  function activeTextSize() {
    return MARK_SIZE_RATIOS[activeMarkSizeIndex];
  }

  function activeNoteSymbolSize() {
    return NOTE_MARK_SIZE_RATIOS[activeMarkSizeIndex];
  }

  function textSizeFallback(ann) {
    return ann.size || MARK_SIZE_RATIOS[DEFAULT_MARK_SIZE_INDEX];
  }

  function noteSymbolSizeFallback(ann) {
    return ann.size || NOTE_MARK_SIZE_RATIOS[DEFAULT_MARK_SIZE_INDEX];
  }

  function symbolScale(ann, metrics) {
    return noteSymbolSizeFallback(ann) * metrics.height / NOTE_SYMBOL_DRAW_HEIGHT;
  }

  function stemAttachPoint() {
    return {
      x: NOTE_HEAD_RX * Math.cos(NOTE_STEM_ATTACH_ANGLE),
      y: NOTE_HEAD_RY * Math.sin(NOTE_STEM_ATTACH_ANGLE),
    };
  }

  function svgEllipse(cx, cy, rx, ry, color, filled) {
    const ellipse = document.createElementNS(SVG_NS, "ellipse");
    ellipse.setAttribute("cx", String(cx));
    ellipse.setAttribute("cy", String(cy));
    ellipse.setAttribute("rx", String(rx));
    ellipse.setAttribute("ry", String(ry));
    if (filled) {
      ellipse.setAttribute("fill", color);
      ellipse.setAttribute("stroke", "none");
    } else {
      ellipse.setAttribute("fill", "none");
      ellipse.setAttribute("stroke", color);
      ellipse.setAttribute("stroke-width", String(NOTE_STROKE_WIDTH));
    }
    return ellipse;
  }

  function svgStem(color) {
    const attach = stemAttachPoint();
    const stem = document.createElementNS(SVG_NS, "line");
    stem.setAttribute("x1", String(attach.x));
    stem.setAttribute("y1", String(attach.y));
    stem.setAttribute("x2", String(attach.x));
    stem.setAttribute("y2", String(NOTE_STEM_TOP));
    stem.setAttribute("stroke", color);
    stem.setAttribute("stroke-width", String(NOTE_STEM_WIDTH));
    stem.setAttribute("stroke-linecap", "butt");
    return stem;
  }

  function svgFlag(color) {
    const attach = stemAttachPoint();
    const flag = document.createElementNS(SVG_NS, "path");
    flag.setAttribute(
      "d",
      `M ${attach.x + NOTE_STEM_WIDTH / 2} ${NOTE_STEM_TOP}`
      + ` c ${NOTE_FLAG_CURVE_X} ${NOTE_FLAG_CURVE_Y}`
      + `, ${NOTE_FLAG_END_X} ${NOTE_FLAG_END_Y * NOTE_FLAG_MID_Y_RATIO}`
      + `, ${NOTE_FLAG_END_X} ${NOTE_FLAG_END_Y}`,
    );
    flag.setAttribute("fill", color);
    flag.setAttribute("stroke", "none");
    return flag;
  }

  function appendNoteShape(parent, noteKind, color) {
    if (noteKind === "whole") {
      parent.appendChild(svgEllipse(0, 0, NOTE_HEAD_RX, NOTE_HEAD_RY, color, false));
      return;
    }
    if (noteKind === "half") {
      parent.appendChild(svgStem(color));
      parent.appendChild(svgEllipse(0, 0, NOTE_HEAD_RX, NOTE_HEAD_RY, color, false));
      return;
    }
    if (noteKind === "quarter") {
      parent.appendChild(svgStem(color));
      parent.appendChild(svgEllipse(0, 0, NOTE_HEAD_RX, NOTE_HEAD_RY, color, true));
      return;
    }
    if (noteKind === "eighth") {
      parent.appendChild(svgStem(color));
      parent.appendChild(svgEllipse(0, 0, NOTE_HEAD_RX, NOTE_HEAD_RY, color, true));
      parent.appendChild(svgFlag(color));
    }
  }

  function notePreviewViewBox() {
    const pad = 2;
    const left = -NOTE_HEAD_RX - pad;
    const top = NOTE_STEM_TOP - pad;
    const width = NOTE_HEAD_RX * 2 + NOTE_FLAG_END_X + pad * 2;
    const height = -NOTE_STEM_TOP + NOTE_HEAD_RY + pad;
    return `${left} ${top} ${width} ${height}`;
  }

  function createNotePreviewSvg(noteId, color) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", notePreviewViewBox());
    svg.classList.add("viewer-notes-symbol-preview");
    const group = document.createElementNS(SVG_NS, "g");
    appendNoteShape(group, noteKindFromId(noteId), color);
    svg.appendChild(group);
    return svg;
  }

  function renderNoteSymbolMark(svg, ann, slot) {
    const metrics = slotMetrics(slot);
    const cx = ann.x * metrics.width;
    const cy = ann.y * metrics.height;
    const scale = symbolScale(ann, metrics);
    const group = document.createElementNS(SVG_NS, "g");
    group.classList.add("viewer-notes-mark", "viewer-notes-mark-symbol", "viewer-notes-mark-note");
    group.dataset.annId = ann.id;
    group.setAttribute("transform", `translate(${cx} ${cy}) scale(${scale})`);
    appendNoteShape(group, noteKindFromId(symbolId(ann)), ann.color || COLOR_RED);
    svg.appendChild(group);
  }

  function renderTextSymbolMark(svg, ann, slot, textClass) {
    const metrics = slotMetrics(slot);
    const centered = ann.anchor === SYMBOL_ANCHOR_CENTER;
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", String(ann.x * metrics.width));
    text.setAttribute("y", String(ann.y * metrics.height));
    text.setAttribute("fill", ann.color || COLOR_RED);
    text.setAttribute("font-size", String(textSizeFallback(ann) * metrics.height));
    text.setAttribute("text-anchor", centered ? "middle" : "start");
    text.setAttribute("dominant-baseline", centered ? "central" : "hanging");
    text.textContent = symbolId(ann);
    text.dataset.annId = ann.id;
    text.classList.add("viewer-notes-mark", textClass);
    if (isDynamicSymbol(symbolId(ann))) {
      text.classList.add("viewer-notes-mark-dynamic");
    }
    svg.appendChild(text);
  }

  function removeAnnotation(pageNum, annId) {
    const list = pageAnnotations(pageNum);
    const idx = list.findIndex((item) => item.id === annId);
    if (idx >= 0) list.splice(idx, 1);
    scheduleSave();
  }

  function renderAnnotationSvg(svg, ann, slot) {
    const metrics = slotMetrics(slot);
    const minDim = Math.min(metrics.width, metrics.height);
    if (ann.type === TOOL_PEN && ann.points?.length) {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const d = ann.points.map((pt, i) => {
        const x = pt[0] * metrics.width;
        const y = pt[1] * metrics.height;
        return `${i === 0 ? "M" : "L"} ${x} ${y}`;
      }).join(" ");
      path.setAttribute("d", d);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", ann.color || COLOR_RED);
      path.setAttribute("stroke-width", String((ann.width || activePenWidth) * minDim));
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("stroke-linejoin", "round");
      path.dataset.annId = ann.id;
      path.classList.add("viewer-notes-mark", "viewer-notes-mark-pen");
      svg.appendChild(path);
      return;
    }
    if (ann.type === TOOL_HIGHLIGHT) {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(ann.x * metrics.width));
      rect.setAttribute("y", String(ann.y * metrics.height));
      rect.setAttribute("width", String(ann.w * metrics.width));
      rect.setAttribute("height", String(ann.h * metrics.height));
      rect.setAttribute("fill", ann.color || COLOR_YELLOW);
      rect.setAttribute("class", "viewer-notes-mark viewer-notes-mark-highlight");
      rect.dataset.annId = ann.id;
      svg.appendChild(rect);
      return;
    }
    if (ann.type === TOOL_TEXT) {
      renderTextSymbolMark(svg, ann, slot, "viewer-notes-mark-text");
      return;
    }
    if (ann.type === TOOL_SYMBOL) {
      const id = symbolId(ann);
      if (isNoteSymbolId(id)) {
        renderNoteSymbolMark(svg, ann, slot);
        return;
      }
      renderTextSymbolMark(svg, ann, slot, "viewer-notes-mark-symbol");
    }
  }

  function renderSlotNotes(slot, pageNum) {
    let layer = slot.querySelector(".viewer-notes-layer");
    if (!layer) {
      layer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      layer.classList.add("viewer-notes-layer");
      layer.setAttribute("aria-hidden", "true");
      slot.appendChild(layer);
      bindSlotPointerEvents(slot, layer);
      observeSlot(slot);
    }
    layer.replaceChildren();
    const annotations = pageAnnotations(pageNum);
    annotations.forEach((ann) => renderAnnotationSvg(layer, ann, slot));
    syncLayerSize(slot, layer);
    layer.classList.toggle("viewer-notes-layer-editable", notesModeActive);
    layer.classList.toggle("viewer-notes-layer-eraser", notesModeActive && activeTool === TOOL_ERASER);
    const hoverId = slot.dataset.eraserHoverId;
    if (hoverId) {
      layer.querySelector(`.viewer-notes-mark[data-ann-id="${hoverId}"]`)
        ?.classList.add("viewer-notes-mark-eraser-hover");
    }
  }

  function syncLayerSize(slot, layer) {
    const canvas = slot.querySelector(".viewer-pdf-page");
    if (!canvas) return;
    const w = canvas.offsetWidth || canvas.clientWidth;
    const h = canvas.offsetHeight || canvas.clientHeight;
    layer.setAttribute("width", String(w));
    layer.setAttribute("height", String(h));
    layer.style.width = `${w}px`;
    layer.style.height = `${h}px`;
    layer.style.left = `${canvas.offsetLeft}px`;
    layer.style.top = `${canvas.offsetTop}px`;
  }

  function observeSlot(slot) {
    if (slotObservers.has(slot)) return;
    const canvas = slot.querySelector(".viewer-pdf-page");
    if (!canvas) return;
    const observer = new ResizeObserver(() => {
      const layer = slot.querySelector(".viewer-notes-layer");
      const pageNum = Number(slot.dataset.pageNum);
      if (layer && pageNum) renderSlotNotes(slot, pageNum);
    });
    observer.observe(canvas);
    slotObservers.set(slot, observer);
  }

  function hitAnnotation(slot, pageNum, clientX, clientY) {
    const layer = slot.querySelector(".viewer-notes-layer");
    if (!layer) return null;
    const marks = layer.querySelectorAll(".viewer-notes-mark");
    for (let i = marks.length - 1; i >= 0; i -= 1) {
      const mark = marks[i];
      const rect = mark.getBoundingClientRect();
      const pad = ERASER_HIT_PADDING_PX;
      if (
        clientX >= rect.left - pad
        && clientX <= rect.right + pad
        && clientY >= rect.top - pad
        && clientY <= rect.bottom + pad
      ) {
        return mark.dataset.annId;
      }
    }
    return null;
  }

  function clearEraserHover(slot) {
    delete slot.dataset.eraserHoverId;
    slot.querySelectorAll(".viewer-notes-mark-eraser-hover").forEach((mark) => {
      mark.classList.remove("viewer-notes-mark-eraser-hover");
    });
  }

  function setEraserHover(slot, annId) {
    if (slot.dataset.eraserHoverId === annId) return;
    clearEraserHover(slot);
    if (!annId) return;
    slot.dataset.eraserHoverId = annId;
    const mark = slot.querySelector(`.viewer-notes-mark[data-ann-id="${annId}"]`);
    mark?.classList.add("viewer-notes-mark-eraser-hover");
  }

  function updateEraserHoverFromPointer(slot, clientX, clientY) {
    const pageNum = Number(slot.dataset.pageNum);
    if (!pageNum) return;
    setEraserHover(slot, hitAnnotation(slot, pageNum, clientX, clientY));
  }

  function syncEraserLayerMode() {
    const eraser = notesModeActive && activeTool === TOOL_ERASER;
    document.querySelectorAll(".viewer-notes-layer").forEach((layer) => {
      layer.classList.toggle("viewer-notes-layer-eraser", eraser);
    });
    if (!eraser) {
      document.querySelectorAll(".viewer-pdf-page-slot").forEach(clearEraserHover);
    }
  }

  function cancelTextInput() {
    if (!textInputEl) return;
    textInputEl.remove();
    textInputEl = null;
  }

  function commitTextInput(slot, pageNum) {
    if (!textInputEl) return;
    const value = textInputEl.value.trim();
    const x = Number(textInputEl.dataset.normX);
    const y = Number(textInputEl.dataset.normY);
    cancelTextInput();
    if (!value) return;
    pageAnnotations(pageNum).push({
      id: annotationId(),
      type: TOOL_TEXT,
      x,
      y,
      text: value,
      color: activeColor,
      size: activeTextSize(),
    });
    scheduleSave();
    renderSlotNotes(slot, pageNum);
  }

  function startTextInput(slot, pageNum, norm) {
    cancelTextInput();
    const canvas = slot.querySelector(".viewer-pdf-page") || slot;
    textInputEl = document.createElement("input");
    textInputEl.type = "text";
    textInputEl.className = "viewer-notes-text-input";
    textInputEl.dataset.normX = String(norm.x);
    textInputEl.dataset.normY = String(norm.y);
    textInputEl.style.left = `${canvas.offsetLeft + norm.x * canvas.offsetWidth}px`;
    textInputEl.style.top = `${canvas.offsetTop + norm.y * canvas.offsetHeight}px`;
    slot.appendChild(textInputEl);
    textInputEl.focus();
    textInputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        commitTextInput(slot, pageNum);
      }
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        cancelTextInput();
      }
    });
    textInputEl.addEventListener("blur", () => commitTextInput(slot, pageNum));
  }

  function placeSymbol(slot, pageNum, norm) {
    const entry = {
      id: annotationId(),
      type: TOOL_SYMBOL,
      symbol: activeSymbolId,
      x: clampNorm(norm.x),
      y: clampNorm(norm.y),
      color: activeColor,
      size: isNoteSymbolId(activeSymbolId) ? activeNoteSymbolSize() : activeTextSize(),
    };
    if (!isNoteSymbolId(activeSymbolId)) {
      entry.anchor = SYMBOL_ANCHOR_CENTER;
    }
    pageAnnotations(pageNum).push(entry);
    scheduleSave();
    renderSlotNotes(slot, pageNum);
  }

  function startSymbolMove(slot, layer, pageNum, annId, pointerId, norm) {
    const ann = annotationById(pageNum, annId);
    if (!ann || ann.type !== TOOL_SYMBOL) return false;
    layer.setPointerCapture(pointerId);
    dragState = {
      slot,
      pageNum,
      tool: DRAG_MOVE_SYMBOL,
      pointerId,
      annId,
      grabOffset: { x: norm.x - ann.x, y: norm.y - ann.y },
    };
    slot.querySelector(`.viewer-notes-mark[data-ann-id="${annId}"]`)
      ?.classList.add("viewer-notes-mark-dragging");
    return true;
  }

  function bindSlotPointerEvents(slot, layer) {
    layer.addEventListener("pointerdown", (e) => {
      if (!notesModeActive) return;
      const pageNum = Number(slot.dataset.pageNum);
      if (!pageNum) return;
      const norm = normFromEvent(slot, e.clientX, e.clientY);
      if (activeTool === TOOL_ERASER) {
        const annId = hitAnnotation(slot, pageNum, e.clientX, e.clientY);
        if (annId) {
          removeAnnotation(pageNum, annId);
          clearEraserHover(slot);
          renderSlotNotes(slot, pageNum);
        }
        return;
      }
      const hitId = hitAnnotation(slot, pageNum, e.clientX, e.clientY);
      if (hitId) {
        const hitAnn = annotationById(pageNum, hitId);
        if (hitAnn?.type === TOOL_SYMBOL) {
          e.preventDefault();
          startSymbolMove(slot, layer, pageNum, hitId, e.pointerId, norm);
          return;
        }
      }
      if (activeTool === TOOL_TEXT) {
        e.preventDefault();
        startTextInput(slot, pageNum, norm);
        return;
      }
      if (activeTool === TOOL_SYMBOL) {
        e.preventDefault();
        placeSymbol(slot, pageNum, norm);
        return;
      }
      if (activeTool === TOOL_PEN || activeTool === TOOL_HIGHLIGHT) {
        e.preventDefault();
        layer.setPointerCapture(e.pointerId);
        dragState = {
          slot,
          pageNum,
          tool: activeTool,
          pointerId: e.pointerId,
          start: norm,
          current: norm,
          previewEl: null,
        };
        if (activeTool === TOOL_PEN) {
          dragState.ann = {
            id: annotationId(),
            type: TOOL_PEN,
            color: activeColor,
            width: activePenWidth,
            points: [[clampNorm(norm.x), clampNorm(norm.y)]],
          };
        }
      }
    });
    layer.addEventListener("pointermove", (e) => {
      if (!notesModeActive || activeTool !== TOOL_ERASER || dragState) return;
      updateEraserHoverFromPointer(slot, e.clientX, e.clientY);
    });
    layer.addEventListener("pointerleave", () => {
      clearEraserHover(slot);
    });
    layer.addEventListener("pointermove", (e) => {
      if (!dragState || dragState.pointerId !== e.pointerId) return;
      const norm = normFromEvent(dragState.slot, e.clientX, e.clientY);
      dragState.current = norm;
      if (dragState.tool === DRAG_MOVE_SYMBOL) {
        const ann = annotationById(dragState.pageNum, dragState.annId);
        if (ann) {
          ann.x = clampNorm(norm.x - dragState.grabOffset.x);
          ann.y = clampNorm(norm.y - dragState.grabOffset.y);
          renderSlotNotes(dragState.slot, dragState.pageNum);
          dragState.slot.querySelector(`.viewer-notes-mark[data-ann-id="${dragState.annId}"]`)
            ?.classList.add("viewer-notes-mark-dragging");
        }
        return;
      }
      if (dragState.tool === TOOL_PEN && dragState.ann) {
        const pts = dragState.ann.points;
        const last = pts[pts.length - 1];
        const dx = norm.x - last[0];
        const dy = norm.y - last[1];
        if (Math.hypot(dx, dy) >= MIN_PEN_POINT_DISTANCE) {
          pts.push([clampNorm(norm.x), clampNorm(norm.y)]);
        }
        renderSlotNotes(dragState.slot, dragState.pageNum);
        const layerEl = dragState.slot.querySelector(".viewer-notes-layer");
        if (layerEl && dragState.ann) {
          renderAnnotationSvg(layerEl, dragState.ann, dragState.slot);
        }
      }
      if (dragState.tool === TOOL_HIGHLIGHT) {
        renderSlotNotes(dragState.slot, dragState.pageNum);
        const layerEl = dragState.slot.querySelector(".viewer-notes-layer");
        if (!layerEl) return;
        const metrics = slotMetrics(dragState.slot);
        const x = Math.min(dragState.start.x, norm.x);
        const y = Math.min(dragState.start.y, norm.y);
        const w = Math.abs(norm.x - dragState.start.x);
        const h = Math.abs(norm.y - dragState.start.y);
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(x * metrics.width));
        rect.setAttribute("y", String(y * metrics.height));
        rect.setAttribute("width", String(w * metrics.width));
        rect.setAttribute("height", String(h * metrics.height));
        rect.setAttribute("fill", activeColor);
        rect.classList.add("viewer-notes-mark", "viewer-notes-mark-highlight", "viewer-notes-mark-preview");
        layerEl.appendChild(rect);
      }
    });
    const finishDrag = (e) => {
      if (!dragState || dragState.pointerId !== e.pointerId) return;
      const { slot: dragSlot, pageNum, tool, start, current, ann, annId } = dragState;
      dragState = null;
      try {
        layer.releasePointerCapture(e.pointerId);
      } catch {
        /* pointer already released */
      }
      if (tool === DRAG_MOVE_SYMBOL) {
        dragSlot.querySelector(".viewer-notes-mark-dragging")
          ?.classList.remove("viewer-notes-mark-dragging");
        scheduleSave();
        renderSlotNotes(dragSlot, pageNum);
        return;
      }
      if (tool === TOOL_PEN && ann && ann.points.length > 1) {
        pageAnnotations(pageNum).push(ann);
        scheduleSave();
      }
      if (tool === TOOL_HIGHLIGHT) {
        const x = Math.min(start.x, current.x);
        const y = Math.min(start.y, current.y);
        const w = Math.abs(current.x - start.x);
        const h = Math.abs(current.y - start.y);
        if (w > MIN_PEN_POINT_DISTANCE && h > MIN_PEN_POINT_DISTANCE) {
          pageAnnotations(pageNum).push({
            id: annotationId(),
            type: TOOL_HIGHLIGHT,
            x: clampNorm(x),
            y: clampNorm(y),
            w: clampNorm(w),
            h: clampNorm(h),
            color: activeColor,
          });
          scheduleSave();
        }
      }
      renderSlotNotes(dragSlot, pageNum);
    };
    layer.addEventListener("pointerup", finishDrag);
    layer.addEventListener("pointercancel", finishDrag);
  }

  function applyToolDefaultColor(tool) {
    activeColor = TOOL_DEFAULT_COLORS[tool] || COLOR_RED;
    updateColorSwatches();
  }

  function updateToolButtons() {
    notesToolbar?.querySelectorAll(".viewer-notes-tool").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tool === activeTool);
    });
    const symbolsPanel = notesToolbar?.querySelector(".viewer-notes-symbols");
    symbolsPanel?.classList.toggle("hidden", activeTool !== TOOL_SYMBOL);
    const penSizesPanel = notesToolbar?.querySelector(".viewer-notes-pen-sizes");
    penSizesPanel?.classList.toggle("hidden", activeTool !== TOOL_PEN);
    const markSizesPanel = notesToolbar?.querySelector(".viewer-notes-mark-sizes");
    markSizesPanel?.classList.toggle("hidden", activeTool !== TOOL_TEXT && activeTool !== TOOL_SYMBOL);
    syncEraserLayerMode();
  }

  function updateMarkSizeButtons() {
    notesToolbar?.querySelectorAll(".viewer-notes-mark-size-btn").forEach((btn) => {
      const idx = Number(btn.dataset.markSizeIndex);
      btn.classList.toggle("active", idx === activeMarkSizeIndex);
    });
  }

  function updatePenSizeButtons() {
    notesToolbar?.querySelectorAll(".viewer-notes-pen-size-btn").forEach((btn) => {
      const idx = Number(btn.dataset.penSizeIndex);
      btn.classList.toggle("active", PEN_WIDTH_RATIOS[idx] === activePenWidth);
    });
  }

  function updateColorSwatches() {
    notesToolbar?.querySelectorAll(".viewer-notes-color-swatch").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.color === activeColor);
    });
  }

  function updateSymbolButtons() {
    notesToolbar?.querySelectorAll(".viewer-notes-symbol-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.symbolId === activeSymbolId);
    });
  }

  function appendTextSymbolButton(parent, symbol) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "viewer-notes-symbol-btn";
    if (isDynamicSymbol(symbol)) {
      btn.classList.add("viewer-notes-symbol-btn-dynamic");
    }
    btn.dataset.symbolId = symbol;
    btn.textContent = symbol;
    btn.addEventListener("click", () => {
      activeSymbolId = symbol;
      updateSymbolButtons();
    });
    parent.appendChild(btn);
  }

  function appendNoteSymbolButton(parent, noteId) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "viewer-notes-symbol-btn viewer-notes-symbol-btn-note";
    btn.dataset.symbolId = noteId;
    btn.title = NOTE_SYMBOL_LABELS[noteId] || noteId;
    btn.appendChild(createNotePreviewSvg(noteId, COLOR_BLACK));
    btn.addEventListener("click", () => {
      activeSymbolId = noteId;
      updateSymbolButtons();
    });
    parent.appendChild(btn);
  }

  function buildToolbar() {
    if (!notesToolbar) return;
    notesToolbar.replaceChildren();
    const toolsGroup = document.createElement("div");
    toolsGroup.className = "viewer-notes-tools";
    toolsGroup.setAttribute("role", "group");
    toolsGroup.setAttribute("aria-label", "Annotation tools");
    TOOLS.forEach((tool) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "viewer-notes-tool";
      btn.dataset.tool = tool;
      btn.textContent = TOOL_LABELS[tool];
      btn.addEventListener("click", () => {
        activeTool = tool;
        applyToolDefaultColor(tool);
        updateToolButtons();
      });
      toolsGroup.appendChild(btn);
    });
    notesToolbar.appendChild(toolsGroup);
    const colorsGroup = document.createElement("div");
    colorsGroup.className = "viewer-notes-colors";
    colorsGroup.setAttribute("role", "group");
    colorsGroup.setAttribute("aria-label", "Colors");
    COLOR_PALETTE.forEach((color) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "viewer-notes-color-swatch";
      btn.dataset.color = color;
      btn.title = color;
      btn.addEventListener("click", () => {
        activeColor = color;
        updateColorSwatches();
      });
      colorsGroup.appendChild(btn);
    });
    notesToolbar.appendChild(colorsGroup);
    const penSizesGroup = document.createElement("div");
    penSizesGroup.className = "viewer-notes-pen-sizes hidden";
    penSizesGroup.setAttribute("role", "group");
    penSizesGroup.setAttribute("aria-label", "Pen size");
    PEN_WIDTH_RATIOS.forEach((ratio, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "viewer-notes-pen-size-btn";
      btn.dataset.penSizeIndex = String(index);
      btn.title = `Pen size ${index + 1}`;
      const dot = document.createElement("span");
      dot.className = "viewer-notes-pen-size-dot";
      dot.setAttribute("aria-hidden", "true");
      btn.appendChild(dot);
      btn.addEventListener("click", () => {
        activePenWidth = ratio;
        updatePenSizeButtons();
      });
      penSizesGroup.appendChild(btn);
    });
    notesToolbar.appendChild(penSizesGroup);
    const markSizesGroup = document.createElement("div");
    markSizesGroup.className = "viewer-notes-mark-sizes hidden";
    markSizesGroup.setAttribute("role", "group");
    markSizesGroup.setAttribute("aria-label", "Text and symbol size");
    MARK_SIZE_RATIOS.forEach((ratio, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "viewer-notes-mark-size-btn";
      btn.dataset.markSizeIndex = String(index);
      btn.title = `Size ${index + 1}`;
      const label = document.createElement("span");
      label.className = "viewer-notes-mark-size-label";
      label.textContent = "A";
      label.setAttribute("aria-hidden", "true");
      btn.appendChild(label);
      btn.addEventListener("click", () => {
        activeMarkSizeIndex = index;
        updateMarkSizeButtons();
      });
      markSizesGroup.appendChild(btn);
    });
    notesToolbar.appendChild(markSizesGroup);
    const symbolsPanel = document.createElement("div");
    symbolsPanel.className = "viewer-notes-symbols hidden";
    symbolsPanel.setAttribute("role", "group");
    symbolsPanel.setAttribute("aria-label", "Music symbols");
    TEXT_SYMBOLS.forEach((symbol) => appendTextSymbolButton(symbolsPanel, symbol));
    NOTE_SYMBOL_IDS.forEach((noteId) => appendNoteSymbolButton(symbolsPanel, noteId));
    notesToolbar.appendChild(symbolsPanel);
    applyToolDefaultColor(activeTool);
    updateToolButtons();
    updateColorSwatches();
    updatePenSizeButtons();
    updateMarkSizeButtons();
    updateSymbolButtons();
  }

  function setNotesMode(active) {
    notesModeActive = active;
    notesToggleBtn?.classList.toggle("active", active);
    notesToolbar?.classList.toggle("hidden", !active);
    document.querySelectorAll(".viewer-notes-layer").forEach((layer) => {
      layer.classList.toggle("viewer-notes-layer-editable", active);
    });
    syncEraserLayerMode();
    if (!active) cancelTextInput();
  }

  function refreshAllSlots() {
    document.querySelectorAll(".viewer-pdf-page-slot").forEach((slot) => {
      const pageNum = Number(slot.dataset.pageNum);
      if (pageNum && slot.querySelector(".viewer-pdf-page")) {
        renderSlotNotes(slot, pageNum);
      }
    });
  }

  function updateNotesToggleVisibility(pane) {
    if (!notesToggleBtn) return;
    const show = notesEnabled() && pane?.dataset.media === "pdf";
    notesToggleBtn.classList.toggle("hidden", !show);
    if (!show) setNotesMode(false);
  }

  function onViewerOpen(id, files, selectedFileId) {
    if (scoreId) flushSave();
    scoreId = id;
    fileId = selectedFileId || files?.find((f) => f.media === "pdf")?.id || files?.[0]?.id || "";
    setNotesMode(false);
    loadNotesForScore(id).then(() => {
      refreshAllSlots();
      const pane = document.querySelector(`.viewer-pane[data-pane="${fileId}"]`);
      updateNotesToggleVisibility(pane);
    });
  }

  function onViewerClose() {
    flushSave();
    cancelTextInput();
    setNotesMode(false);
    scoreId = "";
    fileId = "";
    scoreNotes = { files: {} };
    dragState = null;
  }

  function onPaneChange(id, pane) {
    fileId = id;
    updateNotesToggleVisibility(pane);
    refreshAllSlots();
  }

  function onPageSlotReady(slot, pageNum) {
    if (!notesEnabled() || !fileId) return;
    renderSlotNotes(slot, pageNum);
  }

  function bindOverlay() {
    overlay = document.getElementById("score-viewer-overlay");
    if (!overlay || overlay.dataset.notesBound === "true") return;
    overlay.dataset.notesBound = "true";
    userId = overlay.dataset.userId || "";
    storageMode = overlay.dataset.notesStorage || "none";
    notesToolbar = document.getElementById("score-viewer-notes-toolbar");
    notesToggleBtn = document.getElementById("score-viewer-notes-toggle");
    if (!notesEnabled()) {
      notesToggleBtn?.classList.add("hidden");
      notesToolbar?.classList.add("hidden");
      return;
    }
    buildToolbar();
    notesToggleBtn?.classList.add("hidden");
    notesToggleBtn?.addEventListener("click", () => setNotesMode(!notesModeActive));
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !textInputEl) return;
      e.stopPropagation();
      cancelTextInput();
    });
  }

  bindOverlay();
  window.ScoreViewerNotes = {
    onViewerOpen,
    onViewerClose,
    onPaneChange,
    onPageSlotReady,
    setNotesMode,
  };
})();
