(function () {
  "use strict";

  const DRAG_MIME = "application/x-score-file";
  const ACCORDION_MODE_VIEW = "view";
  const ACCORDION_MODE_EDIT = "edit";

  function setAccordionExpanded(item, expanded) {
    item.classList.toggle("score-accordion-expanded", expanded);
    item.classList.toggle("score-accordion-collapsed", !expanded);
    const editor = item.querySelector("[data-score-editor]");
    if (editor) editor.classList.toggle("hidden", !expanded);
  }

  function setAccordionMode(item, mode) {
    item.dataset.accordionMode = mode || "";
    item.classList.toggle("score-accordion-view", mode === ACCORDION_MODE_VIEW);
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
    if (item.dataset.mode === "create" || item.dataset.mode === "split") {
      item.remove();
    } else {
      collapseAccordion(item);
    }
  }

  function collapseAllExcept(except) {
    document.querySelectorAll(".score-accordion-expanded").forEach((el) => {
      if (el !== except) collapseAccordion(el);
    });
  }

  function expandViewAccordion(item) {
    collapseAllExcept(item);
    setAccordionExpanded(item, true);
    setAccordionMode(item, ACCORDION_MODE_VIEW);
    ensureAuxSectionVisible(item);
  }

  function expandEditAccordion(item) {
    collapseAllExcept(item);
    setAccordionExpanded(item, true);
    setAccordionMode(item, ACCORDION_MODE_EDIT);
    ensureAuxSectionVisible(item);
    if (window.TagInput) window.TagInput.initAll(item);
  }

  function expandAccordion(item) {
    expandEditAccordion(item);
  }

  function toggleViewAccordion(item) {
    if (item.dataset.accordionMode === ACCORDION_MODE_VIEW) {
      collapseAccordion(item);
    } else {
      expandViewAccordion(item);
    }
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

  function summaryFilterText(score) {
    return [
      score.title || "",
      score.composer || "",
      score.arranger || "",
      score.description || "",
      (score.tags || []).join(" "),
    ].filter(Boolean).join(" ");
  }

  function updateSummary(item, score) {
    const titleEl = item.querySelector(".score-summary-title");
    if (titleEl) titleEl.textContent = score.title || "New score";
    const mainEl = item.querySelector(".score-summary-main");
    let composerEl = item.querySelector(".score-summary-composer");
    if (mainEl) {
      if (score.composer) {
        if (!composerEl) {
          composerEl = document.createElement("span");
          composerEl.className = "score-summary-composer";
          titleEl.insertAdjacentElement("afterend", composerEl);
        }
        composerEl.textContent = score.composer;
        composerEl.classList.remove("hidden");
      } else if (composerEl) {
        composerEl.remove();
      }
    }
    const tagsEl = item.querySelector(".score-summary-tags");
    if (tagsEl) {
      tagsEl.replaceChildren();
      (score.tags || []).forEach((t) => {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        chip.textContent = t;
        tagsEl.appendChild(chip);
      });
    }
    item.dataset.filterTags = (score.tags || []).join(",");
    item.dataset.filterText = summaryFilterText(score);
  }

  function buildCreateAccordion(stagedFile, libraryCtx, folderId, splitContext) {
    const li = document.createElement("li");
    li.className = "score-accordion score-accordion-expanded";
    li.dataset.mode = splitContext ? "split" : "create";
    li.dataset.libraryCtx = libraryCtx;
    li.dataset.folderId = folderId;
    li.dataset.canEdit = "true";
    if (splitContext) {
      li.dataset.splitSrc = splitContext.srcScoreId;
      li.dataset.splitFileId = splitContext.fileId;
    }
    const title = UploadHelpers.basename(stagedFile ? stagedFile.name : "New score");
    li.innerHTML = `
      <div class="score-summary" data-score-summary>
        <span class="score-summary-title">${title}</span>
      </div>
      <div class="score-editor" data-score-editor>
        <div class="score-panel-main">
          <span class="score-panel-main-icon">📄</span>
          <div class="score-panel-main-info">
            <div class="score-panel-main-name">${stagedFile ? stagedFile.name : ""}</div>
            <div class="score-panel-main-sub">${stagedFile ? stagedFile.name : ""}</div>
          </div>
        </div>
        <div class="score-section" data-section="details">
          <div class="score-section-header" data-section-toggle><span>Details</span><span>−</span></div>
          <div class="score-section-body">
            <div class="form-group"><label>Title *</label><input class="form-control" data-field="title" value="${title}"></div>
            <div class="form-group"><label>Composer</label><input class="form-control" data-field="composer"></div>
            <div class="form-group"><label>Arranger</label><input class="form-control" data-field="arranger"></div>
            <div class="form-group"><label>Description</label><textarea class="form-control" data-field="description"></textarea></div>
            <div class="form-group"><label>Tags</label>
              <div class="tag-field" data-tag-field><input type="hidden" name="tags" value="[]"><div class="tag-chip-list" data-tag-list></div><input class="tag-field-input" data-tag-input placeholder="Add tag…"></div>
            </div>
          </div>
        </div>
        <div class="score-section" data-section="aux">
          <div class="score-section-header" data-section-toggle><span>Additional files</span><span>−</span></div>
          <div class="score-section-body">
            <div class="aux-files">
              <ul class="aux-file-list" data-aux-list></ul>
              <div class="aux-drop-zone drop-target aux-drop-zone-active" data-drop-kind="aux" data-score-id="">
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
    if (stagedFile) li._stagedFile = stagedFile;
    return li;
  }

  async function saveAccordion(item) {
    const meta = collectMetadata(item);
    const mode = item.dataset.mode || "edit";
    const libraryCtx = item.dataset.libraryCtx;
    const folderId = item.dataset.folderId || "root";

    if (mode === "create") {
      const file = item._stagedFile;
      if (!file) {
        showToast("PDF file missing", true);
        return;
      }
      const fd = new FormData();
      fd.append("file", file);
      fd.append("folder_id", folderId);
      Object.entries(meta).forEach(([k, v]) => fd.append(k, v));
      const res = await fetch(`/library/${libraryCtx}/scores/new`, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || "Save failed", true);
        return;
      }
      location.reload();
      return;
    }

    if (mode === "split") {
      const res = await fetch(`/scores/${item.dataset.splitSrc}/files/${item.dataset.splitFileId}/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...meta, library_ctx: libraryCtx, folder_id: folderId }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || "Split failed", true);
        return;
      }
      location.reload();
      return;
    }

    const scoreId = item.dataset.scoreId;
    const res = await fetch(`/scores/${scoreId}/edit`, {
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

  async function removeAux(scoreId, fileId, row) {
    const res = await fetch(`/scores/${scoreId}/files/${fileId}/remove`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Remove failed", true);
      return;
    }
    row.remove();
  }

  function bindAuxFileItem(item, scoreId) {
    const removeBtn = item.querySelector("[data-remove-file]");
    if (removeBtn) {
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeAux(scoreId, removeBtn.dataset.removeFile, item);
      });
    }
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
    const res = await fetch(`/scores/${scoreId}/files`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Upload failed", true);
      return;
    }
    appendAuxFile(listEl, data.file, scoreId);
  }

  function appendAuxFile(listEl, file, scoreId) {
    const item = document.createElement("li");
    item.className = "aux-file-item";
    item.draggable = true;
    item.dataset.fileId = file.id;
    item.dataset.dragKind = "aux";
    item.dataset.scoreId = scoreId;
    const icon = document.createElement("span");
    icon.className = "aux-file-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "📄";
    item.appendChild(icon);
    const type = document.createElement("span");
    type.className = "aux-file-type";
    type.textContent = file.type_label || "File";
    item.appendChild(type);
    const name = document.createElement("span");
    name.className = "aux-file-name";
    name.textContent = file.name;
    item.appendChild(name);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "aux-file-remove";
    btn.dataset.removeFile = file.id;
    btn.textContent = "×";
    item.appendChild(btn);
    listEl.appendChild(item);
    bindAuxFileItem(item, scoreId);
  }

  async function addYoutube(scoreId, listEl) {
    const info = UploadHelpers.promptYoutube();
    if (!info) return;
    const res = await fetch(`/scores/${scoreId}/files`, {
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

  function bindAccordion(item) {
    const titleEl = item.querySelector(".score-summary-title");
    const editBtn = item.querySelector(".score-edit-btn");
    const isExistingScore = item.dataset.mode === "edit" && item.dataset.scoreId;
    if (titleEl && isExistingScore) {
      titleEl.classList.add("score-summary-title-toggle");
      titleEl.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleViewAccordion(item);
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

    const mainNameInput = item.querySelector("[data-main-name-input]");
    if (mainNameInput) {
      mainNameInput.addEventListener("change", async () => {
        const res = await fetch(`/scores/${item.dataset.scoreId}/files/${mainNameInput.dataset.fileId}/name`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: mainNameInput.value }),
        });
        if (!res.ok) showToast("Name update failed", true);
      });
    }

    const ytBtn = item.querySelector(".add-youtube-btn");
    const auxList = item.querySelector("[data-aux-list]");
    if (ytBtn && auxList) {
      ytBtn.addEventListener("click", () => addYoutube(item.dataset.scoreId, auxList));
    }

    const mainPanel = item.querySelector("[data-drag-kind='main']");
    if (mainPanel) {
      mainPanel.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData(DRAG_MIME, JSON.stringify({
          scoreId: item.dataset.scoreId,
          fileId: mainPanel.dataset.fileId,
          dragKind: "main",
        }));
      });
    }

    if (item.dataset.dragScore) {
      item.addEventListener("dragstart", (e) => {
        if (!item.dataset.scoreId) return;
        e.dataTransfer.setData("application/x-score-id", item.dataset.scoreId);
      });
    }

    const deleteBtn = item.querySelector(".score-delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!window.confirm("Delete this score permanently?")) return;
        const res = await fetch(`/scores/${deleteBtn.dataset.scoreId}/delete`, { method: "POST" });
        if (res.ok) item.remove();
        else showToast("Delete failed", true);
      });
    }
  }

  function initExisting() {
    document.querySelectorAll(".score-accordion").forEach(bindAccordion);
    if (window.TagInput) window.TagInput.initAll(document);
  }

  window.ScoreEditor = {
    initExisting,
    expandAccordion,
    expandEditAccordion,
    expandViewAccordion,
    buildCreateAccordion,
    bindAccordion,
    addAuxFile,
    appendAuxFile,
    DRAG_MIME,
  };

  document.addEventListener("DOMContentLoaded", initExisting);
})();
