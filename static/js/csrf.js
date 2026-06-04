(function () {
  "use strict";

  const CSRF_META_NAME = "csrf-token";
  const CSRF_HEADER = "X-CSRFToken";

  function csrfToken() {
    return document.querySelector(`meta[name="${CSRF_META_NAME}"]`)?.getAttribute("content") || "";
  }

  function csrfFetch(url, options) {
    const opts = { ...(options || {}) };
    const headers = new Headers(opts.headers || undefined);
    const token = csrfToken();
    if (token) headers.set(CSRF_HEADER, token);
    opts.headers = headers;
    return fetch(url, opts);
  }

  window.Csrf = { token: csrfToken, fetch: csrfFetch };
})();
