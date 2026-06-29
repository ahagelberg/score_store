(function () {
  "use strict";

  const AJAX_HEADER = "X-Requested-With";
  const AJAX_VALUE = "XMLHttpRequest";
  const PREVIEW_PARAM = "preview";
  const SETTINGS_OVERLAY_ID = "maestro-settings-overlay";
  const SETTINGS_BODY_ID = "maestro-settings-body";
  const SETTINGS_BTN_ID = "maestro-settings-btn";
  const SETTINGS_SAVE_ID = "maestro-settings-save";
  const CSRF_FIELD = "csrf_token";
  const CONFIG_URL = "/maestro/config";
  const APPEARANCE_URL = "/maestro/appearance";
  const PASSWORD_URL = "/maestro/password";
  const CONFIG_FIELD_NAMES = ["enable_printing", "enable_download"];
  const APPEARANCE_FIELD_NAMES = [
    "site_title",
    "show_site_title",
    "remove_logotype",
    "theme_css_text",
  ];
  const APPEARANCE_FILE_NAMES = ["logotype", "theme_css"];
  const PASSWORD_FIELD_NAMES = ["current_password", "new_password", "new_password_confirm"];

  function previewToken() {
    return new URLSearchParams(window.location.search).get(PREVIEW_PARAM) || "";
  }

  function scopedUrl(path) {
    return window.Csrf?.appendScopeParams?.(path) ?? path;
  }

  function settingsBody() {
    return document.getElementById(SETTINGS_BODY_ID);
  }

  function settingsOverlay() {
    return document.getElementById(SETTINGS_OVERLAY_ID);
  }

  function showSettings() {
    const el = settingsOverlay();
    if (!el) return;
    el.classList.remove("hidden");
    el.setAttribute("aria-hidden", "false");
  }

  function closeSettings() {
    const el = settingsOverlay();
    if (!el) return;
    el.classList.add("hidden");
    el.setAttribute("aria-hidden", "true");
  }

  function appendPreviewToFormData(body) {
    const token = previewToken();
    if (token && !body.has(PREVIEW_PARAM)) body.set(PREVIEW_PARAM, token);
  }

  function csrfToken() {
    return document.getElementById("maestro-settings-csrf")?.value
      || document.querySelector('meta[name="csrf-token"]')?.getAttribute("content")
      || "";
  }

  function appendCsrf(body) {
    const token = csrfToken();
    if (token) body.set(CSRF_FIELD, token);
  }

  function fieldValue(body, name) {
    const root = settingsBody();
    if (!root) return;
    const el = root.querySelector(`[name="${name}"]`);
    if (!el) return;
    if (el.type === "checkbox") {
      if (el.checked) body.set(name, el.value || "1");
      return;
    }
    if (el.type === "file") {
      if (el.files?.[0]) body.set(name, el.files[0]);
      return;
    }
    body.set(name, el.value);
  }

  function buildConfigFormData() {
    const body = new FormData();
    CONFIG_FIELD_NAMES.forEach((name) => fieldValue(body, name));
    appendCsrf(body);
    appendPreviewToFormData(body);
    return body;
  }

  function buildAppearanceFormData() {
    const body = new FormData();
    APPEARANCE_FIELD_NAMES.forEach((name) => fieldValue(body, name));
    APPEARANCE_FILE_NAMES.forEach((name) => fieldValue(body, name));
    appendCsrf(body);
    appendPreviewToFormData(body);
    return body;
  }

  function buildPasswordFormData() {
    const body = new FormData();
    PASSWORD_FIELD_NAMES.forEach((name) => fieldValue(body, name));
    appendCsrf(body);
    appendPreviewToFormData(body);
    return body;
  }

  function passwordChangeRequested() {
    const root = settingsBody();
    const current = root?.querySelector('[name="current_password"]');
    return Boolean(current?.value);
  }

  async function postForm(url, body) {
    const res = await Csrf.fetch(scopedUrl(url), {
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
    return { ok: res.ok, data };
  }

  async function saveSettings() {
    const configResult = await postForm(CONFIG_URL, buildConfigFormData());
    if (!configResult.ok) {
      window.showToast?.(configResult.data?.error || "Library config save failed", true);
      return;
    }
    const appearanceResult = await postForm(APPEARANCE_URL, buildAppearanceFormData());
    if (!appearanceResult.ok) {
      window.showToast?.(appearanceResult.data?.error || "Appearance save failed", true);
      return;
    }
    if (passwordChangeRequested()) {
      const passwordResult = await postForm(PASSWORD_URL, buildPasswordFormData());
      if (!passwordResult.ok) {
        window.showToast?.(passwordResult.data?.error || "Password change failed", true);
        return;
      }
      PASSWORD_FIELD_NAMES.forEach((name) => {
        const el = settingsBody()?.querySelector(`[name="${name}"]`);
        if (el) el.value = "";
      });
    }
    window.showToast?.("Settings saved");
    closeSettings();
    window.location.reload();
  }

  function bindSettings() {
    const btn = document.getElementById(SETTINGS_BTN_ID);
    if (btn) btn.addEventListener("click", showSettings);

    document.querySelectorAll("[data-maestro-settings-close]").forEach((el) => {
      el.addEventListener("click", closeSettings);
    });

    const overlay = settingsOverlay();
    if (overlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeSettings();
      });
    }

    const saveBtn = document.getElementById(SETTINGS_SAVE_ID);
    if (saveBtn) saveBtn.addEventListener("click", () => { saveSettings(); });
  }

  function bindEscape() {
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!settingsOverlay()?.classList.contains("hidden")) closeSettings();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById(SETTINGS_BTN_ID)) return;
    bindSettings();
    bindEscape();
  });
})();
