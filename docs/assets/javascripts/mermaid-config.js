(() => {
  const diagrams = Array.from(document.querySelectorAll("pre.portal-mermaid"), (source) => {
    const figure = document.createElement("figure");
    figure.className = "portal-mermaid";
    const preview = document.createElement("div");
    preview.className = "portal-mermaid__preview";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "portal-mermaid__zoom";
    button.textContent = "Увеличить схему";
    button.hidden = true;

    const definition = source.textContent.trim();
    figure.append(preview, button);
    source.replaceWith(figure);
    return { preview, button, definition };
  });
  if (!diagrams.length) return;

  const dialog = document.createElement("dialog");
  dialog.className = "mermaid-modal";
  dialog.setAttribute("aria-label", "Просмотр схемы");
  dialog.innerHTML = [
    '<div class="mermaid-modal__bar">',
    '  <button type="button" data-zoom-out aria-label="Уменьшить">−</button>',
    '  <button type="button" data-zoom-fit>Вписать</button>',
    '  <button type="button" data-zoom-in aria-label="Увеличить">+</button>',
    '  <button type="button" data-zoom-close autofocus>Закрыть</button>',
    '</div>',
    '<div class="mermaid-modal__body"></div>',
  ].join("");
  const dialogBody = dialog.querySelector(".mermaid-modal__body");
  document.body.append(dialog);

  let active;
  let scale;
  const setScale = (factor) => {
    scale = Math.min(Math.max(factor, 0.2), 3);
    active.svg.style.width = Math.round(active.width * scale) + "px";
  };
  const fit = () => {
    const gutter = 32;
    const barHeight = dialog.querySelector(".mermaid-modal__bar").offsetHeight;
    const width = dialogBody.clientWidth - gutter;
    const height = window.innerHeight - barHeight - 2 * gutter;
    setScale(Math.min(width / active.width, height / active.height, 1.35));
    dialogBody.scrollTo(0, 0);
  };
  const close = () => {
    if (!active) return;
    const { preview, button, svg } = active;
    svg.style.removeProperty("width");
    preview.append(svg);
    preview.style.removeProperty("min-height");
    active = undefined;
    dialog.close();
    button.focus();
  };
  const open = ({ preview, button }) => {
    const svg = preview.querySelector("svg");
    const [, , width, height] = svg.getAttribute("viewBox").trim().split(/\s+/).map(Number);
    preview.style.minHeight = preview.offsetHeight + "px";
    active = { preview, button, svg, width, height };
    dialogBody.append(svg);
    dialog.showModal();
    fit();
  };

  dialog.querySelector("[data-zoom-out]").addEventListener("click", () => setScale(scale / 1.25));
  dialog.querySelector("[data-zoom-in]").addEventListener("click", () => setScale(scale * 1.25));
  dialog.querySelector("[data-zoom-fit]").addEventListener("click", fit);
  dialog.querySelector("[data-zoom-close]").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  diagrams.forEach((diagram) => diagram.button.addEventListener("click", () => open(diagram)));

  const showError = ({ preview, button }) => {
    const message = document.createElement("p");
    message.textContent = "Схема недоступна. Этапы описаны на этой странице.";
    preview.replaceChildren(message);
    button.hidden = true;
  };

  const renderer = import("https://cdn.jsdelivr.net/npm/mermaid@11.15.0/dist/mermaid.esm.min.mjs");
  let sequence = 0;
  let pending = Promise.resolve();

  const renderDiagrams = () => {
    pending = pending.then(async () => {
      const { default: mermaid } = await renderer;
      const style = getComputedStyle(document.body);
      const color = (name) => style.getPropertyValue(name).trim();
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "base",
        themeVariables: {
          darkMode: document.body.dataset.mdColorScheme === "slate",
          primaryColor: color("--portal-soft"),
          primaryTextColor: color("--portal-text"),
          primaryBorderColor: color("--portal-accent"),
          lineColor: color("--portal-muted"),
          edgeLabelBackground: color("--portal-surface"),
          fontFamily: "Segoe UI, sans-serif",
          fontSize: "16px",
        },
        flowchart: {
          useMaxWidth: false,
          nodeSpacing: 24,
          rankSpacing: 30,
        },
      });

      for (const diagram of diagrams) {
        try {
          const { svg } = await mermaid.render("portal-diagram-" + ++sequence, diagram.definition);
          if (active?.preview === diagram.preview) close();
          diagram.preview.innerHTML = svg;
          diagram.button.hidden = false;
        } catch (error) {
          showError(diagram);
          console.error("Mermaid diagram could not be rendered", error);
        }
      }
    }).catch((error) => {
      diagrams.forEach(showError);
      console.error("Mermaid could not be loaded", error);
    });
  };

  new MutationObserver(renderDiagrams).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-md-color-scheme"],
  });
  renderDiagrams();
})();
