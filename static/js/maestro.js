(function () {
  "use strict";

  const MAESTRO_ROLE = "maestro";
  let editUserPassword = "";

  function configurePasswordField(mode, user, pw, hint, roleEl) {
    const role = roleEl ? roleEl.value : (user?.role || "");
    const isMaestro = role === MAESTRO_ROLE;
    if (mode === "edit" && user) {
      pw.required = false;
      if (isMaestro) {
        pw.value = "";
        hint.textContent = "Admin passwords are not stored for viewing";
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
    overlay.classList.remove("hidden");
  }

  function closeDialog() {
    const overlay = document.getElementById("user-dialog-overlay");
    if (overlay) overlay.classList.add("hidden");
  }

  async function toggleAssign(userId, scoreId, assign) {
    const res = await fetch("/maestro/assign", {
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
      });
    }

    document.querySelectorAll("[data-dialog-close]").forEach((el) => {
      el.addEventListener("click", closeDialog);
    });

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

    document.querySelectorAll(".mobile-share-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const panel = document.querySelector(`[data-share-panel="${btn.dataset.scoreId}"]`);
        if (panel) panel.classList.toggle("hidden");
      });
    });

    document.querySelectorAll(".assign-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        toggleAssign(cb.dataset.userId, cb.dataset.scoreId, cb.checked);
      });
    });
  });
})();
