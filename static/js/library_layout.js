(function () {
  "use strict";

  const STORAGE_KEY = "scorestore-library-layout";
  const VIEW_LIST = "list";
  const VIEW_FOLDER = "folder";
  const ROOT_FOLDER_ID = "root";
  const FOLDER_PARENT_KEY = "parent_id";
  const FOLDER_LIST_ENTRY_CLASS = "folder-list-entry";
  const FOLDER_PARENT_ENTRY_CLASS = "folder-parent-entry";
  const FOLDER_PARENT_ROOT_LABEL = "All scores";
  const LAYOUT_PARAM_KEYS = ["view", "folder", "user_folder"];
  const FOLDER_DEPTH_PARSE_RADIX = 10;
  const FOLDER_DEPTH_STEP = 1;
  const FOLDER_TREE_ROOT_DEPTH = 0;
  const NARROW_SCREEN_MAX_WIDTH_PX = 1023;
  const COMPACT_NAV_MEDIA = `(max-width: ${NARROW_SCREEN_MAX_WIDTH_PX}px)`;
  const FOLDER_PARENT_ICON_TEMPLATE_ID = "folder-parent-icon-template";

  function createFolderParentIcon() {
    const tpl = document.getElementById(FOLDER_PARENT_ICON_TEMPLATE_ID);
    if (tpl?.content?.firstElementChild) {
      return tpl.content.firstElementChild.cloneNode(true);
    }
    const icon = document.createElement("span");
    icon.className = "folder-list-icon folder-parent-icon";
    icon.setAttribute("aria-hidden", "true");
    return icon;
  }

  function isCompactFolderNav() {
    return window.matchMedia(COMPACT_NAV_MEDIA).matches;
  }

  function usesFolderNavigation(layout) {
    if (isCompactFolderNav()) return true;
    return storedViewMode(layout) === VIEW_FOLDER;
  }

  function displayViewMode(storedMode) {
    if (isCompactFolderNav()) return VIEW_LIST;
    return storedMode;
  }

  function installCompactNavListener() {
    if (window.__folderNavCompactListener) return;
    window.__folderNavCompactListener = true;
    window.matchMedia(COMPACT_NAV_MEDIA).addEventListener("change", () => {
      const layout = loadLayout();
      document.querySelectorAll(".library-workspace").forEach((workspace) => {
        setViewMode(workspace, storedViewMode(layout), layout);
      });
    });
  }

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

  function parseFolders(workspace) {
    try {
      return JSON.parse(workspace.dataset.folders || "[]");
    } catch {
      return [];
    }
  }

  function saveFolders(workspace, folders) {
    workspace.dataset.folders = JSON.stringify(folders);
  }

  function applyScoreFolderToAccordion(accordion, folderId) {
    accordion.dataset.scoreFolderId = folderId;
    accordion.dataset.folderId = folderId;
  }

  function canManageFolders(workspace) {
    return !!workspace.querySelector(".new-folder-btn");
  }

  function folderTreeItem(workspace, folderId) {
    return workspace.querySelector(`.folder-tree-item[data-folder-id="${CSS.escape(folderId)}"]`);
  }

  function setFolderTreeItemDepth(item, depth) {
    item.dataset.depth = String(depth);
    const link = item.querySelector(":scope > .folder-tree-row > .folder-tree-link");
    if (link) link.dataset.depth = String(depth);
    item.querySelectorAll(":scope > .folder-tree-children > .folder-tree-item").forEach((child) => {
      setFolderTreeItemDepth(child, depth + FOLDER_DEPTH_STEP);
    });
  }

  function insertFolderTreeItemSorted(parentChildren, item, folderName) {
    const siblings = [...parentChildren.querySelectorAll(":scope > .folder-tree-item")];
    const insertBefore = siblings.find((sibling) => {
      const siblingName = sibling.querySelector(".folder-tree-name")?.textContent || "";
      return (folderName || "").localeCompare(siblingName, undefined, { sensitivity: "base" }) < 0;
    });
    if (insertBefore) parentChildren.insertBefore(item, insertBefore);
    else parentChildren.appendChild(item);
  }

  function buildFolderTreeItem(folder, libraryCtx, depth, manageFolders) {
    const li = document.createElement("li");
    li.className = "folder-tree-item drop-target";
    li.dataset.dropKind = "folder";
    li.dataset.folderId = folder.id;
    li.dataset.depth = String(depth);
    li.dataset.libraryCtx = libraryCtx;
    const row = document.createElement("div");
    row.className = "folder-tree-row";
    const link = document.createElement("a");
    link.className = "folder-tree-link";
    link.href = "#";
    link.dataset.folderId = folder.id;
    link.dataset.depth = String(depth);
    const icon = document.createElement("span");
    icon.className = "folder-tree-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "📁";
    const name = document.createElement("span");
    name.className = "folder-tree-name";
    name.textContent = folder.name || folder.id;
    link.title = `Open ${folder.name || folder.id}`;
    link.append(icon, name);
    row.appendChild(link);
    if (manageFolders && folder.id !== ROOT_FOLDER_ID) {
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "btn-icon btn-icon-sm delete-folder-btn";
      deleteBtn.dataset.folderId = folder.id;
      deleteBtn.dataset.libraryCtx = libraryCtx;
      deleteBtn.title = "Delete folder";
      deleteBtn.textContent = "×";
      row.appendChild(deleteBtn);
    }
    const children = document.createElement("ul");
    children.className = "folder-tree-children";
    li.append(row, children);
    return li;
  }

  function insertFolder(workspace, folder) {
    const folders = parseFolders(workspace);
    folders.push(folder);
    saveFolders(workspace, folders);
    const libraryCtx = workspace.dataset.libraryCtx || workspaceCtx(workspace);
    const parentId = folder[FOLDER_PARENT_KEY] || ROOT_FOLDER_ID;
    const parentItem = folderTreeItem(workspace, parentId);
    const parentChildren = parentItem?.querySelector(":scope > .folder-tree-children");
    if (!parentChildren) return;
    const parentDepth = parseInt(parentItem.dataset.depth || String(FOLDER_TREE_ROOT_DEPTH), FOLDER_DEPTH_PARSE_RADIX);
    const item = buildFolderTreeItem(folder, libraryCtx, parentDepth + FOLDER_DEPTH_STEP, canManageFolders(workspace));
    insertFolderTreeItemSorted(parentChildren, item, folder.name);
    window.LibraryDrop?.bindDropTarget?.(item);
    refreshWorkspace(workspace);
  }

  function removeFolder(workspace, folderId) {
    const folders = parseFolders(workspace);
    const folder = folderById(folders, folderId);
    if (!folder) return;
    const parentId = folder[FOLDER_PARENT_KEY] || ROOT_FOLDER_ID;
    const updated = folders
      .filter((entry) => entry.id !== folderId)
      .map((entry) => {
        if ((entry[FOLDER_PARENT_KEY] || ROOT_FOLDER_ID) === folderId) {
          return { ...entry, [FOLDER_PARENT_KEY]: parentId };
        }
        return entry;
      });
    saveFolders(workspace, updated);
    workspace.querySelectorAll(".score-accordion").forEach((accordion) => {
      if ((accordion.dataset.scoreFolderId || ROOT_FOLDER_ID) === folderId) {
        applyScoreFolderToAccordion(accordion, parentId);
      }
    });
    const item = folderTreeItem(workspace, folderId);
    if (item) {
      const parentItem = item.parentElement?.closest(".folder-tree-item");
      const parentChildren = parentItem?.querySelector(":scope > .folder-tree-children");
      const deletedChildren = item.querySelector(":scope > .folder-tree-children");
      if (parentChildren && deletedChildren) {
        const parentDepth = parseInt(parentItem.dataset.depth || String(FOLDER_TREE_ROOT_DEPTH), FOLDER_DEPTH_PARSE_RADIX);
        while (deletedChildren.firstChild) {
          const child = deletedChildren.firstChild;
          parentChildren.appendChild(child);
          setFolderTreeItemDepth(child, parentDepth + FOLDER_DEPTH_STEP);
        }
      }
      item.remove();
    }
    const layout = loadLayout();
    if (storedFolderId(layout, workspace) === folderId) {
      setFolder(workspace, parentId, layout);
      return;
    }
    refreshWorkspace(workspace);
  }

  function folderById(folders, folderId) {
    return folders.find((folder) => folder.id === folderId) || null;
  }

  function parentFolderId(folders, folderId) {
    const folder = folderById(folders, folderId);
    if (!folder) return ROOT_FOLDER_ID;
    return folder[FOLDER_PARENT_KEY] || ROOT_FOLDER_ID;
  }

  function parentFolderLabel(folders, parentId) {
    if (parentId === ROOT_FOLDER_ID) return FOLDER_PARENT_ROOT_LABEL;
    const folder = folderById(folders, parentId);
    return folder?.name || FOLDER_PARENT_ROOT_LABEL;
  }

  function folderPath(folders, folderId) {
    const path = [];
    let currentId = folderId;
    while (currentId && currentId !== ROOT_FOLDER_ID) {
      const folder = folderById(folders, currentId);
      if (!folder) break;
      path.unshift(folder);
      currentId = folder[FOLDER_PARENT_KEY] || ROOT_FOLDER_ID;
    }
    return path;
  }

  function updateFolderBreadcrumb(workspace, storedMode, folderId) {
    const breadcrumb = workspace.querySelector("[data-folder-breadcrumb]");
    const titleEl = workspace.querySelector(".files-pane-title");
    if (!breadcrumb || !titleEl) return;
    const defaultTitle = titleEl.dataset.defaultTitle || titleEl.textContent;
    const showBreadcrumb = storedMode === VIEW_FOLDER && !isCompactFolderNav() && folderId !== ROOT_FOLDER_ID;
    if (!showBreadcrumb) {
      breadcrumb.replaceChildren();
      breadcrumb.classList.add("hidden");
      titleEl.classList.remove("hidden");
      titleEl.textContent = defaultTitle;
      return;
    }
    const segments = folderPath(parseFolders(workspace), folderId);
    if (segments.length === 0) {
      breadcrumb.replaceChildren();
      breadcrumb.classList.add("hidden");
      titleEl.classList.remove("hidden");
      titleEl.textContent = defaultTitle;
      return;
    }
    titleEl.classList.add("hidden");
    breadcrumb.classList.remove("hidden");
    breadcrumb.replaceChildren();
    segments.forEach((folder, index) => {
      if (index > 0) {
        const sep = document.createElement("span");
        sep.className = "folder-breadcrumb-sep";
        sep.textContent = "/";
        sep.setAttribute("aria-hidden", "true");
        breadcrumb.appendChild(sep);
      }
      if (index < segments.length - 1) {
        const link = document.createElement("a");
        link.className = "folder-breadcrumb-link";
        link.href = "#";
        link.dataset.folderId = folder.id;
        link.textContent = folder.name;
        link.addEventListener("click", (e) => {
          e.preventDefault();
          setFolder(workspace, folder.id, loadLayout());
        });
        breadcrumb.appendChild(link);
      } else {
        const current = document.createElement("span");
        current.className = "folder-breadcrumb-current";
        current.textContent = folder.name;
        breadcrumb.appendChild(current);
      }
    });
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

  function childFolders(folders, parentId) {
    return folders
      .filter((folder) => {
        if (folder.id === ROOT_FOLDER_ID) return false;
        return (folder[FOLDER_PARENT_KEY] || ROOT_FOLDER_ID) === parentId;
      })
      .sort((a, b) => (a.name || "").localeCompare(b.name || "", undefined, { sensitivity: "base" }));
  }

  function removeFolderListEntries(workspace) {
    workspace.querySelectorAll(`.${FOLDER_LIST_ENTRY_CLASS}, .${FOLDER_PARENT_ENTRY_CLASS}`).forEach((entry) => entry.remove());
  }

  function buildFolderParentEntry(parentId, label, libraryCtx, workspace) {
    const li = document.createElement("li");
    li.className = `${FOLDER_PARENT_ENTRY_CLASS} ${FOLDER_LIST_ENTRY_CLASS}`;
    li.dataset.filterName = label;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "folder-list-link folder-parent-link";
    btn.dataset.folderId = parentId;
    const icon = createFolderParentIcon();
    const name = document.createElement("span");
    name.className = "folder-list-name";
    name.textContent = label;
    btn.title = `Open ${label}`;
    btn.append(icon, name);
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      setFolder(workspace, parentId, loadLayout());
    });
    li.appendChild(btn);
    return li;
  }

  function buildFolderListEntry(folder, libraryCtx, workspace) {
    const li = document.createElement("li");
    li.className = `${FOLDER_LIST_ENTRY_CLASS} drop-target`;
    li.dataset.dropKind = "folder";
    li.dataset.folderId = folder.id;
    li.dataset.libraryCtx = libraryCtx;
    li.dataset.filterName = folder.name || "";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "folder-list-link";
    btn.dataset.folderId = folder.id;
    const icon = document.createElement("span");
    icon.className = "folder-list-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "📁";
    const name = document.createElement("span");
    name.className = "folder-list-name";
    name.textContent = folder.name || folder.id;
    const folderLabel = folder.name || folder.id;
    btn.title = `Open ${folderLabel}`;
    btn.append(icon, name);
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      setFolder(workspace, folder.id, loadLayout());
    });
    li.appendChild(btn);
    return li;
  }

  function syncFolderNavEntries(workspace, folderNav, folderId) {
    removeFolderListEntries(workspace);
    const list = workspace.querySelector(".score-list");
    if (!list || !folderNav) return;
    const libraryCtx = workspace.dataset.libraryCtx || workspaceCtx(workspace);
    const folders = parseFolders(workspace);
    const fragment = document.createDocumentFragment();
    if (folderId !== ROOT_FOLDER_ID) {
      const parentId = parentFolderId(folders, folderId);
      fragment.appendChild(
        buildFolderParentEntry(parentId, parentFolderLabel(folders, parentId), libraryCtx, workspace),
      );
    }
    childFolders(folders, folderId).forEach((folder) => {
      fragment.appendChild(buildFolderListEntry(folder, libraryCtx, workspace));
    });
    if (fragment.childNodes.length === 0) return;
    const firstScore = list.querySelector(".score-accordion");
    list.insertBefore(fragment, firstScore);
    list.querySelectorAll(`.${FOLDER_LIST_ENTRY_CLASS}`).forEach((entry) => {
      window.LibraryDrop?.bindDropTarget?.(entry);
    });
    if (window.ScoreFilter?.reapplyAll) window.ScoreFilter.reapplyAll();
  }

  function applyFolderFilter(workspace, folderId) {
    const layout = loadLayout();
    const folderNav = usesFolderNavigation(layout);
    syncFolderNavEntries(workspace, folderNav, folderId);
    workspace.querySelectorAll(".score-accordion").forEach((item) => {
      const inFolder = item.dataset.scoreFolderId || ROOT_FOLDER_ID;
      const hide = folderNav && inFolder !== folderId;
      item.classList.toggle("folder-filter-hidden", hide);
    });
    syncScoreIds(workspace);
    if (window.ScoreFilter?.reapplyAll) window.ScoreFilter.reapplyAll();
    window.ScoreEditorPreview?.reconcile?.();
  }

  function setViewMode(workspace, storedMode, layout) {
    workspace.dataset.libraryView = displayViewMode(storedMode);
    const folderId = storedFolderId(layout, workspace);
    workspace.querySelectorAll(".view-toggle-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.viewMode === storedMode);
    });
    setActiveFolderLink(workspace, folderId);
    setDropFolderIds(workspace, folderId);
    updateFolderBreadcrumb(workspace, storedMode, folderId);
    applyFolderFilter(workspace, folderId);
  }

  function setFolder(workspace, folderId, layout) {
    if (!layout.folders) layout.folders = {};
    const previousFolderId = storedFolderId(layout, workspace);
    layout.folders[workspaceCtx(workspace)] = folderId;
    saveLayout(layout);
    const storedMode = storedViewMode(layout);
    setActiveFolderLink(workspace, folderId);
    setDropFolderIds(workspace, folderId);
    updateFolderBreadcrumb(workspace, storedMode, folderId);
    if (previousFolderId !== folderId) {
      window.ScoreEditor?.collapseAllExpanded?.(workspace);
    }
    applyFolderFilter(workspace, folderId);
  }

  function folderIdForWorkspace(workspace) {
    return storedFolderId(loadLayout(), workspace);
  }

  function bindWorkspace(workspace, layout) {
    if (workspace.dataset.layoutBound === "true") {
      refreshWorkspace(workspace);
      return;
    }
    workspace.dataset.layoutBound = "true";
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
    if (!workspace.dataset.folderTreeClickBound) {
      workspace.dataset.folderTreeClickBound = "true";
      workspace.addEventListener("click", (e) => {
        const link = e.target.closest(".folder-tree-link");
        if (!link || !workspace.contains(link)) return;
        e.preventDefault();
        const activeLayout = loadLayout();
        if (workspace.dataset.libraryView !== VIEW_FOLDER) {
          activeLayout.viewMode = VIEW_FOLDER;
          saveLayout(activeLayout);
          setViewMode(workspace, VIEW_FOLDER, activeLayout);
        }
        setFolder(workspace, link.dataset.folderId || ROOT_FOLDER_ID, activeLayout);
      });
    }
  }

  function initChoirReset(root) {
    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "btn btn-sm";
    resetBtn.textContent = "Reset layout";
    resetBtn.title = "Reset layout";
    resetBtn.addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      location.reload();
    });
    const toolbar = root.querySelector(".desktop-panel-header") || root;
    toolbar.appendChild(resetBtn);
  }

  function refreshWorkspace(workspace) {
    if (!workspace) return;
    const layout = loadLayout();
    setViewMode(workspace, storedViewMode(layout), layout);
  }

  function initWorkspaces(root) {
    installCompactNavListener();
    const layout = loadLayout();
    (root || document).querySelectorAll(".library-workspace").forEach((workspace) => {
      bindWorkspace(workspace, layout);
    });
  }

  function init(options) {
    stripLayoutParams();
    initWorkspaces(options?.root || document);
    if (options?.choirReset) initChoirReset(options.root);
  }

  window.LibraryLayout = {
    init,
    initWorkspaces,
    stripLayoutParams,
    initChoirReset,
    syncScoreIdsForWorkspace: syncScoreIds,
    refreshWorkspace,
    loadLayout,
    saveLayout,
    folderIdForWorkspace,
    insertFolder,
    removeFolder,
    applyScoreFolderToAccordion,
    STORAGE_KEY,
  };
})();
