(function () {
  "use strict";

  const AJAX_HEADER = "X-Requested-With";
  const AJAX_VALUE = "XMLHttpRequest";

  function setMaestroDialogAutocomplete(mode, username) {
    const usernameField = document.getElementById("maestro-username");
    const pw = document.getElementById("maestro-password");
    if (!usernameField || !pw) return;
    const section = mode === "edit" && username
      ? `section-maestro-edit-${username}`
      : "section-maestro-new";
    usernameField.autocomplete = `${section} username`;
    pw.autocomplete = `${section} new-password`;
  }

  function clearMaestroDialogAutocomplete() {
    const usernameField = document.getElementById("maestro-username");
    const pw = document.getElementById("maestro-password");
    if (usernameField) usernameField.autocomplete = "off";
    if (pw) {
      pw.autocomplete = "off";
      pw.value = "";
    }
  }

  function closeMaestroDialog() {
    const overlay = document.getElementById("maestro-dialog-overlay");
    if (overlay) overlay.classList.add("hidden");
    clearMaestroDialogAutocomplete();
  }

  function setMaestroLogotypePreview(logotypeUrl) {
    const wrap = document.getElementById("maestro-logotype-preview-wrap");
    const img = document.getElementById("maestro-logotype-preview");
    const removeWrap = document.getElementById("maestro-remove-logotype-wrap");
    const removeCb = document.getElementById("maestro-remove-logotype");
    if (!wrap || !img) return;
    if (logotypeUrl) {
      img.src = logotypeUrl;
      wrap.classList.remove("hidden");
      if (removeWrap) removeWrap.classList.remove("hidden");
      if (removeCb) removeCb.checked = false;
    } else {
      img.removeAttribute("src");
      wrap.classList.add("hidden");
      if (removeWrap) removeWrap.classList.add("hidden");
      if (removeCb) removeCb.checked = false;
    }
  }

  function maestroPasswordHint() {
    const pw = document.getElementById("maestro-password");
    return pw?.closest(".settings-option")?.querySelector(".settings-option-hint") || null;
  }

  function openMaestroDialog(mode, maestro) {
    const overlay = document.getElementById("maestro-dialog-overlay");
    const form = document.getElementById("maestro-dialog-form");
    const title = document.getElementById("maestro-dialog-title");
    const pw = document.getElementById("maestro-password");
    const hint = maestroPasswordHint();
    const deleteBtn = document.getElementById("maestro-delete-btn");
    const themeTextGroup = document.getElementById("maestro-theme-text-group");
    const logotypeInput = document.getElementById("maestro-logotype");
    if (!overlay || !form || !pw) return;
    if (mode === "edit" && maestro) {
      title.textContent = "Edit maestro";
      form.action = `/admin/maestros/${maestro.id}`;
      form.method = "post";
      document.getElementById("maestro-dialog-id").value = maestro.id;
      document.getElementById("maestro-display-name").value = maestro.displayName;
      document.getElementById("maestro-username").value = maestro.username;
      document.getElementById("maestro-site-title").value = maestro.siteTitle || "";
      const showTitle = document.getElementById("maestro-show-site-title");
      if (showTitle) showTitle.checked = maestro.showSiteTitle !== false;
      pw.required = false;
      pw.value = "";
      if (hint) hint.textContent = "Leave blank to keep current password";
      if (deleteBtn) deleteBtn.classList.remove("hidden");
      if (themeTextGroup) themeTextGroup.classList.remove("hidden");
      if (logotypeInput) logotypeInput.value = "";
      setMaestroLogotypePreview(maestro.logotypeUrl || "");
      setMaestroDialogAutocomplete("edit", maestro.username);
    } else {
      title.textContent = "Add maestro";
      form.action = "/admin/maestros";
      form.method = "post";
      form.reset();
      const showTitle = document.getElementById("maestro-show-site-title");
      if (showTitle) showTitle.checked = true;
      pw.required = true;
      if (hint) hint.textContent = "Required for new maestros";
      if (deleteBtn) deleteBtn.classList.add("hidden");
      if (themeTextGroup) themeTextGroup.classList.add("hidden");
      if (logotypeInput) logotypeInput.value = "";
      setMaestroLogotypePreview("");
      setMaestroDialogAutocomplete("new");
    }
    overlay.classList.remove("hidden");
  }

  function openPasswordDialog() {
    const overlay = document.getElementById("maestro-password-overlay");
    const form = document.getElementById("maestro-password-form");
    if (!overlay || !form) return;
    form.action = "/admin/password";
    form.reset();
    overlay.classList.remove("hidden");
  }

  function closePasswordDialog() {
    const overlay = document.getElementById("maestro-password-overlay");
    if (overlay) overlay.classList.add("hidden");
  }

  async function deleteMaestro(maestroId, displayName) {
    const msg = `Delete maestro "${displayName}"?\n\nAll scores, libraries, and sub-accounts will be removed.`;
    if (!window.confirm(msg)) return;
    const res = await Csrf.fetch(`/admin/maestros/${maestroId}`, { method: "DELETE" });
    if (!res.ok && window.showToast) showToast("Delete failed", true);
    else if (window.PageNav?.refreshAdmin) await window.PageNav.refreshAdmin({});
    else window.location.assign("/admin");
  }

  async function deleteMaestroBackup(maestroId, filename) {
    const msg = `Delete backup "${filename}"?`;
    if (!window.confirm(msg)) return;
    try {
      const res = await Csrf.fetch(
        `/admin/maestros/${encodeURIComponent(maestroId)}/backups/${encodeURIComponent(filename)}`,
        { method: "DELETE", headers: { [AJAX_HEADER]: AJAX_VALUE } },
      );
      let data = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }
      if (!res.ok) {
        window.showToast?.(data?.error || "Delete failed", true);
        return;
      }
      window.showToast?.(data?.message || "Backup deleted");
      if (window.PageNav?.refreshAdmin) await window.PageNav.refreshAdmin({});
      else window.location.reload();
    } catch {
      window.showToast?.("Delete failed", true);
    }
  }

  async function createMaestroBackup(maestroId, button) {
    if (!maestroId) return;
    const body = new FormData();
    body.set("csrf_token", Csrf.token());
    if (button) button.disabled = true;
    try {
      const res = await Csrf.fetch(`/admin/maestros/${encodeURIComponent(maestroId)}/backup`, {
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
        window.showToast?.(data?.error || "Backup failed", true);
        return;
      }
      window.showToast?.(data?.message || "Backup created");
      if (window.PageNav?.refreshAdmin) await window.PageNav.refreshAdmin({});
      else window.location.reload();
    } catch {
      window.showToast?.("Backup failed", true);
    } finally {
      if (button && button.dataset.backupEnabled === "1") button.disabled = false;
    }
  }

  async function submitBackupConfig(form) {
    const body = new FormData(form);
    try {
      const res = await Csrf.fetch(form.action, {
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
        return;
      }
      window.showToast?.(data?.message || "Saved");
      if (window.PageNav?.refreshAdmin) await window.PageNav.refreshAdmin({});
    } catch {
      window.showToast?.("Save failed", true);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("admin-root");
    if (!root) return;

    const addBtn = document.getElementById("add-maestro-btn");
    if (addBtn) addBtn.addEventListener("click", () => openMaestroDialog("new"));

    root.addEventListener("click", (event) => {
      const editBtn = event.target.closest(".maestro-edit-btn");
      if (editBtn && root.contains(editBtn)) {
        openMaestroDialog("edit", {
          id: editBtn.dataset.maestroId,
          displayName: editBtn.dataset.displayName,
          username: editBtn.dataset.username,
          siteTitle: editBtn.dataset.siteTitle || "",
          showSiteTitle: editBtn.dataset.showSiteTitle !== "0",
          logotypeUrl: editBtn.dataset.logotypeUrl || "",
        });
        return;
      }
      const deleteBtn = event.target.closest(".maestro-delete-btn");
      if (deleteBtn && root.contains(deleteBtn)) {
        deleteMaestro(deleteBtn.dataset.maestroId, deleteBtn.dataset.displayName);
        return;
      }
      const backupBtn = event.target.closest("#admin-maestro-backup-btn");
      if (backupBtn && root.contains(backupBtn)) {
        createMaestroBackup(backupBtn.dataset.maestroId, backupBtn);
        return;
      }
      const backupDeleteBtn = event.target.closest(".maestro-backup-delete-btn");
      if (backupDeleteBtn && root.contains(backupDeleteBtn)) {
        deleteMaestroBackup(backupDeleteBtn.dataset.maestroId, backupDeleteBtn.dataset.filename);
      }
    });

    root.addEventListener("submit", (event) => {
      const configForm = event.target.closest("#admin-backup-config-form");
      if (!configForm || !root.contains(configForm)) return;
      event.preventDefault();
      submitBackupConfig(configForm);
    });

    const deleteBtn = document.getElementById("maestro-delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", () => {
        const maestroId = document.getElementById("maestro-dialog-id").value;
        const displayName = document.getElementById("maestro-display-name").value || "this maestro";
        if (maestroId) deleteMaestro(maestroId, displayName);
      });
    }

    document.querySelectorAll("[data-maestro-dialog-close]").forEach((el) => {
      el.addEventListener("click", closeMaestroDialog);
    });

    document.querySelectorAll("#admin-password-btn").forEach((btn) => {
      btn.addEventListener("click", openPasswordDialog);
    });

    document.querySelectorAll("[data-maestro-password-close]").forEach((el) => {
      el.addEventListener("click", closePasswordDialog);
    });

    const passwordOverlay = document.getElementById("maestro-password-overlay");
    if (passwordOverlay) {
      passwordOverlay.addEventListener("click", (e) => {
        if (e.target === passwordOverlay) closePasswordDialog();
      });
    }

    const maestroOverlay = document.getElementById("maestro-dialog-overlay");
    if (maestroOverlay) {
      maestroOverlay.addEventListener("click", (e) => {
        if (e.target === maestroOverlay) closeMaestroDialog();
      });
    }
  });
})();
