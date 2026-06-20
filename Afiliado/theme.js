(function () {
  const STORAGE_KEY = "mega_descontos_theme";

  function getPreferredTheme() {
    const savedTheme = localStorage.getItem(STORAGE_KEY);
    if (savedTheme === "dark" || savedTheme === "light") {
      return savedTheme;
    }

    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEY, theme);
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.textContent = theme === "dark" ? "Tema claro" : "Tema escuro";
      button.setAttribute("aria-label", theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro");
    });
  }

  function ensureBrandIcon() {
    const brandIconPath = "assets/mega-descontos-icon.png?v=20260620-3";
    const faviconPath = "favicon.ico?v=20260620-3";

    document.querySelectorAll(".brand-icon").forEach((oldIcon) => {
      const icon = document.createElement("img");
      icon.src = brandIconPath;
      icon.alt = "";
      icon.setAttribute("aria-hidden", "true");
      icon.style.width = "44px";
      icon.style.height = "44px";
      icon.style.display = "block";
      icon.style.flex = "0 0 44px";
      icon.style.objectFit = "contain";
      oldIcon.replaceWith(icon);
    });

    document.querySelectorAll("link[rel='icon'], link[rel='shortcut icon']").forEach((favicon) => {
      favicon.rel = "icon";
      favicon.type = "image/x-icon";
      favicon.href = faviconPath;
    });

    if (!document.querySelector("link[rel='icon']")) {
      const favicon = document.createElement("link");
      favicon.rel = "icon";
      favicon.type = "image/x-icon";
      favicon.href = faviconPath;
      document.head.appendChild(favicon);
    }

    if (!document.querySelector("link[rel='apple-touch-icon']")) {
      const touchIcon = document.createElement("link");
      touchIcon.rel = "apple-touch-icon";
      touchIcon.href = brandIconPath;
      document.head.appendChild(touchIcon);
    }
  }

  window.MegaTheme = {
    init() {
      applyTheme(getPreferredTheme());
      ensureBrandIcon();
      document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
          const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
          applyTheme(nextTheme);
        });
      });
    },
    applyTheme,
    ensureBrandIcon
  };

  applyTheme(getPreferredTheme());
})();
