(function () {
  "use strict";

  const AJAX_HEADER = "X-Requested-With";
  const AJAX_VALUE = "XMLHttpRequest";
  const PREVIEW_PARAM = "preview";
  const MENU_OVERLAY_ID = "maestro-menu-overlay";
  const CONFIG_OVERLAY_ID = "maestro-config-overlay";
  const APPEARANCE_OVERLAY_ID = "maestro-appearance-overlay";
  const PASSWORD_OVERLAY_ID = "maestro-password-overlay";
  const MENU_BTN_ID = "maestro-menu-btn";
  const BODY_MENU_OPEN_CLASS = "maestro-menu-open";

  function previewToken() {
    return new URLSearchParams(window.location.search).get(PREVIEW_PARAM) || "";
  }

  function scopedUrl(path) {
    return window.Csrf?.appendScopeParams?.(path) ?? path;
  }

  function overlay(id) {
    return document.getElementById(id);
  }

  function showOverlay(el) {
    if (!el) return;
    el.classList.remove("hidden");
    el.setAttribute("aria-hidden", "false");
  }

  function hideOverlay(el) {
    if (!el) return;
    el.classList.add("hidden");
    el.setAttribute("aria-hidden", "true");
  }

  function openMenu() {
    const menu = overlay(MENU_OVERLAY_ID);
    if (!menu) return;
    showOverlay(menu);
    document.body.classList.add(BODY_MENU_OPEN_CLASS);
  }

  function closeMenu() {
    const menu = overlay(MENU_OVERLAY_ID);
    hideOverlay(menu);
    document.body.classList.remove(BODY_MENU_OPEN_CLASS);
  }

  function openPanel(panelId) {
    closeMenu();
    showOverlay(overlay(panelId));
  }

  function closePanel(panelId) {
    hideOverlay(overlay(panelId));
  }

  function closeAllPanels() {
    closePanel(CONFIG_OVERLAY_ID);
    closePanel(APPEARANCE_OVERLAY_ID);
    closePanel(PASSWORD_OVERLAY_ID);
  }

  function appendPreviewToFormData(body) {
    const token = previewToken();
    if (token && !body.has(PREVIEW_PARAM)) body.set(PREVIEW_PARAM, token);
  }

  async function submitFormAjax(form, reloadOnSuccess) {
    const url = scopedUrl(form.getAttribute("action") || "");
    const body = new FormData(form);
    appendPreviewToFormData(body);
    const res = await Csrf.fetch(url, {
      method: "POST",
      body,
      headers: { [AJAX_HEADER]: AJAX_VALUE },
    });
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) {
      window.showToast?.(data?.error || "Save failed", true);
      return false;
    }
    window.showToast?.(data?.message || "Saved");
    if (reloadOnSuccess) window.location.reload();
    return true;
  }

  function bindMenu() {
    const menuBtn = document.getElementById(MENU_BTN_ID);
    if (menuBtn) menuBtn.addEventListener("click", openMenu);

    document.querySelectorAll("[data-maestro-menu-close]").forEach((el) => {
      el.addEventListener("click", closeMenu);
    });

    document.querySelectorAll("[data-maestro-menu-panel]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const panel = btn.dataset.maestroMenuPanel;
        if (panel === "config") openPanel(CONFIG_OVERLAY_ID);
        else if (panel === "appearance") openPanel(APPEARANCE_OVERLAY_ID);
        else if (panel === "password") openPanel(PASSWORD_OVERLAY_ID);
      });
    });
  }

  function bindSettingsDialogs() {
    document.querySelectorAll("[data-maestro-settings-close]").forEach((el) => {
      el.addEventListener("click", () => {
        closePanel(CONFIG_OVERLAY_ID);
        closePanel(APPEARANCE_OVERLAY_ID);
      });
    });

    [CONFIG_OVERLAY_ID, APPEARANCE_OVERLAY_ID, PASSWORD_OVERLAY_ID].forEach((id) => {
      const el = overlay(id);
      if (!el) return;
      el.addEventListener("click", (e) => {
        if (e.target === el) closePanel(id);
      });
    });

    document.querySelectorAll("[data-maestro-password-close]").forEach((el) => {
      el.addEventListener("click", () => closePanel(PASSWORD_OVERLAY_ID));
    });

    const configForm = document.getElementById("maestro-config-form");
    if (configForm) {
      configForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const ok = await submitFormAjax(configForm, true);
        if (ok) closePanel(CONFIG_OVERLAY_ID);
      });
    }

    const appearanceForm = document.getElementById("maestro-appearance-form");
    if (appearanceForm) {
      appearanceForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const ok = await submitFormAjax(appearanceForm, true);
        if (ok) closePanel(APPEARANCE_OVERLAY_ID);
      });
    }

    const passwordForm = document.getElementById("maestro-password-form");
    if (passwordForm) {
      passwordForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const ok = await submitFormAjax(passwordForm, false);
        if (ok) {
          passwordForm.reset();
          closePanel(PASSWORD_OVERLAY_ID);
        }
      });
    }
  }

  function bindEscape() {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!overlay(MENU_OVERLAY_ID)?.classList.contains("hidden")) {
        closeMenu();
        return;
      }
      closeAllPanels();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById(MENU_BTN_ID)) return;
    bindMenu();
    bindSettingsDialogs();
    bindEscape();
  });
})();
