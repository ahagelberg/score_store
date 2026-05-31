(function () {
  "use strict";

  function showToast(message, isError) {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " toast-error" : "");
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  window.showToast = showToast;

  function promptYoutube() {
    const url = window.prompt("YouTube URL");
    if (!url) return null;
    const name = window.prompt("Display name", "YouTube") || "YouTube";
    return { url, name };
  }

  window.UploadHelpers = {
    promptYoutube,
    isPdfFile(file) {
      return file && (file.type === "application/pdf" || /\.pdf$/i.test(file.name));
    },
    basename(name) {
      return name.replace(/\.[^/.]+$/, "") || "File";
    },
  };
})();
