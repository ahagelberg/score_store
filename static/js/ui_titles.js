(function () {
  "use strict";

  function titleFromNode(node) {
    const aria = node.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const text = node.textContent.replace(/\s+/g, " ").trim();
    if (text) return text;
    return "";
  }

  function applyTitles(root) {
    if (!(root instanceof Element)) return;
    const nodes = root.matches("a, button") ? [root] : [];
    root.querySelectorAll("a, button").forEach((node) => nodes.push(node));
    for (const node of nodes) {
      if (node.hasAttribute("title")) continue;
      const title = titleFromNode(node);
      if (title) node.title = title;
    }
  }

  function observeTitles() {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) applyTitles(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("DOMContentLoaded", () => {
    applyTitles(document.body);
    observeTitles();
  });

  window.UiTitles = { apply: applyTitles };
})();
