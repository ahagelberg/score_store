(function () {
  "use strict";

  const MAESTRO_ROLE = "maestro";
  let editUserPassword = "";
  let handoutUserId = "";

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
      form.action = `/maestro/users/${user.id}/edit`;
      document.getElementById("user-dialog-user-id").value = user.id;
      document.getElementById("user-display-name").value = user.displayName;
      document.getElementById("user-username").value = user.username;
      if (roleEl) roleEl.value = user.role;
      editUserPassword = user.password || "";
      if (deleteBtn) deleteBtn.classList.remove("hidden");
    } else {
      title.textContent = "Add user";
      form.action = "/maestro/users/new";
      form.reset();
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
      const res = await fetch(`/maestro/users/${userId}/handout`);
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

  document.addEventListener("DOMContentLoaded", () => {
    const addBtn = document.getElementById("add-user-btn");
    if (addBtn) addBtn.addEventListener("click", () => openDialog("new"));

    document.querySelectorAll(".user-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        openDialog("edit", {
          id: btn.dataset.userId,
          displayName: btn.dataset.displayName,
          username: btn.dataset.username,
          role: btn.dataset.role,
          password: btn.dataset.password || "",
        });
      });
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
        window.open(`/maestro/users/${handoutUserId}/handout.pdf`, "_blank", "noopener");
      });
    }

    const deleteBtn = document.getElementById("user-delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", () => {
        const userId = document.getElementById("user-dialog-user-id").value;
        if (!userId) return;
        const displayName = document.getElementById("user-display-name").value || "this user";
        const msg =
          `Delete "${displayName}"?\n\nTheir library and assignments will be removed. Scores they own will stay in the global library under system ownership.`;
        if (!window.confirm(msg)) return;
        const form = document.createElement("form");
        form.method = "POST";
        form.action = `/maestro/users/${userId}/delete`;
        const csrfInput = document.createElement("input");
        csrfInput.type = "hidden";
        csrfInput.name = "csrf_token";
        csrfInput.value = Csrf.token();
        form.appendChild(csrfInput);
        document.body.appendChild(form);
        form.submit();
      });
    }

    const overlay = document.getElementById("user-dialog-overlay");
    if (overlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeDialog();
      });
    }

    document.querySelectorAll(".assign-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        toggleAssign(cb.dataset.userId, cb.dataset.scoreId, cb.checked);
      });
    });
  });
})();
