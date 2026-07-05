(function () {
  let modal;
  let modalBody;
  let modalSvg;
  let modalScale = 1;
  let modalBaseWidth = 0;

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

  const ensureModal = () => {
    if (modal) return modal;

    modal = document.createElement("div");
    modal.className = "mermaid-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", "Просмотр схемы");
    modal.hidden = true;
    modal.innerHTML = [
      '<div class="mermaid-modal__backdrop" data-mermaid-close></div>',
      '<div class="mermaid-modal__content">',
      '  <div class="mermaid-modal__bar">',
      '    <button class="mermaid-modal__control" type="button" data-mermaid-zoom-out aria-label="Уменьшить">-</button>',
      '    <button class="mermaid-modal__control" type="button" data-mermaid-zoom-reset aria-label="Исходный размер">1:1</button>',
      '    <button class="mermaid-modal__control" type="button" data-mermaid-zoom-in aria-label="Увеличить">+</button>',
      '    <button class="mermaid-modal__close" type="button" data-mermaid-close aria-label="Закрыть">x</button>',
      '  </div>',
      '  <div class="mermaid-modal__body"></div>',
      '</div>',
    ].join("");

    modalBody = modal.querySelector(".mermaid-modal__body");
    document.body.appendChild(modal);

    modal.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-mermaid-close]")) {
        closeModal();
      }
      if (ev.target.closest("[data-mermaid-zoom-out]")) {
        setModalScale(modalScale - 0.25);
      }
      if (ev.target.closest("[data-mermaid-zoom-reset]")) {
        setModalScale(1);
      }
      if (ev.target.closest("[data-mermaid-zoom-in]")) {
        setModalScale(modalScale + 0.25);
      }
    });

    document.addEventListener("keydown", (ev) => {
      if (modal.hidden || ev.key !== "Escape") return;
      closeModal();
    });

    return modal;
  };

  const getSvgSize = (svg) => {
    const viewBox = svg.getAttribute("viewBox");
    if (viewBox) {
      const parts = viewBox.split(/\s+/).map(Number);
      if (parts.length === 4 && parts[2] > 0 && parts[3] > 0) {
        return { width: parts[2], height: parts[3] };
      }
    }

    const rect = svg.getBoundingClientRect();
    return {
      width: Math.max(rect.width, 600),
      height: Math.max(rect.height, 400),
    };
  };

  const setModalScale = (scale) => {
    if (!modalSvg || !modalBaseWidth) return;

    modalScale = Math.min(Math.max(scale, 0.5), 3);
    modalSvg.style.width = `${Math.round(modalBaseWidth * modalScale)}px`;
    modalSvg.style.height = "auto";
  };

  const uniquifySvgIds = (svg) => {
    const suffix = `-modal-${Date.now().toString(36)}`;
    const idMap = new Map();

    svg.querySelectorAll("[id]").forEach((el) => {
      const oldId = el.id;
      const newId = `${oldId}${suffix}`;
      idMap.set(oldId, newId);
      el.id = newId;
    });

    if (!idMap.size) return;

    svg.querySelectorAll("*").forEach((el) => {
      Array.from(el.attributes).forEach((attr) => {
        let value = attr.value;
        idMap.forEach((newId, oldId) => {
          value = value
            .replaceAll(`url(#${oldId})`, `url(#${newId})`)
            .replaceAll(`"#${oldId}"`, `"#${newId}"`)
            .replaceAll(`'#${oldId}'`, `'#${newId}'`);
        });
        if (value !== attr.value) {
          el.setAttribute(attr.name, value);
        }
      });
    });
  };

  const openModal = (diagram) => {
    const svg = diagram.querySelector("svg");
    if (!svg) return;

    ensureModal();

    const size = getSvgSize(svg);
    modalSvg = svg.cloneNode(true);
    modalBaseWidth = size.width;
    modalScale = 1;

    modalSvg.removeAttribute("id");
    modalSvg.removeAttribute("style");
    modalSvg.setAttribute("width", Math.round(size.width));
    modalSvg.setAttribute("height", Math.round(size.height));
    uniquifySvgIds(modalSvg);

    modalBody.replaceChildren(modalSvg);
    setModalScale(1);

    modal.hidden = false;
    document.body.classList.add("mermaid-modal-open");
    modal.querySelector(".mermaid-modal__close").focus();
  };

  const closeModal = () => {
    if (!modal) return;

    modal.hidden = true;
    modalBody.replaceChildren();
    modalSvg = null;
    modalBaseWidth = 0;
    document.body.classList.remove("mermaid-modal-open");
  };

  const attachZoom = () => {
    document.querySelectorAll(".mermaid").forEach((el) => {
      if (el.dataset.zoomBound) return;

      el.dataset.zoomBound = "1";
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", "Открыть схему в модальном окне");
      el.addEventListener("click", (ev) => {
        if (ev.target.closest("a")) return;
        openModal(el);
      });
      el.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" && ev.key !== " ") return;
        ev.preventDefault();
        openModal(el);
      });
    });
  };

  const run = () => {
    if (!initMermaid()) {
      setTimeout(run, 200);
      return;
    }

    attachZoom();
    setTimeout(attachZoom, 300);
  };

  const observeDiagrams = () => {
    const observer = new MutationObserver(() => attachZoom());
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (typeof document$ !== "undefined") {
    document$.subscribe(() => run());
  } else {
    document.addEventListener("DOMContentLoaded", run);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", observeDiagrams);
  } else {
    observeDiagrams();
  }
})();
