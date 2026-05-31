(function () {
  "use strict";

  const STORAGE_KEY = "scorestore-library-layout";
  const VIEW_LIST = "list";
  const VIEW_FOLDER = "folder";
  const ROOT_FOLDER_ID = "root";
  const LAYOUT_PARAM_KEYS = ["view", "folder", "user_folder"];

  function loadLayout() {
    try {
      const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      if (data.folderId && !data.folders) {
        data.folders = { default: data.folderId };
        delete data.folderId;
      }
      return data;
    } catch {
      return {};
    }
  }

  function saveLayout(data) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  function workspaceCtx(workspace) {
    return workspace.dataset.libraryCtx || workspace.querySelector(".files-pane")?.dataset.libraryCtx || "default";
  }

  function storedViewMode(layout) {
    return layout.viewMode === VIEW_FOLDER ? VIEW_FOLDER : VIEW_LIST;
  }

  function storedFolderId(layout, workspace) {
    return layout.folders?.[workspaceCtx(workspace)] || ROOT_FOLDER_ID;
  }

  function stripLayoutParams() {
    const params = new URLSearchParams(window.location.search);
    let changed = false;
    LAYOUT_PARAM_KEYS.forEach((key) => {
      if (params.has(key)) {
        params.delete(key);
        changed = true;
      }
    });
    if (!changed) return;
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `${window.location.pathname}?${qs}` : window.location.pathname);
  }

  function syncScoreIds(workspace) {
    const ids = [...workspace.querySelectorAll(".score-accordion")]
      .filter((el) => !el.classList.contains("filter-hidden") && !el.classList.contains("folder-filter-hidden"))
      .map((el) => el.dataset.scoreId)
      .filter(Boolean);
    workspace.dataset.scoreIds = JSON.stringify(ids);
  }

  function updatePaneTitle(workspace, viewMode, folderId) {
    const titleEl = workspace.querySelector(".files-pane-title");
    if (!titleEl) return;
    const defaultTitle = titleEl.dataset.defaultTitle || titleEl.textContent;
    if (viewMode !== VIEW_FOLDER) {
      titleEl.textContent = defaultTitle;
      return;
    }
    const folderName = workspace.querySelector(`.folder-tree-link[data-folder-id="${folderId}"] .folder-tree-name`)?.textContent;
    titleEl.textContent = folderName || defaultTitle;
  }

  function setActiveFolderLink(workspace, folderId) {
    workspace.querySelectorAll(".folder-tree-link").forEach((link) => {
      link.classList.toggle("active", link.dataset.folderId === folderId);
    });
  }

  function setDropFolderIds(workspace, folderId) {
    const ctx = workspaceCtx(workspace);
    workspace.querySelectorAll(".files-pane, .score-accordion").forEach((el) => {
      if (el.dataset.libraryCtx === ctx) el.dataset.folderId = folderId;
    });
  }

  function applyFolderFilter(workspace, viewMode, folderId) {
    workspace.querySelectorAll(".score-accordion").forEach((item) => {
      const inFolder = item.dataset.scoreFolderId || ROOT_FOLDER_ID;
      const hide = viewMode === VIEW_FOLDER && inFolder !== folderId;
      item.classList.toggle("folder-filter-hidden", hide);
    });
    syncScoreIds(workspace);
    if (window.ScoreFilter?.reapplyAll) window.ScoreFilter.reapplyAll();
  }

  function setViewMode(workspace, viewMode, layout) {
    workspace.dataset.libraryView = viewMode;
    const folderId = storedFolderId(layout, workspace);
    workspace.querySelectorAll(".view-toggle-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.viewMode === viewMode);
    });
    setActiveFolderLink(workspace, folderId);
    setDropFolderIds(workspace, folderId);
    updatePaneTitle(workspace, viewMode, folderId);
    applyFolderFilter(workspace, viewMode, folderId);
  }

  function setFolder(workspace, folderId, layout) {
    if (!layout.folders) layout.folders = {};
    layout.folders[workspaceCtx(workspace)] = folderId;
    saveLayout(layout);
    const viewMode = workspace.dataset.libraryView || VIEW_LIST;
    setActiveFolderLink(workspace, folderId);
    setDropFolderIds(workspace, folderId);
    updatePaneTitle(workspace, viewMode, folderId);
    applyFolderFilter(workspace, viewMode, folderId);
  }

  function bindWorkspace(workspace, layout) {
    const viewMode = storedViewMode(layout);
    setViewMode(workspace, viewMode, layout);
    workspace.querySelectorAll(".view-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.viewMode;
        if (!mode || workspace.dataset.libraryView === mode) return;
        layout.viewMode = mode;
        saveLayout(layout);
        setViewMode(workspace, mode, layout);
      });
    });
    workspace.querySelectorAll(".folder-tree-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        if (workspace.dataset.libraryView !== VIEW_FOLDER) {
          layout.viewMode = VIEW_FOLDER;
          saveLayout(layout);
          setViewMode(workspace, VIEW_FOLDER, layout);
        }
        setFolder(workspace, link.dataset.folderId || ROOT_FOLDER_ID, layout);
      });
    });
  }

  function initChoirReset(root) {
    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "btn btn-sm";
    resetBtn.textContent = "Reset layout";
    resetBtn.addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      location.reload();
    });
    const toolbar = root.querySelector(".desktop-panel-header") || root;
    toolbar.appendChild(resetBtn);
  }

  function init(options) {
    stripLayoutParams();
    const layout = loadLayout();
    document.querySelectorAll(".library-workspace").forEach((workspace) => bindWorkspace(workspace, layout));
    if (options?.choirReset) initChoirReset(options.root);
  }

  window.LibraryLayout = { init, syncScoreIdsForWorkspace: syncScoreIds, loadLayout, saveLayout, STORAGE_KEY };
  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("library-root");
    const maestroRoot = document.getElementById("maestro-root");
    if (!root && !maestroRoot) return;
    init({ choirReset: root?.dataset.isChoir === "true", root: root || maestroRoot });
  });
})();
