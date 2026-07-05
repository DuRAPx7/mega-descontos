(function () {
  const STORAGE_KEY = "mega_descontos_theme";

  function getPreferredTheme() {
    const savedTheme = localStorage.getItem(STORAGE_KEY);
    if (savedTheme === "dark" || savedTheme === "light") {
      return savedTheme;
    }

    return "dark";
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
    const brandIconPath = "assets/mega-descontos-icon.png?v=20260620-6";
    const faviconPath = "favicon.ico?v=20260620-3";

    function createBrandFallback() {
      const fallback = document.createElement("span");
      fallback.className = "brand-logo-fallback";
      fallback.textContent = "MD";
      fallback.setAttribute("aria-hidden", "true");
      fallback.style.width = "46px";
      fallback.style.height = "46px";
      fallback.style.display = "grid";
      fallback.style.placeItems = "center";
      fallback.style.flex = "0 0 46px";
      fallback.style.borderRadius = "12px";
      fallback.style.background = "linear-gradient(135deg, #111827, #0b1117)";
      fallback.style.color = "#22c55e";
      fallback.style.fontWeight = "900";
      fallback.style.fontSize = "1rem";
      fallback.style.letterSpacing = "0";
      fallback.style.border = "1px solid rgba(34, 197, 94, 0.28)";
      return fallback;
    }

    function polishBrandImage(icon) {
      icon.src = brandIconPath;
      icon.classList.add("brand-logo");
      icon.alt = "";
      icon.setAttribute("aria-hidden", "true");
      icon.style.width = "46px";
      icon.style.height = "46px";
      icon.style.display = "block";
      icon.style.flex = "0 0 46px";
      icon.style.objectFit = "contain";
      icon.style.borderRadius = "12px";
      icon.style.background = "transparent";
      icon.style.padding = "0";
      icon.style.boxShadow = "none";
      icon.onerror = () => {
        icon.replaceWith(createBrandFallback());
      };
    }

    document.querySelectorAll(".brand-icon").forEach((oldIcon) => {
      const icon = document.createElement("img");
      polishBrandImage(icon);
      oldIcon.replaceWith(icon);
    });

    document.querySelectorAll(".brand-logo, .brand > img").forEach((icon) => {
      polishBrandImage(icon);
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
