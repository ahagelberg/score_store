(function () {
  "use strict";

  const DRAG_MIME = "application/x-score-file";
  const SCORE_DRAG_MIME = "application/x-score-id";
  const USER_LIBRARY_CTX_PREFIX = "user-";
  const POINTER_DRAG_THRESHOLD_PX = 10;
  const TOUCH_DRAG_GHOST_CLASS = "score-touch-drag-ghost";
  const TOUCH_DRAG_SUPPRESS_CLICK_MS = 400;
  const COARSE_POINTER_MEDIA = "(pointer: coarse)";

  let touchDragGhost = null;
  let activeTouchDrag = null;
  let touchDragDocumentBound = false;

  function isCoarsePointerDevice() {
    return window.matchMedia(COARSE_POINTER_MEDIA).matches;
  }

  function suppressScoreSummaryClick(item) {
    item.dataset.touchDragSuppressClick = "true";
    window.setTimeout(() => {
      delete item.dataset.touchDragSuppressClick;
    }, TOUCH_DRAG_SUPPRESS_CLICK_MS);
  }

  function scoreSummaryClickSuppressed(item) {
    return item?.dataset?.touchDragSuppressClick === "true";
  }

  function dropTargetFrom(el) {
    return el.closest("[data-drop-kind]");
  }

  function setDropActive(el, on) {
    if (!el) return;
    el.classList.toggle("drop-target-active", on);
  }

  function dropScope(el) {
    return el.closest("#maestro-root, #library-root, #admin-root") || document;
  }

  function pageRoot() {
    return document.getElementById("library-root")
      || document.getElementById("maestro-root")
      || document.getElementById("admin-root");
  }

  function clearDropActive(scope) {
    scope.querySelectorAll(".drop-target-active").forEach((node) => {
      node.classList.remove("drop-target-active");
    });
  }

  function bindDropActiveClear() {
    if (document.body.dataset.dropActiveClearBound) return;
    document.body.dataset.dropActiveClearBound = "true";
    document.addEventListener("dragend", () => clearDropActive(document));
  }

  function userIdFromLibraryCtx(libraryCtx) {
    if (!libraryCtx?.startsWith(USER_LIBRARY_CTX_PREFIX)) return null;
    return libraryCtx.slice(USER_LIBRARY_CTX_PREFIX.length);
  }

  async function assignScoreToUser(scoreId, userId, folderId) {
    const res = await Csrf.fetch("/maestro/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score_id: scoreId, user_id: userId, assign: true }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Assign failed", true);
      return null;
    }
    let effectiveFolder = "root";
    if (folderId && folderId !== "root") {
      const folderRes = await Csrf.fetch(
        `/library/${USER_LIBRARY_CTX_PREFIX}${userId}/scores/${scoreId}/folder`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_id: folderId }),
        },
      );
      if (!folderRes.ok) {
        const folderData = await folderRes.json();
        showToast(folderData.error || "Assigned but folder move failed", true);
        return null;
      }
      effectiveFolder = folderId;
    }
    return { score: data.score, folderId: effectiveFolder };
  }

  function userLibraryWorkspace(userId) {
    return document.querySelector(`.library-workspace[data-library-ctx="${USER_LIBRARY_CTX_PREFIX}${userId}"]`);
  }

  function scoreAccordionInWorkspace(workspace, scoreId) {
    if (!workspace || !scoreId) return null;
    return workspace.querySelector(`.score-accordion[data-score-id="${CSS.escape(scoreId)}"]`);
  }

  function applyScoreFolderToAccordion(accordion, folderId) {
    if (window.LibraryLayout?.applyScoreFolderToAccordion) {
      window.LibraryLayout.applyScoreFolderToAccordion(accordion, folderId);
      return;
    }
    accordion.dataset.scoreFolderId = folderId;
    accordion.dataset.folderId = folderId;
  }

  function refreshScoreListForWorkspace(workspace) {
    if (workspace && window.LibraryLayout?.refreshWorkspace) {
      window.LibraryLayout.refreshWorkspace(workspace);
    }
  }

  function updateScoreFolderInDom(scoreId, folderId, target) {
    const workspace = workspaceFrom(target);
    const accordion = scoreAccordionInWorkspace(workspace, scoreId)
      || document.querySelector(`.score-accordion[data-score-id="${CSS.escape(scoreId)}"]`);
    if (!accordion) return;
    applyScoreFolderToAccordion(accordion, folderId);
    const ws = workspace || accordion.closest(".library-workspace");
    if (accordion.classList.contains("score-accordion-expanded") && ws) {
      window.ScoreEditor?.collapseAllExpanded?.(ws);
    }
    refreshScoreListForWorkspace(ws);
  }

  function insertAssignedScore(userId, folderId, score, target) {
    if (!score?.id) return;
    const libraryCtx = `${USER_LIBRARY_CTX_PREFIX}${userId}`;
    const workspace = userLibraryWorkspace(userId) || workspaceFrom(target);
    const list = workspace?.querySelector(".score-list");
    if (!list) return;
    const existing = scoreAccordionInWorkspace(workspace, score.id);
    if (existing) {
      applyScoreFolderToAccordion(existing, folderId);
    } else {
      ScoreEditor.insertScoreAccordion(list, score, libraryCtx, folderId, {
        expanded: false,
        draggable: true,
        hardDelete: false,
        expandMode: "keep",
      });
    }
    refreshScoreListForWorkspace(workspace);
  }

  function parseDragData(e) {
    const raw = e.dataTransfer.getData(DRAG_MIME);
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch {
        return null;
      }
    }
    return null;
  }

  function getFilesFromEvent(e) {
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      return Array.from(e.dataTransfer.files);
    }
    return [];
  }

  function insertCreateAccordion(list, file, libraryCtx, folderId, splitCtx) {
    return uploadAndInsertScores(list, [file], libraryCtx, folderId, splitCtx);
  }

  async function uploadAndInsertScores(list, files, libraryCtx, folderId, splitCtx) {
    if (splitCtx) {
      const srcAccordion = document.querySelector(`.score-accordion[data-score-id="${splitCtx.srcScoreId}"]`);
      const nameField = srcAccordion?.querySelector(
        `[data-filename-field][data-file-id="${splitCtx.fileId}"]`,
      );
      const mainName = nameField?.dataset.filenameStem || "New score";
      try {
        const data = await ScoreEditor.splitToNewScore(
          splitCtx.srcScoreId,
          splitCtx.fileId,
          libraryCtx,
          folderId,
          mainName.trim() || "New score",
        );
        ScoreEditor.insertScoreAccordion(list, data.score, libraryCtx, folderId, { expandMode: "keep" });
        if (data.source_score && srcAccordion) {
          ScoreEditor.replaceAccordionFromScore(
            srcAccordion,
            data.source_score,
            srcAccordion.dataset.libraryCtx || libraryCtx,
            srcAccordion.dataset.folderId || folderId,
          );
        }
      } catch (err) {
        showToast(err.message || "Split failed", true);
      }
      return;
    }
    const pdfs = files.filter((f) => UploadHelpers.isPdfFile(f));
    if (pdfs.length === 0) {
      showToast("Please choose a PDF file", true);
      return;
    }
    const multi = pdfs.length > 1;
    for (const file of pdfs) {
      try {
        const score = await ScoreEditor.createScoreFromUpload(file, libraryCtx, folderId);
        ScoreEditor.insertScoreAccordion(list, score, libraryCtx, folderId, { expandMode: multi ? "keep" : "collapse" });
      } catch (err) {
        showToast(err.message || "Upload failed", true);
      }
    }
  }

  function workspaceFrom(el) {
    return el.closest(".library-workspace, .maestro-col, .library-page, #library-root");
  }

  function scoreListIn(el) {
    return workspaceFrom(el)?.querySelector(".score-list");
  }

  async function assignDroppedScoreToUser(scoreId, userId, folderId, target) {
    const result = await assignScoreToUser(scoreId, userId, folderId || "root");
    if (!result) return;
    insertAssignedScore(userId, result.folderId, result.score, target);
    showToast("Score assigned");
  }

  async function handleFileDrop(target, files, dragPayload, transfer) {
    const kind = target.dataset.dropKind;
    const libraryCtx = target.dataset.libraryCtx;
    const folderId = target.dataset.folderId || "root";

    const scoreDragId = transfer?.getData(SCORE_DRAG_MIME);
    if (scoreDragId && kind === "user") {
      const userId = target.dataset.userId;
      if (!userId) return;
      await assignDroppedScoreToUser(scoreDragId, userId, "root", target);
      return;
    }
    const assignUserId = userIdFromLibraryCtx(libraryCtx);
    if (scoreDragId && assignUserId && (kind === "library" || kind === "folder")) {
      await assignDroppedScoreToUser(
        scoreDragId,
        assignUserId,
        kind === "folder" ? folderId : "root",
        target,
      );
      return;
    }

    if (scoreDragId && kind === "folder" && libraryCtx) {
      const res = await Csrf.fetch(
        `/library/${libraryCtx}/scores/${scoreDragId}/folder`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_id: folderId }),
        },
      );
      if (res.ok) {
        updateScoreFolderInDom(scoreDragId, folderId, target);
        showToast("Score moved");
      } else {
        const data = await res.json();
        showToast(data.error || "Move failed", true);
      }
      return;
    }

    if (dragPayload && kind === "folder" && dragPayload.dragKind === "main") {
      const list = scoreListIn(target);
      if (!list) return;
      await uploadAndInsertScores(list, [], libraryCtx, folderId, {
        srcScoreId: dragPayload.scoreId,
        fileId: dragPayload.fileId,
      });
      return;
    }

    if (dragPayload && dragPayload.scoreId && kind === "aux") {
      const toScore = target.dataset.scoreId || target.closest("[data-score-id]")?.dataset.scoreId;
      if (!toScore || toScore === dragPayload.scoreId) return;
      const res = await Csrf.fetch(
        window.ScoreEditor.scoreApiPath(dragPayload.scoreId, "files", dragPayload.fileId, "move"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ to_score_id: toScore }),
        },
      );
      if (!res.ok) {
        const data = await res.json();
        showToast(data.error || "Move failed", true);
        return;
      }
      if (ScoreEditor.moveAuxFileInDom(dragPayload.scoreId, dragPayload.fileId, toScore)) {
        showToast("File moved");
      } else {
        showToast("File moved; refresh to see changes");
      }
      return;
    }

    if (files.length === 0) return;

    if (kind === "folder" || kind === "library") {
      const pdfs = files.filter((f) => UploadHelpers.isPdfFile(f));
      if (pdfs.length === 0) {
        showToast("Drop PDF on folder to create a score; drop other files onto a score", true);
        return;
      }
      const list = target.classList.contains("score-list") ? target : scoreListIn(target);
      if (!list) return;
      await uploadAndInsertScores(list, pdfs, libraryCtx, folderId, null);
      return;
    }

    if (kind === "score" || kind === "aux") {
      const scoreId = target.dataset.scoreId || target.closest("[data-score-id]")?.dataset.scoreId;
      if (!scoreId) return;
      const accordion = target.closest(".score-accordion") || document.querySelector(`.score-accordion[data-score-id="${scoreId}"]`);
      if (accordion) ScoreEditor.expandAccordion(accordion);
      const listEl = accordion?.querySelector("[data-aux-list]");
      if (!listEl) return;
      for (const file of files) {
        if (UploadHelpers.isPdfFile(file) && kind === "folder") continue;
        await ScoreEditor.addAuxFile(scoreId, file, listEl);
      }
      return;
    }
  }

  function bindDropTarget(el) {
    if (el.dataset.dropBound === "true") return;
    el.dataset.dropBound = "true";
    bindDropActiveClear();
    const scope = dropScope(el);
    el.addEventListener("dragover", (e) => {
        if (dropTargetFrom(e.target) !== el) return;
        const hasFiles = e.dataTransfer.types.includes("Files");
        const hasScore = e.dataTransfer.types.includes(SCORE_DRAG_MIME);
        const hasInternal = e.dataTransfer.types.includes(DRAG_MIME);
        if (!hasFiles && !hasScore && !hasInternal) return;
        e.preventDefault();
        e.stopPropagation();
        clearDropActive(scope);
        setDropActive(el, true);
      });
      el.addEventListener("dragleave", (e) => {
        if (dropTargetFrom(e.target) !== el) return;
        if (el.contains(e.relatedTarget)) return;
        setDropActive(el, false);
      });
      el.addEventListener("drop", async (e) => {
        if (dropTargetFrom(e.target) !== el) return;
        e.preventDefault();
        e.stopPropagation();
        clearDropActive(scope);
        const payload = parseDragData(e);
        const files = getFilesFromEvent(e);
        await handleFileDrop(el, files, payload, e.dataTransfer);
      });
  }

  function ensureTouchDragGhost() {
    if (touchDragGhost) return touchDragGhost;
    touchDragGhost = document.createElement("div");
    touchDragGhost.className = `${TOUCH_DRAG_GHOST_CLASS} hidden`;
    touchDragGhost.setAttribute("aria-hidden", "true");
    document.body.appendChild(touchDragGhost);
    return touchDragGhost;
  }

  function touchDragTitle(item) {
    return item.querySelector(".score-summary-title")?.textContent?.trim() || "Score";
  }

  function showTouchDragGhost(item, x, y) {
    const ghost = ensureTouchDragGhost();
    ghost.textContent = touchDragTitle(item);
    ghost.classList.remove("hidden");
    ghost.style.left = `${x}px`;
    ghost.style.top = `${y}px`;
  }

  function moveTouchDragGhost(x, y) {
    if (!touchDragGhost) return;
    touchDragGhost.style.left = `${x}px`;
    touchDragGhost.style.top = `${y}px`;
  }

  function hideTouchDragGhost() {
    if (!touchDragGhost) return;
    touchDragGhost.classList.add("hidden");
  }

  function dropTargetAt(x, y) {
    const ghostWasVisible = touchDragGhost && !touchDragGhost.classList.contains("hidden");
    const dragItem = activeTouchDrag?.item;
    if (ghostWasVisible) hideTouchDragGhost();
    const hit = document.elementFromPoint(x, y);
    if (ghostWasVisible && dragItem) showTouchDragGhost(dragItem, x, y);
    return hit ? dropTargetFrom(hit) : null;
  }

  function syntheticScoreTransfer(scoreId) {
    return {
      types: [SCORE_DRAG_MIME],
      getData(type) {
        return type === SCORE_DRAG_MIME ? scoreId : "";
      },
    };
  }

  function clearTouchDragDocumentListeners() {
    if (!touchDragDocumentBound) return;
    document.removeEventListener("pointermove", onTouchDragPointerMove);
    document.removeEventListener("pointerup", onTouchDragPointerUp);
    document.removeEventListener("pointercancel", onTouchDragPointerUp);
    touchDragDocumentBound = false;
  }

  function bindTouchDragDocumentListeners() {
    if (touchDragDocumentBound) return;
    document.addEventListener("pointermove", onTouchDragPointerMove, { passive: false });
    document.addEventListener("pointerup", onTouchDragPointerUp);
    document.addEventListener("pointercancel", onTouchDragPointerUp);
    touchDragDocumentBound = true;
  }

  function onTouchDragPointerMove(e) {
    const drag = activeTouchDrag;
    if (!drag || e.pointerId !== drag.pointerId) return;
    if (!drag.dragging) {
      const dx = e.clientX - drag.startX;
      const dy = e.clientY - drag.startY;
      if (Math.hypot(dx, dy) < POINTER_DRAG_THRESHOLD_PX) return;
      drag.dragging = true;
      drag.item.classList.add("score-dragging");
      showTouchDragGhost(drag.item, e.clientX, e.clientY);
    }
    moveTouchDragGhost(e.clientX, e.clientY);
    clearDropActive(dropScope(drag.item));
    const target = dropTargetAt(e.clientX, e.clientY);
    if (target) setDropActive(target, true);
    e.preventDefault();
  }

  function onTouchDragPointerUp(e) {
    const drag = activeTouchDrag;
    if (!drag || e.pointerId !== drag.pointerId) return;
    clearTouchDragDocumentListeners();
    finishTouchDrag(e.clientX, e.clientY);
  }

  function finishTouchDrag(clientX, clientY) {
    const drag = activeTouchDrag;
    if (!drag) return;
    activeTouchDrag = null;
    hideTouchDragGhost();
    drag.item.classList.remove("score-dragging");
    clearDropActive(document);
    const summary = drag.item.querySelector("[data-score-summary]");
    if (summary && !isCoarsePointerDevice()) summary.setAttribute("draggable", "true");
    if (!drag.dragging) return;
    suppressScoreSummaryClick(drag.item);
    const target = dropTargetAt(clientX, clientY);
    if (!target) return;
    handleFileDrop(target, [], null, syntheticScoreTransfer(drag.scoreId));
  }

  function bindTouchScoreDrag(item) {
    if (item.dataset.touchDragBound === "true") return;
    if (item.dataset.dragScore !== "true" || !item.dataset.scoreId) return;
    const summary = item.querySelector("[data-score-summary]");
    if (!summary) return;
    item.dataset.touchDragBound = "true";
    if (isCoarsePointerDevice()) summary.removeAttribute("draggable");

    summary.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse") return;
      if (e.button !== 0) return;
      if (e.target.closest(".score-summary-actions, button, a")) return;
      if (activeTouchDrag) return;
      summary.removeAttribute("draggable");
      activeTouchDrag = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        dragging: false,
        scoreId: item.dataset.scoreId,
        item,
      };
      bindTouchDragDocumentListeners();
    }, { passive: true });
  }

  function bindTouchScoreDrags(root) {
    (root || document).querySelectorAll('.score-accordion[data-drag-score="true"]').forEach(bindTouchScoreDrag);
  }

  function bindDropTargets(root) {
    root.querySelectorAll(".drop-target").forEach(bindDropTarget);
  }

  function bindUploadButtons(root) {
    root.querySelectorAll(".upload-pdf-btn").forEach((btn) => {
      const actions = btn.closest(".folder-actions");
      const input = actions?.querySelector(".upload-pdf-input");
      if (!input) return;
      btn.addEventListener("click", () => input.click());
      input.addEventListener("change", async () => {
        const selected = Array.from(input.files || []);
        input.value = "";
        const libraryCtx = btn.dataset.libraryCtx;
        const folderId = btn.dataset.folderId || "root";
        const list = scoreListIn(btn);
        if (!list || selected.length === 0) return;
        await uploadAndInsertScores(list, selected, libraryCtx, folderId, null);
      });
    });
  }

  async function createFolder(btn) {
    const name = window.prompt("Folder name");
    if (!name) return;
    const ctx = btn.dataset.libraryCtx;
    const workspace = btn.closest(".library-workspace");
    const parentId = workspace && window.LibraryLayout?.folderIdForWorkspace
      ? window.LibraryLayout.folderIdForWorkspace(workspace)
      : "root";
    const fd = new FormData();
    fd.append("name", name);
    fd.append("parent_id", parentId);
    const res = await Csrf.fetch(`/library/${ctx}/folders/new`, {
      method: "POST",
      body: fd,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!res.ok) {
      showToast("Folder create failed", true);
      return;
    }
    const folder = await res.json();
    if (workspace && window.LibraryLayout?.insertFolder) {
      window.LibraryLayout.insertFolder(workspace, folder);
    }
    showToast("Folder created");
  }

  async function deleteFolder(btn) {
    if (!window.confirm("Delete this folder? Subfolders and scores move to the parent folder.")) return;
    const workspace = btn.closest(".library-workspace");
    const res = await Csrf.fetch(
      `/library/${btn.dataset.libraryCtx}/folders/${btn.dataset.folderId}/delete`,
      { method: "POST" },
    );
    if (!res.ok) {
      showToast("Folder delete failed", true);
      return;
    }
    if (workspace && window.LibraryLayout?.removeFolder) {
      window.LibraryLayout.removeFolder(workspace, btn.dataset.folderId);
    }
    showToast("Folder deleted");
  }

  function bindFolderActions(root) {
    if (root.dataset.folderActionsBound) return;
    root.dataset.folderActionsBound = "true";
    root.addEventListener("click", (e) => {
      const newBtn = e.target.closest(".new-folder-btn");
      if (newBtn && root.contains(newBtn)) {
        e.preventDefault();
        createFolder(newBtn);
        return;
      }
      const deleteBtn = e.target.closest(".delete-folder-btn");
      if (deleteBtn && root.contains(deleteBtn)) {
        e.preventDefault();
        deleteFolder(deleteBtn);
      }
    });
  }

  window.LibraryDrop = {
    bindDropTargets,
    bindDropTarget,
    bindTouchScoreDrag,
    bindTouchScoreDrags,
    scoreSummaryClickSuppressed,
    isCoarsePointerDevice,
  };

  function initRoot(root) {
    if (!root) return;
    bindDropTargets(root);
    bindTouchScoreDrags(root);
    bindUploadButtons(root);
  }

  window.LibraryPage = { initRoot };

  function bootstrapLibraryRoot(root) {
    if (!root) return;
    window.LibraryLayout?.initWorkspaces?.(root);
    window.ScoreFilter?.initAll?.(root);
    window.ScoreEditor?.initExisting?.(root);
    initRoot(root);
    window.ScorePrint?.bindPrintButtons?.(root);
    window.TagInput?.initAll?.(root);
    root.querySelectorAll(".library-workspace").forEach((workspace) => {
      window.LibraryLayout?.refreshWorkspace?.(workspace);
    });
    window.ScoreFilter?.reapplyAll?.();
    window.ScoreEditorPreview?.reconcile?.();
  }

  function bootstrapPage() {
    const root = pageRoot();
    if (!root) return;
    window.LibraryLayout?.stripLayoutParams?.();
    if (root.dataset.isChoir === "true") {
      window.LibraryLayout?.initChoirReset?.(root);
    }
    bindFolderActions(root);
    bootstrapLibraryRoot(root);
  }

  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  onReady(bootstrapPage);
  window.LibraryBootstrap = { bootstrapLibraryRoot, bootstrapPage, pageRoot };
})();
