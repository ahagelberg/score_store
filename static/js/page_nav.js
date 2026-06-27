(function () {
  "use strict";

  const AJAX_HEADER = "X-Requested-With";
  const AJAX_VALUE = "XMLHttpRequest";
  const MAESTRO_ROOT_ID = "maestro-root";
  const ADMIN_ROOT_ID = "admin-root";
  const MAESTRO_USER_LIB_SELECTOR = "#maestro-user-lib";
  const MAESTRO_USER_TREE_SELECTOR = "#maestro-users .user-tree-panel";
  const ADMIN_LIBRARY_SELECTOR = ".admin-col-library";
  const ADMIN_USER_TREE_SELECTOR = ".admin-col-tree .user-tree-panel";

  let navigating = false;

  async function fetchPartial(url) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: {
        [AJAX_HEADER]: AJAX_VALUE,
        Accept: "application/json",
      },
    });
    if (!res.ok) {
      throw new Error(`Request failed (${res.status})`);
    }
    return res.json();
  }

  function replaceOuter(selector, html) {
    if (!html) return;
    const current = document.querySelector(selector);
    if (!current) return;
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    const next = wrapper.firstElementChild;
    if (!next) return;
    current.replaceWith(next);
  }

  function replaceInner(selector, html) {
    const current = document.querySelector(selector);
    if (current) current.innerHTML = html;
  }

  function initInjectedContent(root) {
    if (!root) return;
    if (window.LibraryBootstrap?.bootstrapLibraryRoot) {
      window.LibraryBootstrap.bootstrapLibraryRoot(root);
      return;
    }
    if (window.LibraryLayout?.initWorkspaces) window.LibraryLayout.initWorkspaces(root);
    if (window.ScoreFilter?.initAll) window.ScoreFilter.initAll(root);
    if (window.ScoreEditor?.initExisting) window.ScoreEditor.initExisting(root);
    if (window.LibraryPage?.initRoot) window.LibraryPage.initRoot(root);
    if (window.ScorePrint?.bindPrintButtons) window.ScorePrint.bindPrintButtons(root);
    if (window.TagInput?.initAll) window.TagInput.initAll(root);
  }

  function buildUrl(base, nav) {
    const url = new URL(base, window.location.origin);
    const params = new URLSearchParams(url.search);
    Object.entries(nav || {}).forEach(([key, value]) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });
    url.search = params.toString();
    return url.toString();
  }

  async function navigate(url, pushState) {
    if (navigating) return;
    navigating = true;
    try {
      const data = await fetchPartial(url);
      if (document.getElementById(MAESTRO_ROOT_ID)) {
        replaceInner(MAESTRO_USER_LIB_SELECTOR, data.user_library_html || "");
        replaceOuter(MAESTRO_USER_TREE_SELECTOR, data.user_tree_html);
        initInjectedContent(document.getElementById(MAESTRO_ROOT_ID));
      } else if (document.getElementById(ADMIN_ROOT_ID)) {
        replaceInner(ADMIN_LIBRARY_SELECTOR, data.library_html || "");
        replaceOuter(ADMIN_USER_TREE_SELECTOR, data.user_tree_html);
        initInjectedContent(document.getElementById(ADMIN_ROOT_ID));
      }
      const nextUrl = data.url || url;
      if (pushState !== false) {
        window.history.pushState({ partial: true }, "", nextUrl);
      } else {
        window.history.replaceState({ partial: true }, "", nextUrl);
      }
    } catch {
      window.location.assign(url);
    } finally {
      navigating = false;
    }
  }

  async function refreshMaestro(nav) {
    const url = buildUrl(window.location.pathname, nav);
    await navigate(url, false);
  }

  async function refreshAdmin(nav) {
    const url = buildUrl(window.location.pathname, nav);
    await navigate(url, false);
  }

  function treeLinkFromEvent(event) {
    const root = event.target.closest(`#${MAESTRO_ROOT_ID}, #${ADMIN_ROOT_ID}`);
    if (!root) return null;
    const link = event.target.closest(".user-tree-link");
    if (!link || !root.contains(link)) return null;
    if (event.defaultPrevented) return null;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return null;
    }
    return link;
  }

  document.addEventListener("click", (event) => {
    const link = treeLinkFromEvent(event);
    if (!link) return;
    event.preventDefault();
    navigate(link.href);
  });

  window.addEventListener("popstate", () => {
    if (!document.getElementById(MAESTRO_ROOT_ID) && !document.getElementById(ADMIN_ROOT_ID)) {
      return;
    }
    navigate(window.location.href, false);
  });

  window.PageNav = {
    navigate,
    refreshMaestro,
    refreshAdmin,
  };
})();
