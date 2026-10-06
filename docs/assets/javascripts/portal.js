(function () {
  const overlaySelector = ".portal-menu[open], .portal-faq-toc[open]";
  const initFaqSearch = () => {
    const article = document.querySelector(".portal-content-faq article");
    if (!article || article.querySelector(".portal-faq-search")) return;
    const questions = Array.from(article.querySelectorAll("h3")).map((heading) => {
      const elements = [heading];
      let next = heading.nextElementSibling;
      while (next && !next.matches("h2, h3, .md-source-file")) {
        elements.push(next);
        next = next.nextElementSibling;
      }
      return { heading, elements, text: elements.map((element) => element.textContent).join(" ").toLocaleLowerCase("ru") };
    });
    const groups = Array.from(article.querySelectorAll("h2")).map((heading) => {
      const members = [];
      let next = heading.nextElementSibling;
      while (next && !next.matches("h2")) {
        if (next.matches("h3")) members.push(next);
        next = next.nextElementSibling;
      }
      return { heading, members };
    });
    const form = document.createElement("form");
    form.className = "portal-faq-search";
    form.setAttribute("role", "search");
    form.setAttribute("aria-label", "Поиск по FAQ");
    form.innerHTML = '<label for="portal-faq-query">Поиск по этой странице</label><div class="portal-faq-search-controls"><input id="portal-faq-query" type="search" placeholder="Введите вопрос или слово из ответа" autocomplete="off"><button type="reset">Сбросить</button></div><p role="status" aria-live="polite" hidden></p>';
    article.querySelector("h1")?.after(form);
    const input = form.querySelector("input");
    const status = form.querySelector('[role="status"]');
    const filter = () => {
      const terms = input.value.trim().toLocaleLowerCase("ru").split(/\s+/).filter(Boolean);
      let count = 0;
      questions.forEach((question) => {
        const matches = terms.every((term) => question.text.includes(term));
        question.elements.forEach((element) => { element.hidden = !matches; });
        if (matches) count += 1;
      });
      groups.forEach((group) => { group.heading.hidden = !group.members.some((heading) => !heading.hidden); });
      status.hidden = terms.length === 0;
      status.textContent = count ? `Найдено вопросов: ${count} из ${questions.length}` : "Ничего не найдено. Попробуйте другое слово или сбросьте поиск.";
    };
    input.addEventListener("input", filter);
    form.addEventListener("submit", (event) => { event.preventDefault(); filter(); });
    form.addEventListener("reset", () => { input.value = ""; filter(); input.focus(); });
    // A table-of-contents link must also reach questions hidden by the filter.
    document.querySelector(".portal-faq-toc")?.addEventListener("click", (event) => {
      if (event.target.closest('a[href*="#"]')) { input.value = ""; filter(); }
    });
  };
  const openSearch = () => {
    const toggle = document.getElementById("__search");
    const input = document.querySelector('[data-md-component="search-query"]');
    if (!toggle || !input) return;
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change", { bubbles: true }));
    input.focus();
  };

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-portal-search]")) openSearch();
    document.querySelectorAll(overlaySelector).forEach((menu) => {
      if (!menu.contains(event.target) || event.target.closest("a")) menu.open = false;
    });
  });

  document.addEventListener("toggle", (event) => {
    const menu = event.target;
    if (!menu.matches?.(".portal-menu, .portal-faq-toc") || !menu.open) return;
    document.querySelectorAll(overlaySelector).forEach((other) => {
      if (other !== menu) other.open = false;
    });
  }, true);

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openSearch();
    }
    if (event.key === "Escape") {
      document.querySelectorAll(overlaySelector).forEach((menu) => {
        menu.open = false;
        menu.querySelector("summary")?.focus();
      });
    }
  });

  const onPage = () => {
    initFaqSearch();
    // Resolve navigation links against the deployment prefix and keep the
    // current page/section explicit for keyboard and screen-reader users.
    const header = document.querySelector(".portal-header");
    header?.querySelectorAll("a[href]").forEach((link) => {
      link.href = new URL(link.getAttribute("href"), document.baseURI).href;
    });
    const home = header?.querySelector(".portal-brand");
    const rootPath = home ? new URL(home.href).pathname : "/";
    const currentPath = window.location.pathname;
    const relativePath = currentPath.startsWith(rootPath) ? currentPath.slice(rootPath.length) : currentPath;
    header?.querySelectorAll(".portal-top-nav a").forEach((link) => {
      const destination = new URL(link.href).pathname;
      const current = currentPath === destination;
      const currentSection = link.dataset.portalPrefix && relativePath.startsWith(link.dataset.portalPrefix);
      if (current) link.setAttribute("aria-current", "page");
      else if (currentSection) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    header?.querySelectorAll(".portal-menu").forEach((menu) => {
      const current = menu.dataset.portalSection === "guides"
        ? relativePath.startsWith("user/") || relativePath.startsWith("overview/") || relativePath.startsWith("start/")
        : relativePath.startsWith("project/");
      menu.querySelector("summary")?.classList.toggle("portal-menu-active", current);
    });
    document.querySelectorAll(overlaySelector).forEach((menu) => { menu.open = false; });
    document.querySelectorAll(".md-typeset .portal-mermaid").forEach((diagram) => {
      if (diagram.nextElementSibling?.classList.contains("portal-diagram-hint")) return;
      const hint = document.createElement("p");
      hint.className = "portal-diagram-hint";
      hint.textContent = "Нажмите на схему, чтобы открыть её целиком и изменить масштаб.";
      diagram.after(hint);
    });
  };
  if (typeof document$ !== "undefined") document$.subscribe(onPage);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", onPage);
  else onPage();
})();
