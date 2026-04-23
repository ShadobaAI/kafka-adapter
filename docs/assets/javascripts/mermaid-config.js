// Mermaid configuration for MkDocs Material.
// Material loads Mermaid when it finds a .mermaid element; we override the
// defaults so diagrams render at their native size (not squeezed into
// useMaxWidth).  A click toggles a fullscreen "zoomed" view.

(function () {
  const initMermaid = () => {
    if (typeof window.mermaid === "undefined") {
      return false;
    }
    try {
      window.mermaid.initialize({
        startOnLoad: false,
        theme: document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "default",
        securityLevel: "loose",
        flowchart: {
          useMaxWidth: false,
          htmlLabels: true,
          curve: "basis",
        },
        sequence: { useMaxWidth: false },
        gantt: { useMaxWidth: false },
        class: { useMaxWidth: false },
        state: { useMaxWidth: false },
      });
    } catch (e) {
      console.warn("Mermaid initialize failed:", e);
    }
    return true;
  };

  const attachZoom = () => {
    document.querySelectorAll(".mermaid").forEach((el) => {
      if (el.dataset.zoomBound) return;
      el.dataset.zoomBound = "1";
      el.addEventListener("click", (ev) => {
        // ignore clicks on links inside the diagram
        if (ev.target.closest("a")) return;
        el.classList.toggle("mermaid-zoomed");
      });
    });
  };

  // MkDocs Material uses "instant" navigation via a document$ observable
  // (RxJS).  Re-run initialisation on every navigation event.
  const run = () => {
    if (!initMermaid()) {
      // Mermaid may not have loaded yet — retry once scripts finish.
      setTimeout(run, 200);
      return;
    }
    attachZoom();
  };

  if (typeof document$ !== "undefined") {
    document$.subscribe(() => run());
  } else {
    document.addEventListener("DOMContentLoaded", run);
  }
})();
