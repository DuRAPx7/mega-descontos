const OFFERS_STORAGE_KEY = "mega_descontos_offers";
const FAVORITES_STORAGE_KEY = "mega_descontos_favorites";
const API_OFFERS_URL = "/api/offers";

let offers = [...(window.DEFAULT_OFFERS || [])];
let favorites = loadFavorites();
let searchTerm = "";
let selectedStore = "Todas";
let selectedCategory = "Todas";
let selectedSort = "discount";
let showFavoritesOnly = false;
let currentPage = 1;
const OFFERS_PER_PAGE = 25;

const categories = window.MEGA_CATEGORIES || [];
const moneyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL"
});

const offerGrid = document.querySelector("#offerGrid");
const categoryGrid = document.querySelector("#categoryGrid");
const emptyState = document.querySelector("#emptyState");
const searchForm = document.querySelector("#searchForm");
const searchInput = document.querySelector("#searchInput");
const storeFilter = document.querySelector("#storeFilter");
const categoryFilter = document.querySelector("#categoryFilter");
const sortFilter = document.querySelector("#sortFilter");
const resultsCount = document.querySelector("#resultsCount");
const clearFilters = document.querySelector("#clearFilters");
const favoriteFilterLink = document.querySelector("#favoriteFilterLink");
const offerPagination = document.querySelector("#offerPagination");

function loadFavorites() {
  const savedFavorites = localStorage.getItem(FAVORITES_STORAGE_KEY);
  if (!savedFavorites) {
    return [];
  }

  try {
    return JSON.parse(savedFavorites).map(String);
  } catch {
    return [];
  }
}

function isHttpPage() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

function loadLocalOffersFallback() {
  const savedOffers = localStorage.getItem(OFFERS_STORAGE_KEY);
  if (!savedOffers) {
    return [...(window.DEFAULT_OFFERS || [])];
  }

  try {
    return JSON.parse(savedOffers);
  } catch {
    return [...(window.DEFAULT_OFFERS || [])];
  }
}

function loadOffersFromApi() {
  if (!isHttpPage()) {
    offers = loadLocalOffersFallback();
    renderOffers();
    return;
  }

  fetch(API_OFFERS_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("API indisponivel");
      }
      return response.json();
    })
    .then((apiOffers) => {
      offers = Array.isArray(apiOffers) ? apiOffers : apiOffers.offers || loadLocalOffersFallback();
      renderOffers();
    })
    .catch(() => {
      offers = loadLocalOffersFallback();
      renderOffers();
    });
}

function saveFavorites() {
  localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favorites));
}

function getQueryParams() {
  return new URLSearchParams(window.location.search);
}

function applyInitialFilters() {
  const params = getQueryParams();
  selectedStore = params.get("loja") || selectedStore;
  selectedCategory = params.get("categoria") || selectedCategory;
  searchTerm = params.get("busca") || searchTerm;

  if (storeFilter.querySelector(`option[value="${selectedStore}"]`)) {
    storeFilter.value = selectedStore;
  }
  if (categoryFilter.querySelector(`option[value="${selectedCategory}"]`)) {
    categoryFilter.value = selectedCategory;
  }
  searchInput.value = searchTerm;
}

function renderCategories() {
  categoryGrid.innerHTML = categories
    .map((category) => `
      <button class="category-card" data-category="${category.name}">
        <span class="category-icon">${category.icon}</span>
        <strong>${category.name}</strong>
      </button>
    `)
    .join("");

  document.querySelectorAll(".category-card").forEach((button) => {
    button.addEventListener("click", () => {
      selectedCategory = button.dataset.category === "Mais categorias" ? "Todas" : button.dataset.category;
      categoryFilter.value = selectedCategory;
      currentPage = 1;
      renderOffers();
      document.querySelector("#ofertas").scrollIntoView({ behavior: "smooth" });
    });
  });
}

function getFilteredOffers() {
  const normalizedSearch = searchTerm.trim().toLowerCase();

  const filteredOffers = offers.filter((offer) => {
    const matchesFavorite = !showFavoritesOnly || favorites.includes(offer.id);
    const matchesStore = selectedStore === "Todas" || offer.store === selectedStore;
    const matchesCategory = selectedCategory === "Todas" || offer.category === selectedCategory;
    const matchesSearch =
      !normalizedSearch ||
      `${offer.title} ${offer.store} ${offer.category}`.toLowerCase().includes(normalizedSearch);

    return matchesFavorite && matchesStore && matchesCategory && matchesSearch;
  });

  return filteredOffers.sort((first, second) => {
    if (selectedSort === "price-low") {
      return first.currentPrice - second.currentPrice;
    }
    if (selectedSort === "price-high") {
      return second.currentPrice - first.currentPrice;
    }
    return second.discount - first.discount;
  });
}

function toggleFavorite(offerId) {
  offerId = String(offerId);
  if (favorites.includes(offerId)) {
    favorites = favorites.filter((id) => id !== offerId);
  } else {
    favorites = [...favorites, offerId];
  }

  saveFavorites();
  renderOffers();
}

