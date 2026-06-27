(function () {
  "use strict";

  const SYSTEM_INFO_URL = "/api/system";
  const VERSION_ELEMENT_ID = "site-header-version";
  const PRODUCT_NAME_SELECTOR = ".site-header-product-name";

  function applySystemInfo(info) {
    const versionEl = document.getElementById(VERSION_ELEMENT_ID);
    if (versionEl && info.version) {
      versionEl.textContent = info.version;
      versionEl.hidden = false;
    }
    const nameEl = document.querySelector(PRODUCT_NAME_SELECTOR);
    if (nameEl && info.name) nameEl.textContent = info.name;
  }

  async function loadSystemInfo() {
    if (!document.getElementById(VERSION_ELEMENT_ID)) return;
    try {
      const res = await fetch(SYSTEM_INFO_URL);
      if (!res.ok) return;
      applySystemInfo(await res.json());
    } catch (_) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadSystemInfo);
  } else {
    loadSystemInfo();
  }
})();
