(function () {
  "use strict";

  const PRINT_MEDIA_PDF = "pdf";
  const PRINT_MEDIA_IMAGE = "image";
  const PRINT_PDF_RENDER_SCALE = 2;
  const PRINT_JPEG_QUALITY = 0.92;
  const PRINT_WINDOW_TITLE = "Print";

  function pdfWorkerSrc() {
    const overlay = document.getElementById("score-viewer-overlay");
    return overlay?.dataset.pdfWorker || "";
  }

  function ensurePdfJs() {
    const lib = window.pdfjsLib;
    if (!lib) return null;
    const workerSrc = pdfWorkerSrc();
    if (workerSrc) {
      lib.GlobalWorkerOptions.workerSrc = workerSrc;
    }
    return lib;
  }

  async function loadPdfForPrint(url) {
    const lib = ensurePdfJs();
    if (!lib) throw new Error("PDF.js unavailable");
    return lib.getDocument({ url, withCredentials: true }).promise;
  }

  async function renderPageDataUrl(pdf, pageNum) {
    const page = await pdf.getPage(pageNum);
    const viewport = page.getViewport({ scale: PRINT_PDF_RENDER_SCALE });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
    return canvas.toDataURL("image/jpeg", PRINT_JPEG_QUALITY);
  }

  function writePrintDocument(doc) {
    doc.open();
    doc.write(`<!DOCTYPE html><html><head><title>${PRINT_WINDOW_TITLE}</title><style>
      body { margin: 0; }
      .print-loading { padding: 24px; font: 14px sans-serif; color: #444; }
      img { display: block; width: 100%; height: auto; page-break-after: always; }
      img:last-child { page-break-after: auto; }
    </style></head><body><p class="print-loading">Preparing print…</p></body></html>`);
    doc.close();
  }

  function openPrintWindow() {
    const printWin = window.open("", "_blank");
    if (!printWin) {
      window.showToast?.("Pop-up blocked — allow pop-ups to print", true);
      return null;
    }
    writePrintDocument(printWin.document);
    return printWin;
  }

  async function printPdfIntoWindow(printWin, url) {
    const pdf = await loadPdfForPrint(url);
    const doc = printWin.document;
    doc.body.replaceChildren();
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum += 1) {
      const img = doc.createElement("img");
      img.alt = `Page ${pageNum}`;
      img.src = await renderPageDataUrl(pdf, pageNum);
      doc.body.appendChild(img);
    }
    pdf.destroy?.();
    printWin.focus();
    printWin.print();
    printWin.addEventListener("afterprint", () => printWin.close(), { once: true });
  }

  function printPdfUrl(url) {
    const printWin = openPrintWindow();
    if (!printWin) return;
    printPdfIntoWindow(printWin, url).catch(() => {
      printWin.close();
      window.showToast?.("Print failed", true);
    });
  }

  function printImageUrl(url) {
    const printWin = openPrintWindow();
    if (!printWin) return;
    const doc = printWin.document;
    doc.body.replaceChildren();
    const img = doc.createElement("img");
    img.src = url;
    img.addEventListener("load", () => {
      printWin.focus();
      printWin.print();
      printWin.addEventListener("afterprint", () => printWin.close(), { once: true });
    }, { once: true });
    img.addEventListener("error", () => {
      printWin.close();
      window.showToast?.("Print failed", true);
    }, { once: true });
    doc.body.appendChild(img);
  }

  function printFile(url, media) {
    if (!url) {
      window.showToast?.("Nothing to print", true);
      return;
    }
    if (media === PRINT_MEDIA_PDF) {
      printPdfUrl(url);
      return;
    }
    if (media === PRINT_MEDIA_IMAGE) {
      printImageUrl(url);
      return;
    }
    window.showToast?.("Cannot print this file type", true);
  }

  function bindPrintButtons(root) {
    root.querySelectorAll(".score-print-btn[data-print-url]").forEach((btn) => {
      if (btn.dataset.printBound) return;
      btn.dataset.printBound = "true";
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        printFile(btn.dataset.printUrl, btn.dataset.printMedia || PRINT_MEDIA_PDF);
      });
    });
  }

  window.ScorePrint = {
    printFile,
    bindPrintButtons,
    PRINT_MEDIA_PDF,
    PRINT_MEDIA_IMAGE,
  };

  document.addEventListener("DOMContentLoaded", () => bindPrintButtons(document));
})();
