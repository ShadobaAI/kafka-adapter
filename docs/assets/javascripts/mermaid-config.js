(function () {
  let modal;
  let modalBody;
  let modalSvg;
  let modalScale = 1;
  let modalBaseWidth = 0;
  let modalReturnFocus;
  let renderer;
  let rendererLoad;
  let rendering = Promise.resolve();
  const definitions = new WeakMap();

  const loadRenderer = () => {
    if (!rendererLoad) {
      rendererLoad = import("https://cdn.jsdelivr.net/npm/mermaid@11.15.0/dist/mermaid.esm.min.mjs")
        .then((module) => { renderer = module.default; });
    }
    return rendererLoad;
  };

  // Render in ordinary DOM: Material's closed shadow roots cannot be exported
  // to the accessible zoom dialog. Diagram definitions stay in Markdown.
  const getDiagramSvg = (diagram) => diagram.querySelector("svg")
    || diagram.shadowRoot?.querySelector("svg");

  const initMermaid = () => {
    if (!renderer) {
      return false;
    }

    try {
      const style = getComputedStyle(document.body);
      const color = (name) => style.getPropertyValue(name).trim();
      renderer.initialize({
        startOnLoad: false,
        theme: "base",
        themeVariables: {
          darkMode: document.body.getAttribute("data-md-color-scheme") === "slate",
          primaryColor: color("--portal-soft"),
          primaryTextColor: color("--portal-text"),
          primaryBorderColor: color("--portal-accent"),
          lineColor: color("--portal-muted"),
          secondaryColor: color("--portal-surface"),
          tertiaryColor: color("--portal-bg"),
          fontFamily: "Segoe UI, sans-serif",
          fontSize: "15px",
        },
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
      if (modal.hidden) return;
      if (ev.key === "Escape") closeModal();
      if (ev.key === "Tab") {
        const controls = Array.from(modal.querySelectorAll("button"));
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (ev.shiftKey && document.activeElement === first) {
          ev.preventDefault();
          last.focus();
        } else if (!ev.shiftKey && document.activeElement === last) {
          ev.preventDefault();
          first.focus();
        }
      }
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

    [svg, ...svg.querySelectorAll("[id]")].filter((el) => el.id).forEach((el) => {
      const oldId = el.id;
      const newId = `${oldId}${suffix}`;
      idMap.set(oldId, newId);
      el.id = newId;
    });

    if (!idMap.size) return;

    svg.querySelectorAll("style").forEach((style) => {
      idMap.forEach((newId, oldId) => {
        const escaped = oldId.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
        style.textContent = style.textContent.replace(new RegExp("#" + escaped + "(?![a-zA-Z0-9_-])", "g"), "#" + newId);
      });
    });

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
    const svg = getDiagramSvg(diagram);
    if (!svg) return;
    modalReturnFocus = diagram;

    ensureModal();

    const size = getSvgSize(svg);
    modalSvg = svg.cloneNode(true);
    modalBaseWidth = size.width;
    modalScale = 1;

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
    modalReturnFocus?.focus();
    modalReturnFocus = null;
  };

  const attachZoom = () => {
    document.querySelectorAll(".portal-mermaid").forEach((el) => {

      const svg = getDiagramSvg(el);
      if (svg) {
        svg.style.setProperty("max-width", "none", "important");
        svg.style.width = `${Math.max(getSvgSize(svg).width, 600)}px`;
        svg.style.height = "auto";
      }
      if (!el.nextElementSibling?.classList.contains("portal-diagram-hint")) {
        const hint = document.createElement("p");
        hint.className = "portal-diagram-hint";
        hint.textContent = "Нажмите на схему, чтобы открыть её целиком и изменить масштаб.";
        el.after(hint);
      }

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
    const diagrams = Array.from(document.querySelectorAll(".portal-mermaid"));
    if (!diagrams.length) return;
    diagrams.forEach((diagram) => {
      if (!definitions.has(diagram)) definitions.set(diagram, diagram.textContent);
    });
    rendering = rendering.then(async () => {
      await loadRenderer();
      initMermaid();
      const scheme = document.body.getAttribute("data-md-color-scheme");
      for (const diagram of diagrams) {
        if (!diagram.isConnected || diagram.dataset.portalTheme === scheme) continue;
        diagram.textContent = definitions.get(diagram);
        diagram.removeAttribute("data-processed");
        await renderer.run({ nodes: [diagram] });
        diagram.dataset.portalTheme = scheme;
      }
      attachZoom();
    }).catch((error) => console.error("Mermaid render failed:", error));
  };

  const observeDiagrams = () => {
    const observer = new MutationObserver(() => attachZoom());
    observer.observe(document.body, { childList: true, subtree: true });
    const paletteObserver = new MutationObserver(() => {
      if (modal && !modal.hidden) closeModal();
      run();
    });
    paletteObserver.observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });
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
