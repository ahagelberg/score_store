(function () {
  "use strict";

  const MAESTRO_ROLE = "maestro";
  const PREVIEW_PARAM = "preview";
  const AJAX_HEADER = "X-Requested-With";
  const AJAX_VALUE = "XMLHttpRequest";
  const MAESTRO_ROOT_ID = "maestro-root";
  let editUserPassword = "";
  let handoutUserId = "";

  function maestroRoot() {
    return document.getElementById(MAESTRO_ROOT_ID);
  }

  function previewTokenFromPage() {
    const form = document.getElementById("user-dialog-form");
    const fromForm = form?.dataset?.previewToken || "";
    return fromForm || new URLSearchParams(window.location.search).get(PREVIEW_PARAM) || "";
  }

  function ensurePreviewField(form) {
    const token = previewTokenFromPage()
      || form.querySelector(`input[name="${PREVIEW_PARAM}"]`)?.value
      || "";
    if (!token) return;
    let input = form.querySelector(`input[name="${PREVIEW_PARAM}"]`);
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = PREVIEW_PARAM;
      form.appendChild(input);
    }
    input.value = token;
  }

  function configurePasswordField(mode, user, pw, hint, roleEl) {
    const role = roleEl ? roleEl.value : (user?.role || "");
    const isMaestro = role === MAESTRO_ROLE;
    if (mode === "edit" && user) {
      pw.required = false;
      if (isMaestro) {
        pw.value = "";
        hint.textContent = "Encrypted passwords are not stored for viewing";
      } else {
        pw.value = user.password || "";
        hint.textContent = user.password
          ? "Leave blank to keep current password"
          : "Not on file — enter to set and store";
      }
      return;
    }
    pw.required = true;
    pw.value = "";
    hint.textContent = "Required for new users";
  }

  function updateHandoutButton(mode, roleEl) {
    const handoutBtn = document.getElementById("user-handout-btn");
    const userId = document.getElementById("user-dialog-user-id")?.value || "";
    if (!handoutBtn) return;
    const role = roleEl?.value || "";
    const show = mode === "edit" && userId && role !== MAESTRO_ROLE;
    handoutBtn.classList.toggle("hidden", !show);
  }

  function scopedUrl(path) {
    return window.Csrf?.appendScopeParams?.(path) ?? path;
  }

  function openDialog(mode, user) {
    const overlay = document.getElementById("user-dialog-overlay");
    const form = document.getElementById("user-dialog-form");
    const title = document.getElementById("user-dialog-title");
    const pw = document.getElementById("user-password");
    const hint = document.getElementById("user-password-hint");
    const roleEl = document.getElementById("user-role");
    const deleteBtn = document.getElementById("user-delete-btn");
    if (!overlay || !form || !pw || !hint) return;
    if (mode === "edit" && user) {
      title.textContent = "Edit user";
      form.action = scopedUrl(`/maestro/users/${user.id}/edit`);
      ensurePreviewField(form);
      document.getElementById("user-dialog-user-id").value = user.id;
      document.getElementById("user-display-name").value = user.displayName;
      document.getElementById("user-username").value = user.username;
      if (roleEl) roleEl.value = user.role;
      editUserPassword = user.password || "";
      if (deleteBtn) deleteBtn.classList.remove("hidden");
    } else {
      title.textContent = "Add user";
      form.reset();
      form.action = scopedUrl("/maestro/users/new");
      ensurePreviewField(form);
      editUserPassword = "";
      if (deleteBtn) deleteBtn.classList.add("hidden");
    }
    configurePasswordField(mode, user, pw, hint, roleEl);
    updateHandoutButton(mode, roleEl);
    overlay.classList.remove("hidden");
  }

  function closeDialog() {
    const overlay = document.getElementById("user-dialog-overlay");
    if (overlay) overlay.classList.add("hidden");
  }

  function closeHandoutDialog() {
    const overlay = document.getElementById("user-handout-overlay");
    if (overlay) overlay.classList.add("hidden");
    handoutUserId = "";
  }

  function openPasswordDialog() {
    const overlay = document.getElementById("maestro-password-overlay");
    const form = document.getElementById("maestro-password-form");
    if (!overlay || !form) return;
    form.reset();
    overlay.classList.remove("hidden");
  }

  function closePasswordDialog() {
    const overlay = document.getElementById("maestro-password-overlay");
    if (overlay) overlay.classList.add("hidden");
  }

  async function openHandoutDialog(userId) {
    const overlay = document.getElementById("user-handout-overlay");
    const content = document.getElementById("user-handout-content");
    if (!overlay || !content || !userId) return;
    handoutUserId = userId;
    content.innerHTML = "<p class=\"user-handout-note\">Loading…</p>";
    overlay.classList.remove("hidden");
    try {
      const res = await fetch(scopedUrl(`/maestro/users/${userId}/handout`));
      if (!res.ok) throw new Error("Failed to load handout");
      content.innerHTML = await res.text();
    } catch {
      content.innerHTML = "<p class=\"user-handout-note\">Could not load account details.</p>";
    }
  }

  async function toggleAssign(userId, scoreId, assign) {
    const res = await Csrf.fetch("/maestro/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, score_id: scoreId, assign }),
    });
    if (!res.ok && window.showToast) showToast("Assignment failed", true);
  }

  async function refreshAfterUserChange(nav) {
    if (window.PageNav?.refreshMaestro) {
      await window.PageNav.refreshMaestro(nav || {});
      return;
    }
    window.location.reload();
  }

  async function submitUserForm(event) {
    event.preventDefault();
    const form = event.currentTarget;
    ensurePreviewField(form);
    const urlBase = scopedUrl(form.getAttribute("action") || "/maestro/users/new");
    const pageParams = new URLSearchParams(window.location.search);
    const url = pageParams.get("user")
      ? `${urlBase}${urlBase.includes("?") ? "&" : "?"}user=${encodeURIComponent(pageParams.get("user"))}`
      : urlBase;
    const body = new FormData(form);
    if (previewTokenFromPage() && !body.has(PREVIEW_PARAM)) {
      body.set(PREVIEW_PARAM, previewTokenFromPage());
    }
    try {
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
        const msg = data?.error || (res.status === 403 ? "Not authorized — reopen preview and try again" : "Save failed");
        window.showToast?.(msg, true);
        return;
      }
      closeDialog();
      window.showToast?.(data?.message || "Saved");
      await refreshAfterUserChange(data?.nav || {});
    } catch {
      window.showToast?.("Save failed", true);
    }
  }

  async function deleteUser(userId, displayName) {
    const msg =
      `Delete "${displayName}"?\n\nTheir library and assignments will be removed. Scores they own will stay in the global library under system ownership.`;
    if (!window.confirm(msg)) return;
    const params = new URLSearchParams(window.location.search);
    const body = new FormData();
    body.set("csrf_token", Csrf.token());
    const selected = params.get("user");
    if (selected) body.set("user", selected);
    if (previewTokenFromPage()) body.set(PREVIEW_PARAM, previewTokenFromPage());
    try {
      const res = await Csrf.fetch(scopedUrl(`/maestro/users/${userId}/delete?${params.toString()}`), {
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
        window.showToast?.(data?.error || "Delete failed", true);
        return;
      }
      closeDialog();
      window.showToast?.(data?.message || "User deleted");
      await refreshAfterUserChange(data?.nav || {});
    } catch {
      window.showToast?.("Delete failed", true);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = maestroRoot();
    if (!root) return;

    const userForm = document.getElementById("user-dialog-form");
    if (userForm) userForm.addEventListener("submit", submitUserForm);

    const addBtn = document.getElementById("add-user-btn");
    if (addBtn) addBtn.addEventListener("click", () => openDialog("new"));

    root.addEventListener("click", (event) => {
      const editBtn = event.target.closest(".user-edit-btn");
      if (editBtn && root.contains(editBtn)) {
        openDialog("edit", {
          id: editBtn.dataset.userId,
          displayName: editBtn.dataset.displayName,
          username: editBtn.dataset.username,
          role: editBtn.dataset.role,
          password: editBtn.dataset.password || "",
        });
        return;
      }
      const handoutBtn = event.target.closest(".user-handout-tree-btn");
      if (handoutBtn && root.contains(handoutBtn)) {
        openHandoutDialog(handoutBtn.dataset.userId);
      }
    });

    root.addEventListener("change", (event) => {
      const cb = event.target.closest(".assign-checkbox");
      if (!cb || !root.contains(cb)) return;
      toggleAssign(cb.dataset.userId, cb.dataset.scoreId, cb.checked);
    });

    const roleEl = document.getElementById("user-role");
    const pw = document.getElementById("user-password");
    const hint = document.getElementById("user-password-hint");
    if (roleEl && pw && hint) {
      roleEl.addEventListener("change", () => {
        const mode = document.getElementById("user-dialog-user-id")?.value ? "edit" : "new";
        const user = mode === "edit" ? { role: roleEl.value, password: editUserPassword } : null;
        configurePasswordField(mode, user, pw, hint, roleEl);
        updateHandoutButton(mode, roleEl);
      });
    }

    document.querySelectorAll("[data-dialog-close]").forEach((el) => {
      el.addEventListener("click", closeDialog);
    });

    const handoutBtn = document.getElementById("user-handout-btn");
    if (handoutBtn) {
      handoutBtn.addEventListener("click", () => {
        const userId = document.getElementById("user-dialog-user-id")?.value;
        if (userId) openHandoutDialog(userId);
      });
    }

    document.querySelectorAll("[data-handout-close]").forEach((el) => {
      el.addEventListener("click", closeHandoutDialog);
    });

    document.querySelectorAll("#maestro-password-btn").forEach((btn) => {
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

    const handoutOverlay = document.getElementById("user-handout-overlay");
    if (handoutOverlay) {
      handoutOverlay.addEventListener("click", (e) => {
        if (e.target === handoutOverlay) closeHandoutDialog();
      });
    }

    const handoutPdfBtn = document.getElementById("user-handout-pdf-btn");
    if (handoutPdfBtn) {
      handoutPdfBtn.addEventListener("click", () => {
        if (!handoutUserId) return;
        window.open(scopedUrl(`/maestro/users/${handoutUserId}/handout.pdf`), "_blank", "noopener");
      });
    }

    const handoutPrintBtn = document.getElementById("user-handout-print-btn");
    if (handoutPrintBtn) {
      handoutPrintBtn.addEventListener("click", () => {
        window.print();
      });
    }

    const deleteBtn = document.getElementById("user-delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", () => {
        const userId = document.getElementById("user-dialog-user-id").value;
        if (!userId) return;
        const displayName = document.getElementById("user-display-name").value || "this user";
        deleteUser(userId, displayName);
      });
    }

    const overlay = document.getElementById("user-dialog-overlay");
    if (overlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeDialog();
      });
    }
  });
})();
