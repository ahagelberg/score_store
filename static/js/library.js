(function () {
  "use strict";

  const DRAG_MIME = "application/x-score-file";
  const SCORE_DRAG_MIME = "application/x-score-id";
  const USER_LIBRARY_CTX_PREFIX = "user-";

  function dropTargetFrom(el) {
    return el.closest("[data-drop-kind]");
  }

  function setDropActive(el, on) {
    if (!el) return;
    el.classList.toggle("drop-target-active", on);
  }

  function userIdFromLibraryCtx(libraryCtx) {
    if (!libraryCtx?.startsWith(USER_LIBRARY_CTX_PREFIX)) return null;
    return libraryCtx.slice(USER_LIBRARY_CTX_PREFIX.length);
  }

  async function assignScoreToUser(scoreId, userId, folderId) {
    const res = await fetch("/maestro/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score_id: scoreId, user_id: userId, assign: true }),
    });
    if (!res.ok) {
      const data = await res.json();
      showToast(data.error || "Assign failed", true);
      return false;
    }
    if (folderId && folderId !== "root") {
      const folderRes = await fetch(
        `/library/${USER_LIBRARY_CTX_PREFIX}${userId}/scores/${scoreId}/folder`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_id: folderId }),
        },
      );
      if (!folderRes.ok) {
        showToast("Assigned but folder move failed", true);
        return false;
      }
    }
    return true;
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
    const item = ScoreEditor.buildCreateAccordion(file, libraryCtx, folderId, splitCtx);
    list.insertBefore(item, list.firstChild);
    ScoreEditor.bindAccordion(item);
    if (window.TagInput) window.TagInput.initAll(item);
    ScoreEditor.expandAccordion(item);
  }

  function workspaceFrom(el) {
    return el.closest(".library-workspace, .maestro-col, .library-page, #library-root");
  }

  function scoreListIn(el) {
    return workspaceFrom(el)?.querySelector(".score-list");
  }

  async function handleFileDrop(target, files, dragPayload, transfer) {
    const kind = target.dataset.dropKind;
    const libraryCtx = target.dataset.libraryCtx;
    const folderId = target.dataset.folderId || "root";

    const scoreDragId = transfer?.getData(SCORE_DRAG_MIME);
    const assignUserId = userIdFromLibraryCtx(libraryCtx);
    if (scoreDragId && assignUserId && (kind === "library" || kind === "folder")) {
      const ok = await assignScoreToUser(scoreDragId, assignUserId, kind === "folder" ? folderId : "root");
      if (ok) {
        showToast("Score assigned");
        location.reload();
      }
      return;
    }

    if (scoreDragId && kind === "folder" && libraryCtx) {
      const res = await fetch(`/library/${libraryCtx}/scores/${scoreDragId}/folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: folderId }),
      });
      if (res.ok) {
        showToast("Score moved");
        location.reload();
      } else {
        const data = await res.json();
        showToast(data.error || "Move failed", true);
      }
      return;
    }

    if (dragPayload && kind === "folder" && dragPayload.dragKind === "main") {
      const list = scoreListIn(target);
      if (!list) return;
      insertCreateAccordion(list, null, libraryCtx, folderId, {
        srcScoreId: dragPayload.scoreId,
        fileId: dragPayload.fileId,
      });
      return;
    }

    if (dragPayload && dragPayload.scoreId && kind === "aux") {
      const toScore = target.dataset.scoreId || target.closest("[data-score-id]")?.dataset.scoreId;
      if (!toScore || toScore === dragPayload.scoreId) return;
      const res = await fetch(`/scores/${dragPayload.scoreId}/files/${dragPayload.fileId}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_score_id: toScore }),
      });
      if (!res.ok) {
        const data = await res.json();
        showToast(data.error || "Move failed", true);
        return;
      }
      location.reload();
      return;
    }

    if (files.length === 0) return;

    if (kind === "folder" || kind === "library") {
      const pdf = files.find((f) => UploadHelpers.isPdfFile(f));
      if (!pdf) {
        showToast("Drop PDF on folder to create a score; drop other files onto a score", true);
        return;
      }
      const list = target.classList.contains("score-list") ? target : scoreListIn(target);
      if (!list) return;
      insertCreateAccordion(list, pdf, libraryCtx, folderId, null);
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

  function bindDropTargets(root) {
    root.querySelectorAll(".drop-target").forEach((el) => {
      el.addEventListener("dragover", (e) => {
        if (dropTargetFrom(e.target) !== el) return;
        const hasFiles = e.dataTransfer.types.includes("Files");
        const hasScore = e.dataTransfer.types.includes(SCORE_DRAG_MIME);
        const hasInternal = e.dataTransfer.types.includes(DRAG_MIME);
        if (!hasFiles && !hasScore && !hasInternal) return;
        e.preventDefault();
        e.stopPropagation();
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
        setDropActive(el, false);
        const payload = parseDragData(e);
        const files = getFilesFromEvent(e);
        await handleFileDrop(el, files, payload, e.dataTransfer);
      });
    });
  }

  function bindUploadButtons(root) {
    root.querySelectorAll(".upload-pdf-btn").forEach((btn) => {
      const actions = btn.closest(".folder-actions");
      const input = actions?.querySelector(".upload-pdf-input");
      if (!input) return;
      btn.addEventListener("click", () => input.click());
      input.addEventListener("change", () => {
        const file = input.files[0];
        input.value = "";
        if (!file || !UploadHelpers.isPdfFile(file)) {
          showToast("Please choose a PDF file", true);
          return;
        }
        const libraryCtx = btn.dataset.libraryCtx;
        const folderId = btn.dataset.folderId || "root";
        const list = scoreListIn(btn);
        if (list) insertCreateAccordion(list, file, libraryCtx, folderId, null);
      });
    });
  }

  function bindFolderActions(root) {
    root.querySelectorAll(".new-folder-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = window.prompt("Folder name");
        if (!name) return;
        const ctx = btn.dataset.libraryCtx;
        const fd = new FormData();
        fd.append("name", name);
        const res = await fetch(`/library/${ctx}/folders/new`, {
          method: "POST",
          body: fd,
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (res.ok) location.reload();
        else showToast("Folder create failed", true);
      });
    });
    root.querySelectorAll(".delete-folder-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!window.confirm("Delete this folder? Scores move to root.")) return;
        const res = await fetch(`/library/${btn.dataset.libraryCtx}/folders/${btn.dataset.folderId}/delete`, { method: "POST" });
        if (res.ok) location.reload();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("library-root") || document.getElementById("maestro-root");
    if (!root) return;
    bindDropTargets(root);
    bindUploadButtons(root);
    bindFolderActions(root);

    const assignPanel = document.querySelector(".maestro-assign-panel[data-maestro-assign-user]");
    if (assignPanel) {
      assignPanel.classList.add("drop-target");
      assignPanel.dataset.dropKind = "assign";
      assignPanel.addEventListener("dragover", (e) => {
        if (e.dataTransfer.types.includes(SCORE_DRAG_MIME)) {
          e.preventDefault();
          assignPanel.classList.add("drop-target-active");
        }
      });
      assignPanel.addEventListener("dragleave", () => assignPanel.classList.remove("drop-target-active"));
      assignPanel.addEventListener("drop", async (e) => {
        if (dropTargetFrom(e.target) !== assignPanel) return;
        e.preventDefault();
        assignPanel.classList.remove("drop-target-active");
        const scoreId = e.dataTransfer.getData(SCORE_DRAG_MIME);
        const userId = assignPanel.dataset.maestroAssignUser;
        if (!scoreId || !userId) return;
        const ok = await assignScoreToUser(scoreId, userId, "root");
        if (ok) {
          showToast("Score assigned");
          location.reload();
        }
      });
    }
  });
})();
