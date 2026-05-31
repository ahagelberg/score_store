(function () {
  "use strict";

  const URL_SYNC_DEBOUNCE_MS = 300;
  const reapplyHandlers = [];

  function parsePreserve(root) {
    try {
      return JSON.parse(root.dataset.preserveParams || "{}");
    } catch {
      return {};
    }
  }

  function buildFilterUrl(root, query, tag) {
    const base = root.dataset.pageBase || window.location.pathname;
    const params = new URLSearchParams();
    const preserve = parsePreserve(root);
    Object.entries(preserve).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    if (query) params.set("q", query);
    if (tag) params.set("tag", tag);
    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  }

  function initFilterRoot(root) {
    const workspace = root.closest(".library-workspace");
    if (!workspace) return;
    const input = root.querySelector("[data-filter-input]");
    const clearBtn = root.querySelector("[data-filter-clear]");
    const list = workspace.querySelector(".score-list");
    const countEl = workspace.querySelector("[data-filter-count]");
    const emptyEl = workspace.querySelector("[data-filter-empty]");
    const tagButtons = workspace.querySelectorAll("[data-tag-filter]");
    let activeTag = root.dataset.activeTag || "";
    let urlTimer = null;

    function syncUrl() {
      const q = input ? input.value.trim() : "";
      const url = buildFilterUrl(root, q, activeTag);
      window.history.replaceState(null, "", url);
    }

    function scheduleUrlSync() {
      if (urlTimer) clearTimeout(urlTimer);
      urlTimer = setTimeout(syncUrl, URL_SYNC_DEBOUNCE_MS);
    }

    function applyFilter() {
      const q = input ? input.value.trim().toLowerCase() : "";
      let visible = 0;
      if (list) {
        list.querySelectorAll(".score-accordion").forEach((item) => {
          const text = (item.dataset.filterText || "").toLowerCase();
          const tags = (item.dataset.filterTags || "").split(",").filter(Boolean);
          const tagMatch = !activeTag || tags.includes(activeTag);
          const textMatch = !q || text.includes(q);
          const folderHidden = item.classList.contains("folder-filter-hidden");
          const show = tagMatch && textMatch && !folderHidden;
          item.classList.toggle("filter-hidden", !show);
          if (show) visible += 1;
        });
      }
      const folderTree = workspace.querySelector(".folder-tree");
      if (folderTree) {
        folderTree.querySelectorAll(".folder-tree-item").forEach((row) => {
          const name = (row.querySelector(".folder-tree-name")?.textContent || "").toLowerCase();
          row.classList.toggle("filter-hidden", q && !name.includes(q));
        });
      }
      if (countEl) countEl.textContent = visible ? `(${visible})` : "";
      if (emptyEl) emptyEl.classList.toggle("hidden", visible > 0);
      if (clearBtn) clearBtn.classList.toggle("hidden", !q);
      if (window.LibraryLayout?.syncScoreIdsForWorkspace) {
        window.LibraryLayout.syncScoreIdsForWorkspace(workspace);
      }
    }

    if (input) {
      input.addEventListener("input", () => {
        applyFilter();
        scheduleUrlSync();
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (input) input.value = "";
        applyFilter();
        syncUrl();
        input?.focus();
      });
    }

    tagButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const tag = btn.dataset.tag || "";
        if (activeTag === tag) {
          activeTag = "";
          btn.classList.remove("active");
        } else {
          activeTag = tag;
          tagButtons.forEach((b) => b.classList.toggle("active", b.dataset.tag === tag));
        }
        applyFilter();
        syncUrl();
      });
    });

    reapplyHandlers.push(applyFilter);
    applyFilter();
  }

  function initAll() {
    document.querySelectorAll("[data-filter-root]").forEach(initFilterRoot);
  }

  function reapplyAll() {
    reapplyHandlers.forEach((fn) => fn());
  }

  window.ScoreFilter = { initAll, reapplyAll };
  document.addEventListener("DOMContentLoaded", initAll);
})();
