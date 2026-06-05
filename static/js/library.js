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

  function insertAssignedScore(userId, folderId, score, target) {
    if (!score?.id) return;
    const libraryCtx = `${USER_LIBRARY_CTX_PREFIX}${userId}`;
    const workspace = userLibraryWorkspace(userId) || workspaceFrom(target);
    const list = workspace?.querySelector(".score-list");
    if (!list) return;
    const existing = list.querySelector(`.score-accordion[data-score-id="${CSS.escape(score.id)}"]`);
    if (existing) {
      existing.dataset.scoreFolderId = folderId;
      existing.dataset.folderId = folderId;
    } else {
      ScoreEditor.insertScoreAccordion(list, score, libraryCtx, folderId, {
        expanded: false,
        draggable: true,
        hardDelete: false,
        expandMode: "keep",
      });
    }
    if (workspace && window.LibraryLayout?.refreshWorkspace) {
      window.LibraryLayout.refreshWorkspace(workspace);
    }
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

  async function handleFileDrop(target, files, dragPayload, transfer) {
    const kind = target.dataset.dropKind;
    const libraryCtx = target.dataset.libraryCtx;
    const folderId = target.dataset.folderId || "root";

    const scoreDragId = transfer?.getData(SCORE_DRAG_MIME);
    const assignUserId = userIdFromLibraryCtx(libraryCtx);
    if (scoreDragId && assignUserId && (kind === "library" || kind === "folder")) {
      const result = await assignScoreToUser(scoreDragId, assignUserId, kind === "folder" ? folderId : "root");
      if (result) {
        insertAssignedScore(assignUserId, result.folderId, result.score, target);
        showToast("Score assigned");
      }
      return;
    }

    if (scoreDragId && kind === "folder" && libraryCtx) {
      const res = await Csrf.fetch(`/library/${libraryCtx}/scores/${scoreDragId}/folder`, {
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
      await uploadAndInsertScores(list, [], libraryCtx, folderId, {
        srcScoreId: dragPayload.scoreId,
        fileId: dragPayload.fileId,
      });
      return;
    }

    if (dragPayload && dragPayload.scoreId && kind === "aux") {
      const toScore = target.dataset.scoreId || target.closest("[data-score-id]")?.dataset.scoreId;
      if (!toScore || toScore === dragPayload.scoreId) return;
      const res = await Csrf.fetch(`/scores/${dragPayload.scoreId}/files/${dragPayload.fileId}/move`, {
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

  function bindFolderActions(root) {
    root.querySelectorAll(".new-folder-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
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
        if (res.ok) location.reload();
        else showToast("Folder create failed", true);
      });
    });
    root.querySelectorAll(".delete-folder-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!window.confirm("Delete this folder? Subfolders and scores move to the parent folder.")) return;
        const res = await Csrf.fetch(`/library/${btn.dataset.libraryCtx}/folders/${btn.dataset.folderId}/delete`, { method: "POST" });
        if (res.ok) location.reload();
      });
    });
  }

  window.LibraryDrop = { bindDropTargets };

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
        const result = await assignScoreToUser(scoreId, userId, "root");
        if (result) {
          insertAssignedScore(userId, result.folderId, result.score, assignPanel);
          showToast("Score assigned");
        }
      });
    }
  });
})();
