(function () {
  "use strict";

  const DRAG_MIME = "application/x-score-file";
  const ACCORDION_MODE_EDIT = "edit";
  const GLOBAL_LIBRARY_ID = "_global";
  const USER_LIBRARY_CTX_PREFIX = "user-";
  const ICON_DOWNLOAD = `<svg class="icon-download" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>`;
  const ICON_PRINT = `<svg class="icon-print" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9V3h12v6"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6z"/></svg>`;
  const ICON_PAPERCLIP = `<svg class="icon-paperclip" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`;

  function syncEditorPreview(item) {
    window.ScoreEditorPreview?.reconcile?.(item);
  }

  function setAccordionExpanded(item, expanded) {
    item.classList.toggle("score-accordion-expanded", expanded);
    item.classList.toggle("score-accordion-collapsed", !expanded);
    const editor = item.querySelector("[data-score-editor]");
    if (editor) editor.classList.toggle("hidden", !expanded);
    syncEditorPreview(item);
  }

  function setAccordionMode(item, mode) {
    item.dataset.accordionMode = mode || "";
    item.classList.toggle("score-accordion-edit", mode === ACCORDION_MODE_EDIT);
  }

  function ensureAuxSectionVisible(item) {
    const aux = item.querySelector('.score-section[data-section="aux"]');
    if (aux) aux.classList.remove("collapsed");
  }

  function collapseAccordion(item) {
    setAccordionExpanded(item, false);
    setAccordionMode(item, null);
  }

  function closeAccordion(item) {
    collapseAccordion(item);
  }

  function collapseAllExcept(except) {
    document.querySelectorAll(".score-accordion-expanded").forEach((el) => {
      if (el !== except) collapseAccordion(el);
    });
  }

  function collapseAllExpanded(scope) {
    const root = scope || document;
    root.querySelectorAll(".score-accordion-expanded").forEach((el) => collapseAccordion(el));
  }

  function syncTagsOnExpand(item) {
    const tags = tagsForItem(item);
    syncSummaryTags(item, tags);
    syncItemTagField(item, tags);
  }

  function expandEditAccordion(item) {
    collapseAllExcept(item);
    setAccordionExpanded(item, true);
    setAccordionMode(item, ACCORDION_MODE_EDIT);
    ensureAuxSectionVisible(item);
    syncTagsOnExpand(item);
  }

  function expandEditAccordionKeepOthers(item) {
    setAccordionExpanded(item, true);
    setAccordionMode(item, ACCORDION_MODE_EDIT);
    ensureAuxSectionVisible(item);
    syncTagsOnExpand(item);
  }

  function expandAccordion(item) {
    expandEditAccordion(item);
  }

  function hasAuxFiles(item) {
    const auxList = item.querySelector("[data-aux-list]");
    return auxList && auxList.children.length > 0;
  }

  function syncAuxIndicator(item) {
    const indicator = item.querySelector("[data-score-aux-indicator]");
    if (indicator) indicator.classList.toggle("score-aux-icon-empty", !hasAuxFiles(item));
  }

  function openScoreViewer(item) {
    const viewBtn = item.querySelector(".score-view-btn");
    if (!viewBtn || !window.ScoreViewer) return;
    window.ScoreViewer.openFromButton(viewBtn);
  }

  function auxIndicatorHtml(hasAux) {
    const emptyClass = hasAux ? "" : " score-aux-icon-empty";
    return `<span class="score-aux-icon${emptyClass}" data-score-aux-indicator aria-hidden="true" title="Additional files">${ICON_PAPERCLIP}</span>`;
  }

  function toggleEditAccordion(item) {
    if (item.dataset.accordionMode === ACCORDION_MODE_EDIT) {
      closeAccordion(item);
    } else {
      expandEditAccordion(item);
    }
  }

  function collectMetadata(item) {
    const data = {};
    item.querySelectorAll("[data-field]").forEach((el) => {
      data[el.dataset.field] = el.value;
    });
    const tagsHidden = item.querySelector('input[name="tags"]');
    data.tags = tagsHidden ? tagsHidden.value : "[]";
    return data;
  }

  function scoreSubtitleLine(score) {
    const composer = (score.composer || "").trim();
    const year = (score.year || "").trim();
    if (composer && year) return `${composer} (${year})`;
    if (composer) return composer;
    if (year) return `(${year})`;
    return "";
  }

  function summaryFilterText(score) {
    return [
      score.title || "",
      score.composer || "",
      score.year || "",
      score.arranger || "",
      score.description || "",
      (score.tags || []).join(" "),
    ].filter(Boolean).join(" ");
  }

  function syncSummaryTags(item, tags) {
    const tagsEl = item.querySelector(".score-summary-tags");
    if (tagsEl) {
      tagsEl.replaceChildren();
      tags.forEach((t) => {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        chip.textContent = t;
        tagsEl.appendChild(chip);
      });
    }
    item.dataset.filterTags = tags.join(",");
  }

  function syncItemTagField(item, tags) {
    const field = item.querySelector("[data-tag-field]");
    if (!field || !window.TagInput) return;
    window.TagInput.initField(field);
    window.TagInput.setFieldTags(field, tags);
  }

  function tagsForItem(item) {
    const field = item.querySelector("[data-tag-field]");
    const hiddenEl = field?.querySelector('input[name="tags"]');
    const fromHidden = window.TagInput ? window.TagInput.parseTags(hiddenEl?.value) : [];
    const fromDataset = (item.dataset.filterTags || "").split(",").filter(Boolean);
    if (fromHidden.length || !fromDataset.length) return fromHidden;
    if (hiddenEl) hiddenEl.value = JSON.stringify(fromDataset);
    return fromDataset;
  }

  function updateSummary(item, score) {
    const titleEl = item.querySelector(".score-summary-title");
    if (titleEl) titleEl.textContent = score.title || "New score";
    const mainEl = item.querySelector(".score-summary-main");
    let composerEl = item.querySelector(".score-summary-composer");
    if (mainEl) {
      const subtitle = scoreSubtitleLine(score);
      if (subtitle) {
        if (!composerEl) {
          composerEl = document.createElement("span");
          composerEl.className = "score-summary-composer";
          titleEl.insertAdjacentElement("afterend", composerEl);
        }
        composerEl.textContent = subtitle;
        composerEl.classList.remove("hidden");
      } else if (composerEl) {
        composerEl.remove();
      }
    }
    const tags = score.tags || [];
    syncSummaryTags(item, tags);
    syncItemTagField(item, tags);
    item.dataset.filterText = summaryFilterText(score);
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function mainFileFromScore(score) {
    return (score.files || []).find((f) => f.role === "main") || null;
  }

  function auxFilesFromScore(score) {
    return (score.files || []).filter((f) => f.role !== "main");
  }

  function auxTypeLabel(file) {
    if (file.type_label) return file.type_label;
    if (file.media === "youtube") return "YouTube";
    const stored = file.stored_name || "";
    const extMatch = stored.match(/\.([^.]+)$/);
    const ext = extMatch ? extMatch[1].toLowerCase() : "";
    if (ext === "mscz" || ext === "mscx") return "MuseScore";
    if (ext === "musicxml" || ext === "xml") return "MusicXML";
    if (ext) return ext.toUpperCase();
    const mediaLabels = { pdf: "PDF", image: "Image", audio: "Audio", video: "Video", musescore: "MuseScore" };
    return mediaLabels[file.media] || "File";
  }

  function fileExtension(storedName) {
    if (!storedName) return "";
    const dot = storedName.lastIndexOf(".");
    if (dot <= 0) return "";
    return storedName.slice(dot + 1).toLowerCase();
  }

  function fileDisplayName(stem, ext) {
    return ext ? `${stem}.${ext}` : stem;
  }

  function buildAuxFileNameHtml(fileId, name, storedName, youtubeUrl) {
    const ext = fileExtension(storedName || "");
    const extAttr = ext ? ` data-filename-ext="${escapeHtml(ext)}"` : "";
    const extHtml = ext ? `<span class="filename-field-ext">.${escapeHtml(ext)}</span>` : "";
    const display = youtubeUrl ? escapeHtml(name) : escapeHtml(fileDisplayName(name, ext));
    const displayEl = youtubeUrl
      ? `<a class="aux-file-name aux-file-link filename-field-value" href="${escapeHtml(youtubeUrl)}" target="_blank" rel="noopener noreferrer" data-filename-display data-file-id="${escapeHtml(fileId)}">${display}</a>`
      : `<span class="aux-file-name filename-field-value" data-filename-display data-file-id="${escapeHtml(fileId)}">${display}</span>`;
    return `<div class="aux-file-name-field filename-field" data-filename-field data-file-id="${escapeHtml(fileId)}" data-filename-stem="${escapeHtml(name)}"${extAttr}>
      ${displayEl}
      <button type="button" class="btn-icon btn-icon-sm filename-field-edit" title="Edit filename" aria-label="Edit filename">✎</button>
      <div class="filename-field-edit-row">
        <input class="form-control filename-field-input" type="text" data-filename-input value="${escapeHtml(name)}">
        ${extHtml}
      </div>
    </div>`;
  }

  function buildFilenameFieldHtml(fileId, name, storedName) {
    const ext = fileExtension(storedName || "");
    const extAttr = ext ? ` data-filename-ext="${escapeHtml(ext)}"` : "";
    const extHtml = ext ? `<span class="filename-field-ext">.${escapeHtml(ext)}</span>` : "";
    const display = fileDisplayName(name, ext);
    return `<div class="form-group" data-filename-field data-file-id="${escapeHtml(fileId)}" data-filename-stem="${escapeHtml(name)}"${extAttr}>
      <label>Filename</label>
      <div class="filename-field">
        <span class="filename-field-value" data-filename-display data-file-id="${escapeHtml(fileId)}">${escapeHtml(display)}</span>
        <button type="button" class="btn-icon btn-icon-sm filename-field-edit" title="Edit filename" aria-label="Edit filename">✎</button>
        <div class="filename-field-edit-row">
          <input class="form-control filename-field-input" type="text" data-filename-input value="${escapeHtml(name)}">
          ${extHtml}
        </div>
      </div>
    </div>`;
  }

  function previewPdfUrl(scoreId, mainFile) {
    if (!scoreId || !mainFile?.stored_name) return "";
    return `/files/${encodeURIComponent(scoreId)}/${encodeURIComponent(mainFile.stored_name)}`;
  }

  function libraryIdFromCtx(libraryCtx) {
    if (libraryCtx === "global") return GLOBAL_LIBRARY_ID;
    if (libraryCtx?.startsWith(USER_LIBRARY_CTX_PREFIX)) {
      return libraryCtx.slice(USER_LIBRARY_CTX_PREFIX.length);
    }
    return libraryCtx;
  }

  function buildAuxFileHtml(file) {
    return `<li class="aux-file-item" draggable="true" data-file-id="${escapeHtml(file.id)}" data-drag-kind="aux">
      <span class="aux-file-icon" aria-hidden="true">📄</span>
      <span class="aux-file-type">${escapeHtml(auxTypeLabel(file))}</span>
      ${buildAuxFileNameHtml(file.id, file.name, file.stored_name, file.media === "youtube" ? file.url : null)}
      <button type="button" class="aux-file-remove" data-remove-file="${escapeHtml(file.id)}" title="Remove">×</button>
    </li>`;
  }

  function buildScoreAccordion(score, libraryCtx, folderId, options) {
    const opts = options || {};
    const expanded = opts.expanded !== false;
    const draggable = opts.draggable === true;
    const hardDelete = opts.hardDelete !== false;
    const mainFile = mainFileFromScore(score);
    const auxFiles = auxFilesFromScore(score);
    const tagsJson = JSON.stringify(score.tags || []);
    const filterText = summaryFilterText(score);
    const filterTags = (score.tags || []).join(",");
    const subtitle = scoreSubtitleLine(score);
    const composerHtml = subtitle
      ? `<span class="score-summary-composer">${escapeHtml(subtitle)}</span>`
      : "";
    const canEditYear = opts.canEditYear === true;
    const yearFieldHtml = canEditYear
      ? `<div class="form-group"><label>Year</label><input class="form-control" type="text" data-field="year" value="${escapeHtml(score.year || "")}" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" placeholder="e.g. 2024"></div>`
      : "";
    const noMainBadge = mainFile ? "" : `<span class="score-badge-warn">No main PDF</span>`;
    const tagChips = (score.tags || []).map((t) => `<span class="tag-chip">${escapeHtml(t)}</span>`).join("");
    const summaryActionsHtml = mainFile
      ? `<a class="btn-icon btn-icon-sm score-view-btn" href="/scores/${encodeURIComponent(score.id)}/view?lib=${encodeURIComponent(libraryCtx)}" data-score-id="${escapeHtml(score.id)}" title="View" aria-label="View">👁</a>
         <a class="btn-icon btn-icon-sm viewer-header-btn score-download-btn" href="/scores/${escapeHtml(score.id)}/download" title="Download" aria-label="Download">${ICON_DOWNLOAD}</a>
         <button type="button" class="btn-icon btn-icon-sm score-print-btn" data-print-url="/files/${escapeHtml(score.id)}/${escapeHtml(mainFile.stored_name)}" data-print-media="pdf" title="Print" aria-label="Print">${ICON_PRINT}</button>`
      : "";
    const li = document.createElement("li");
    li.className = `score-accordion drop-target${expanded ? " score-accordion-expanded score-accordion-edit" : " score-accordion-collapsed"}`;
    li.dataset.dropKind = "score";
    li.dataset.scoreId = score.id;
    li.dataset.scoreFolderId = folderId;
    li.dataset.filterText = filterText;
    li.dataset.filterTags = filterTags;
    li.dataset.mode = "edit";
    li.dataset.libraryCtx = libraryCtx;
    li.dataset.libraryId = opts.libraryId || libraryIdFromCtx(libraryCtx);
    li.dataset.folderId = folderId;
    li.dataset.canEdit = "true";
    li.dataset.hardDelete = hardDelete ? "true" : "false";
    if (draggable) {
      li.dataset.dragScore = "true";
    }
    const previewUrl = previewPdfUrl(score.id, mainFile);
    if (previewUrl) li.dataset.previewPdfUrl = previewUrl;
    const summaryDragAttr = draggable ? ' draggable="true"' : "";
    const deleteLabel = hardDelete ? "Delete" : "Remove";
    li.innerHTML = `
      <div class="score-summary score-summary-clickable" data-score-summary${summaryDragAttr}>
        <div class="score-summary-main">
          ${auxIndicatorHtml(auxFiles.length > 0)}
          <div class="score-summary-text">
            <span class="score-summary-title">${escapeHtml(score.title || "New score")}</span>
            ${composerHtml}
          </div>
          ${noMainBadge}
        </div>
        <div class="score-summary-end">
          <div class="score-summary-tags">${tagChips}</div>
          <div class="score-summary-actions">
            ${summaryActionsHtml}
            <button type="button" class="btn-icon btn-icon-sm score-edit-btn" data-action="expand" title="Edit" aria-label="Edit">✎</button>
            <button type="button" class="btn-icon btn-icon-sm btn-icon-danger score-delete-btn" data-score-id="${escapeHtml(score.id)}" title="${deleteLabel}" aria-label="${deleteLabel}">×</button>
          </div>
        </div>
      </div>
      <div class="score-editor${expanded ? "" : " hidden"}" data-score-editor>
            <div class="score-section" data-section="details">
              <div class="score-section-header" data-section-toggle><span>Details</span><span>−</span></div>
              <div class="score-section-body">
                <div class="form-group"><label>Title *</label><input class="form-control" type="text" data-field="title" value="${escapeHtml(score.title || "")}" required></div>
                <div class="form-group"><label>Composer</label><input class="form-control" type="text" data-field="composer" value="${escapeHtml(score.composer || "")}"></div>
                ${yearFieldHtml}
                <div class="form-group"><label>Arranger</label><input class="form-control" type="text" data-field="arranger" value="${escapeHtml(score.arranger || "")}"></div>
                <div class="form-group"><label>Description</label><textarea class="form-control" data-field="description">${escapeHtml(score.description || "")}</textarea></div>
                <div class="form-group"><label>Tags</label>
                  <div class="tag-field" data-tag-field><input type="hidden" name="tags" value="${escapeHtml(tagsJson)}"><div class="tag-chip-list" data-tag-list></div><input class="tag-field-input" data-tag-input placeholder="Add tag…"></div>
                </div>
                ${mainFile ? buildFilenameFieldHtml(mainFile.id, mainFile.name, mainFile.stored_name) : ""}
              </div>
            </div>
            <div class="score-section" data-section="aux">
              <div class="score-section-header" data-section-toggle><span>Additional files</span><span>−</span></div>
              <div class="score-section-body">
                <button type="button" class="btn btn-sm add-youtube-btn">+ YouTube</button>
                <div class="aux-files">
                  <ul class="aux-file-list" data-aux-list>${auxFiles.map(buildAuxFileHtml).join("")}</ul>
                  <div class="aux-drop-zone drop-target aux-drop-zone-active" data-drop-kind="aux" data-score-id="${escapeHtml(score.id)}">
                    <p class="aux-drop-hint">Drop files here to add</p>
                  </div>
                </div>
              </div>
            </div>
            <div class="score-editor-actions">
              <button type="button" class="btn score-cancel-btn">Cancel</button>
              <button type="button" class="btn btn-primary score-save-btn">Save</button>
            </div>
      </div>`;
    return li;
  }

  async function createScoreFromUpload(file, libraryCtx, folderId) {
    const title = UploadHelpers.basename(file.name);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("folder_id", folderId);
    fd.append("title", title);
    fd.append("composer", "");
    fd.append("arranger", "");
    fd.append("description", "");
    fd.append("tags", "[]");
    const res = await Csrf.fetch(`/library/${libraryCtx}/scores/new`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload failed");
    return data.score;
  }

  async function splitToNewScore(srcScoreId, fileId, libraryCtx, folderId, title) {
    const res = await Csrf.fetch(`/scores/${srcScoreId}/files/${fileId}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title || "New score",
        composer: "",
        arranger: "",
        description: "",
        tags: "[]",
        library_ctx: libraryCtx,
        folder_id: folderId,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Split failed");
    return data;
  }

  function canEditYearFromList(list) {
    const workspace = list?.closest(".library-workspace");
    return workspace?.dataset.canEditYear === "true";
  }

  function replaceAccordionFromScore(item, score, libraryCtx, folderId) {
    const expanded = item.classList.contains("score-accordion-expanded");
    const accordionMode = item.dataset.accordionMode || null;
    const draggable = item.dataset.dragScore === "true";
    const hardDelete = item.dataset.hardDelete !== "false";
    const parent = item.parentNode;
    const list = item.closest(".score-list");
    const newItem = buildScoreAccordion(score, libraryCtx, folderId, {
      expanded,
      draggable,
      hardDelete,
      canEditYear: canEditYearFromList(list),
    });
    if (accordionMode) setAccordionMode(newItem, accordionMode);
    parent.replaceChild(newItem, item);
    bindAccordion(newItem);
    if (window.TagInput) window.TagInput.initAll(newItem);
    window.LibraryDrop?.bindDropTargets?.(newItem);
    window.ScoreEditorPreview?.reconcile?.(newItem);
    return newItem;
  }

  function insertScoreAccordion(list, score, libraryCtx, folderId, options) {
    const opts = options || {};
    const draggable = opts.draggable ?? list.querySelector(".score-accordion[data-drag-score]") !== null;
    const expanded = opts.expanded !== undefined ? opts.expanded : true;
    const item = buildScoreAccordion(score, libraryCtx, folderId, {
      expanded,
      draggable,
      hardDelete: opts.hardDelete,
      canEditYear: opts.canEditYear ?? canEditYearFromList(list),
    });
    list.insertBefore(item, list.firstChild);
    bindAccordion(item);
    if (window.TagInput) window.TagInput.initAll(item);
    window.LibraryDrop?.bindDropTargets?.(item);
    if (expanded) {
      if (opts.expandMode === "keep") expandEditAccordionKeepOthers(item);
      else expandEditAccordion(item);
    }
    window.ScoreFilter?.reapplyAll?.();
    return item;
  }

  async function saveAccordion(item) {
    const meta = collectMetadata(item);
    const scoreId = item.dataset.scoreId;
    if (!scoreId) {
      showToast("Score not found", true);
      return;
    }
    const res = await Csrf.fetch(`/scores/${scoreId}/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(meta),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Save failed", true);
      return;
    }
    updateSummary(item, data.score);
    showToast("Saved");
    collapseAccordion(item);
  }

  function syncFilenameField(field, stem, ext) {
    const display = field.querySelector("[data-filename-display]");
    const input = field.querySelector("[data-filename-input]");
    const resolvedExt = ext || field.dataset.filenameExt || "";
    const displayText = fileDisplayName(stem, resolvedExt);
    if (display) display.textContent = displayText;
    if (input) input.value = stem;
    field.dataset.filenameStem = stem;
    if (resolvedExt) field.dataset.filenameExt = resolvedExt;
  }

  function syncFilenameDisplay(accordion, fileId, file) {
    const stem = file.name;
    const ext = fileExtension(file.stored_name || "");
    accordion.querySelectorAll(`[data-filename-field][data-file-id="${fileId}"]`).forEach((field) => {
      syncFilenameField(field, stem, ext);
    });
  }

  async function saveFilenameField(field, scoreId) {
    const input = field.querySelector("[data-filename-input]");
    if (!input) return null;
    const fileId = field.dataset.fileId;
    const stem = input.value.trim();
    if (!stem) return null;
    if (stem === field.dataset.filenameStem) return;
    const res = await Csrf.fetch(`/scores/${scoreId}/files/${fileId}/name`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: stem }),
    });
    if (!res.ok) {
      showToast("Name update failed", true);
      return null;
    }
    const data = await res.json();
    return data.file;
  }

  function bindFilenameField(field, scoreId, accordion) {
    const input = field.querySelector("[data-filename-input]");
    const editBtn = field.querySelector(".filename-field-edit");
    if (!input || !editBtn) return;

    function enterEdit() {
      field.classList.add("filename-field-editing");
      input.value = field.dataset.filenameStem || input.value;
      input.focus();
      input.select();
    }

    function exitEdit() {
      field.classList.remove("filename-field-editing");
    }

    function revertInput() {
      input.value = field.dataset.filenameStem || input.value;
    }

    editBtn.addEventListener("mousedown", (e) => e.stopPropagation());
    editBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      enterEdit();
    });

    input.addEventListener("mousedown", (e) => e.stopPropagation());
    input.addEventListener("keydown", async (e) => {
      e.stopPropagation();
      if (e.key === "Escape") {
        revertInput();
        exitEdit();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const savedFile = await saveFilenameField(field, scoreId);
        if (savedFile) syncFilenameDisplay(accordion, field.dataset.fileId, savedFile);
        else if (savedFile === null) revertInput();
        exitEdit();
      }
    });

    input.addEventListener("blur", async () => {
      if (!field.classList.contains("filename-field-editing")) return;
      const savedFile = await saveFilenameField(field, scoreId);
      if (savedFile) syncFilenameDisplay(accordion, field.dataset.fileId, savedFile);
      else if (savedFile === null) revertInput();
      exitEdit();
    });
  }

  function bindFilenameFields(accordion) {
    const scoreId = accordion.dataset.scoreId;
    if (!scoreId) return;
    accordion.querySelectorAll("[data-filename-field]").forEach((field) => {
      if (field.dataset.filenameBound) return;
      field.dataset.filenameBound = "true";
      bindFilenameField(field, scoreId, accordion);
    });
  }

  function moveAuxFileInDom(srcScoreId, fileId, dstScoreId) {
    const srcItem = document.querySelector(
      `.score-accordion[data-score-id="${CSS.escape(srcScoreId)}"] .aux-file-item[data-file-id="${CSS.escape(fileId)}"]`,
    );
    const dstList = document.querySelector(
      `.score-accordion[data-score-id="${CSS.escape(dstScoreId)}"] [data-aux-list]`,
    );
    if (!srcItem || !dstList) return false;
    srcItem.remove();
    dstList.appendChild(srcItem);
    bindAuxFileItem(srcItem, dstScoreId);
    const srcAccordion = document.querySelector(`.score-accordion[data-score-id="${CSS.escape(srcScoreId)}"]`);
    const dstAccordion = dstList.closest(".score-accordion");
    if (srcAccordion) syncAuxIndicator(srcAccordion);
    if (dstAccordion) {
      syncAuxIndicator(dstAccordion);
      bindFilenameFields(dstAccordion);
    }
    return true;
  }

  async function removeAux(scoreId, fileId, row) {
    const res = await Csrf.fetch(`/scores/${scoreId}/files/${fileId}/remove`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Remove failed", true);
      return;
    }
    row.remove();
    const accordion = row.closest(".score-accordion");
    if (accordion) syncAuxIndicator(accordion);
  }

  function bindAuxFileItem(item, scoreId) {
    const removeBtn = item.querySelector("[data-remove-file]");
    if (removeBtn) {
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeAux(scoreId, removeBtn.dataset.removeFile, item);
      });
    }
    item.querySelectorAll(".aux-file-link").forEach((link) => {
      link.addEventListener("mousedown", (e) => e.stopPropagation());
    });
    if (item.draggable) {
      item.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData(DRAG_MIME, JSON.stringify({
          scoreId,
          fileId: item.dataset.fileId,
          dragKind: item.dataset.dragKind || "aux",
        }));
        item.classList.add("file-dragging");
      });
      item.addEventListener("dragend", () => item.classList.remove("file-dragging"));
    }
  }

  async function addAuxFile(scoreId, file, listEl) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await Csrf.fetch(`/scores/${scoreId}/files`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Upload failed", true);
      return;
    }
    appendAuxFile(listEl, data.file, scoreId);
  }

  function appendAuxFile(listEl, file, scoreId) {
    const wrapper = document.createElement("ul");
    wrapper.innerHTML = buildAuxFileHtml(file);
    const item = wrapper.firstElementChild;
    listEl.appendChild(item);
    bindAuxFileItem(item, scoreId);
    const accordion = listEl.closest(".score-accordion");
    if (accordion) {
      bindFilenameFields(accordion);
      syncAuxIndicator(accordion);
    }
  }

  async function addYoutube(scoreId, listEl) {
    const info = UploadHelpers.promptYoutube();
    if (!info) return;
    const res = await Csrf.fetch(`/scores/${scoreId}/files`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(info),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "YouTube add failed", true);
      return;
    }
    appendAuxFile(listEl, data.file, scoreId);
  }

  function summaryOpensViewer(item) {
    const workspace = item.closest(".library-workspace");
    return workspace?.dataset.summaryOpensViewer === "true";
  }

  function openSummaryAction(item) {
    if (item.dataset.canEdit === "true" && !summaryOpensViewer(item)) {
      toggleEditAccordion(item);
    } else {
      openScoreViewer(item);
    }
  }

  const SCORE_DRAG_BLOCK_SELECTOR = ".score-summary-actions, button, a";

  function bindScoreDrag(item) {
    if (!item.dataset.dragScore) return;
    const summaryEl = item.querySelector("[data-score-summary]");
    if (!summaryEl) return;
    summaryEl.draggable = true;
    summaryEl.addEventListener("dragstart", (e) => {
      if (e.target.closest(SCORE_DRAG_BLOCK_SELECTOR)) {
        e.preventDefault();
        return;
      }
      if (!item.dataset.scoreId) return;
      e.dataTransfer.setData("application/x-score-id", item.dataset.scoreId);
      item.classList.add("score-dragging");
    });
    summaryEl.addEventListener("dragend", () => item.classList.remove("score-dragging"));
  }

  function bindAccordion(item) {
    const summaryEl = item.querySelector("[data-score-summary]");
    const editBtn = item.querySelector(".score-edit-btn");
    const isExistingScore = item.dataset.mode === "edit" && item.dataset.scoreId;
    if (summaryEl && isExistingScore) {
      summaryEl.classList.add("score-summary-clickable");
      syncAuxIndicator(item);
      summaryEl.addEventListener("click", (e) => {
        if (e.target.closest(".score-summary-actions, button, a")) return;
        openSummaryAction(item);
      });
    }
    if (editBtn) {
      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleEditAccordion(item);
      });
    }
    const downloadBtn = item.querySelector(".score-download-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", (e) => e.stopPropagation());
    }
    window.ScorePrint?.bindPrintButtons?.(item);
    item.querySelectorAll("[data-section-toggle]").forEach((hdr) => {
      hdr.addEventListener("click", () => {
        hdr.closest(".score-section").classList.toggle("collapsed");
      });
    });
    const cancelBtn = item.querySelector(".score-cancel-btn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => closeAccordion(item));
    }
    const saveBtn = item.querySelector(".score-save-btn");
    if (saveBtn) saveBtn.addEventListener("click", () => saveAccordion(item));

    item.querySelectorAll(".aux-file-item[draggable]").forEach((auxItem) => {
      bindAuxFileItem(auxItem, item.dataset.scoreId);
    });

    bindFilenameFields(item);

    const ytBtn = item.querySelector(".add-youtube-btn");
    const auxList = item.querySelector("[data-aux-list]");
    if (ytBtn && auxList) {
      ytBtn.addEventListener("click", () => addYoutube(item.dataset.scoreId, auxList));
    }

    if (item.dataset.dragScore) {
      bindScoreDrag(item);
    }

    const deleteBtn = item.querySelector(".score-delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const hardDelete = item.dataset.hardDelete !== "false";
        const msg = hardDelete
          ? "Delete this score permanently? This removes it for everyone."
          : "Remove this score from this library? It will remain available elsewhere.";
        if (!window.confirm(msg)) return;
        const libraryId = item.dataset.libraryId || "";
        const res = await Csrf.fetch(`/scores/${deleteBtn.dataset.scoreId}/delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ library_id: libraryId }),
        });
        if (res.ok) {
          item.remove();
          window.ScoreEditorPreview?.reconcile?.(item);
        } else showToast(hardDelete ? "Delete failed" : "Remove failed", true);
      });
    }
  }

  function bindEscapeToCloseEdit() {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const overlay = document.getElementById("score-viewer-overlay");
      if (overlay && !overlay.classList.contains("hidden")) return;
      if (e.target.closest(".filename-field-editing")) return;
      const item = document.querySelector(".score-accordion-expanded.score-accordion-edit");
      if (!item) return;
      closeAccordion(item);
    });
  }

  function initExisting() {
    bindEscapeToCloseEdit();
    document.querySelectorAll(".score-accordion").forEach((item) => {
      bindAccordion(item);
      if (item.classList.contains("score-accordion-expanded")) {
        window.ScoreEditorPreview?.reconcile?.(item);
      }
    });
    if (window.TagInput) window.TagInput.initAll(document);
  }

  window.ScoreEditor = {
    initExisting,
    expandAccordion,
    expandEditAccordion,
    expandEditAccordionKeepOthers,
    buildScoreAccordion,
    bindAccordion,
    addAuxFile,
    appendAuxFile,
    createScoreFromUpload,
    splitToNewScore,
    insertScoreAccordion,
    replaceAccordionFromScore,
    collapseAllExpanded,
    moveAuxFileInDom,
    DRAG_MIME,
  };

  document.addEventListener("DOMContentLoaded", initExisting);
})();
