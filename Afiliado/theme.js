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

  window.MegaTheme = {
    init() {
      applyTheme(getPreferredTheme());
      document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
          const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
          applyTheme(nextTheme);
        });
      });
    },
    applyTheme
  };

  applyTheme(getPreferredTheme());
})();
