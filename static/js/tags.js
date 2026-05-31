(function () {
  "use strict";

  const COMMIT_KEYS = new Set(["Enter", ","]);

  function parseTags(raw) {
    if (!raw) return [];
    try {
      return JSON.parse(raw);
    } catch {
      return [];
    }
  }

  function syncHidden(field) {
    const hidden = field.querySelector('input[name="tags"]');
    const chips = field.querySelectorAll("[data-tag-chip]");
    const tags = Array.from(chips).map((c) => c.dataset.tagValue);
    hidden.value = JSON.stringify(tags);
  }

  function addChip(field, text) {
    const value = text.trim().toLowerCase();
    if (!value) return;
    const list = field.querySelector("[data-tag-list]");
    const existing = Array.from(list.querySelectorAll("[data-tag-chip]")).some(
      (c) => c.dataset.tagValue === value
    );
    if (existing) return;
    const chip = document.createElement("span");
    chip.className = "tag-chip";
    chip.dataset.tagChip = "";
    chip.dataset.tagValue = value;
    chip.appendChild(document.createTextNode(value + " "));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tag-chip-remove";
    btn.dataset.tagRemove = "";
    btn.textContent = "×";
    chip.appendChild(btn);
    list.appendChild(chip);
    syncHidden(field);
  }

  function initField(field) {
    if (field.dataset.tagInit) return;
    field.dataset.tagInit = "1";
    const hidden = field.querySelector('input[name="tags"]');
    parseTags(hidden.value).forEach((t) => addChip(field, t));
    const input = field.querySelector("[data-tag-input]");
    input.addEventListener("keydown", (e) => {
      if (COMMIT_KEYS.has(e.key)) {
        e.preventDefault();
        addChip(field, input.value);
        input.value = "";
      }
    });
    field.addEventListener("click", (e) => {
      if (e.target.closest("[data-tag-remove]")) {
        e.target.closest("[data-tag-chip]").remove();
        syncHidden(field);
      }
    });
  }

  function initAll(root) {
    (root || document).querySelectorAll("[data-tag-field]").forEach(initField);
  }

  window.TagInput = { initAll, initField, addChip, syncHidden, parseTags };
  document.addEventListener("DOMContentLoaded", () => initAll(document));
})();
