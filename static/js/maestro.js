(function () {
  "use strict";

  function openDialog(mode, user) {
    const overlay = document.getElementById("user-dialog-overlay");
    const form = document.getElementById("user-dialog-form");
    const title = document.getElementById("user-dialog-title");
    const pw = document.getElementById("user-password");
    const hint = document.getElementById("user-password-hint");
    if (!overlay || !form) return;
    if (mode === "edit" && user) {
      title.textContent = "Edit user";
      form.action = `/maestro/users/${user.id}/edit`;
      document.getElementById("user-dialog-user-id").value = user.id;
      document.getElementById("user-display-name").value = user.displayName;
      document.getElementById("user-username").value = user.username;
      document.getElementById("user-role").value = user.role;
      pw.required = false;
      hint.textContent = "Leave blank to keep current password";
    } else {
      title.textContent = "Add user";
      form.action = "/maestro/users/new";
      form.reset();
      pw.required = true;
      hint.textContent = "Required for new users";
    }
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
        });
      });
    });

    document.querySelectorAll("[data-dialog-close]").forEach((el) => {
      el.addEventListener("click", closeDialog);
    });

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
