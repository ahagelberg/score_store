(function () {
  "use strict";

  const CSRF_META_NAME = "csrf-token";
  const CSRF_HEADER = "X-CSRFToken";
  const SCOPE_QUERY_KEYS = ["maestro", "user", "lib", "preview"];

  function csrfToken() {
    return document.querySelector(`meta[name="${CSRF_META_NAME}"]`)?.getAttribute("content") || "";
  }

  function appendScopeParams(url) {
    if (!url.startsWith("/")) return url;
    const pageParams = new URLSearchParams(window.location.search);
    const scoped = new URL(url, window.location.origin);
    SCOPE_QUERY_KEYS.forEach((key) => {
      if (!scoped.searchParams.has(key) && pageParams.has(key)) {
        scoped.searchParams.set(key, pageParams.get(key));
      }
    });
    return scoped.pathname + scoped.search;
  }

  function csrfFetch(url, options) {
    const opts = { ...(options || {}) };
    const headers = new Headers(opts.headers || undefined);
    const token = csrfToken();
    if (token) headers.set(CSRF_HEADER, token);
    opts.headers = headers;
    return fetch(appendScopeParams(url), opts);
  }

  window.Csrf = { token: csrfToken, fetch: csrfFetch, appendScopeParams };
})();