function renderPagination(totalOffers) {
  const totalPages = Math.max(1, Math.ceil(totalOffers / OFFERS_PER_PAGE));
  currentPage = Math.min(currentPage, totalPages);

  if (totalOffers <= OFFERS_PER_PAGE) {
    offerPagination.innerHTML = "";
    offerPagination.hidden = true;
    return;
  }

  const startPage = Math.max(1, currentPage - 2);
  const endPage = Math.min(totalPages, currentPage + 2);
  const pageButtons = [];
  for (let page = startPage; page <= endPage; page += 1) {
    pageButtons.push(
      `<button type="button" data-page="${page}" class="${page === currentPage ? "active" : ""}" aria-current="${page === currentPage ? "page" : "false"}">${page}</button>`
    );
  }

  offerPagination.hidden = false;
  offerPagination.innerHTML = `
    <button type="button" data-page="${currentPage - 1}" ${currentPage === 1 ? "disabled" : ""}>Anterior</button>
    ${startPage > 1 ? `<button type="button" data-page="1">1</button><span>...</span>` : ""}
    ${pageButtons.join("")}
    ${endPage < totalPages ? `<span>...</span><button type="button" data-page="${totalPages}">${totalPages}</button>` : ""}
    <button type="button" data-page="${currentPage + 1}" ${currentPage === totalPages ? "disabled" : ""}>Proxima</button>
  `;

  offerPagination.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      currentPage = Number(button.dataset.page);
      renderOffers();
      document.querySelector("#ofertas").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderOffers() {
  const filteredOffers = getFilteredOffers();
  const totalPages = Math.max(1, Math.ceil(filteredOffers.length / OFFERS_PER_PAGE));
  currentPage = Math.min(currentPage, totalPages);
  const pageStart = (currentPage - 1) * OFFERS_PER_PAGE;
  const visibleOffers = filteredOffers.slice(pageStart, pageStart + OFFERS_PER_PAGE);

  offerGrid.innerHTML = visibleOffers
    .map((offer) => {
      const isFavorite = favorites.includes(String(offer.id));
      const detailUrl = `produto.html?id=${encodeURIComponent(offer.id)}`;
      return `
        <article class="offer-card">
          <span class="discount-pill">-${offer.discount}%</span>
          <button class="favorite-button ${isFavorite ? "active" : ""}" type="button" data-offer-id="${offer.id}" aria-label="Adicionar aos favoritos">
            ${isFavorite ? "Favorito" : "Salvar"}
          </button>
          <a class="offer-image-link" href="${detailUrl}">
            <img src="${offer.image}" alt="${offer.title}" loading="lazy" onerror="this.style.visibility='hidden'">
          </a>
          <div class="offer-body">
            <h3><a class="offer-title-link" href="${detailUrl}">${offer.title}</a></h3>
            <span class="store-name">${offer.store}</span>
            <div>
              <span class="current-price">${moneyFormatter.format(offer.currentPrice)}</span>
              <span class="old-price">${moneyFormatter.format(offer.oldPrice)}</span>
            </div>
            <a href="${detailUrl}">Ver detalhes</a>
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll(".favorite-button").forEach((button) => {
    button.addEventListener("click", () => {
      toggleFavorite(button.dataset.offerId);
    });
  });

  resultsCount.textContent = `${filteredOffers.length} ${
    filteredOffers.length === 1 ? "oferta" : "ofertas"
  }${showFavoritesOnly ? " favoritas" : ""}${filteredOffers.length ? ` / pagina ${currentPage} de ${totalPages}` : ""}`;
  emptyState.textContent = offers.length
    ? "Nenhuma oferta encontrada com esses filtros."
    : "Ainda nao ha ofertas reais publicadas. O bot continua monitorando as lojas.";
  emptyState.hidden = filteredOffers.length > 0;
  renderPagination(filteredOffers.length);
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  searchTerm = searchInput.value;
  currentPage = 1;
  renderOffers();
  document.querySelector("#ofertas").scrollIntoView({ behavior: "smooth" });
});

searchInput.addEventListener("input", () => {
  searchTerm = searchInput.value;
  currentPage = 1;
  renderOffers();
});

storeFilter.addEventListener("change", () => {
  selectedStore = storeFilter.value;
  showFavoritesOnly = false;
  currentPage = 1;
  renderOffers();
});

categoryFilter.addEventListener("change", () => {
  selectedCategory = categoryFilter.value;
  showFavoritesOnly = false;
  currentPage = 1;
  renderOffers();
});

sortFilter.addEventListener("change", () => {
  selectedSort = sortFilter.value;
  currentPage = 1;
  renderOffers();
});

clearFilters.addEventListener("click", () => {
  searchTerm = "";
  selectedStore = "Todas";
  selectedCategory = "Todas";
  selectedSort = "discount";
  showFavoritesOnly = false;
  currentPage = 1;
  searchInput.value = "";
  storeFilter.value = selectedStore;
  categoryFilter.value = selectedCategory;
  sortFilter.value = selectedSort;
  renderOffers();
});

favoriteFilterLink.addEventListener("click", () => {
  showFavoritesOnly = true;
  selectedStore = "Todas";
  selectedCategory = "Todas";
  storeFilter.value = selectedStore;
  categoryFilter.value = selectedCategory;
  currentPage = 1;
  renderOffers();
});

document.querySelectorAll(".store-card").forEach((button) => {
  button.addEventListener("click", () => {
    showFavoritesOnly = false;
    selectedStore = button.dataset.store;
    storeFilter.value = selectedStore;
    currentPage = 1;
    renderOffers();
    document.querySelector("#ofertas").scrollIntoView({ behavior: "smooth" });
  });
});

document.querySelector(".newsletter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  event.currentTarget.reset();
  alert("Pronto! Na proxima etapa vamos conectar essa lista a um backend.");
});

applyInitialFilters();
renderCategories();
renderOffers();
loadOffersFromApi();
setInterval(loadOffersFromApi, 30000);
