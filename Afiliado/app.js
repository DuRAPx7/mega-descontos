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

function loadFavorites() {
  const savedFavorites = localStorage.getItem(FAVORITES_STORAGE_KEY);
  if (!savedFavorites) {
    return [];
  }

  try {
    return JSON.parse(savedFavorites);
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
  if (favorites.includes(offerId)) {
    favorites = favorites.filter((id) => id !== offerId);
  } else {
    favorites = [...favorites, offerId];
  }

  saveFavorites();
  renderOffers();
}

function renderOffers() {
  const filteredOffers = getFilteredOffers();

  offerGrid.innerHTML = filteredOffers
    .map((offer) => {
      const isFavorite = favorites.includes(offer.id);
      return `
        <article class="offer-card">
          <span class="discount-pill">-${offer.discount}%</span>
          <button class="favorite-button ${isFavorite ? "active" : ""}" type="button" data-offer-id="${offer.id}" aria-label="Adicionar aos favoritos">
            ${isFavorite ? "Favorito" : "Salvar"}
          </button>
          <img src="${offer.image}" alt="${offer.title}" loading="lazy" onerror="this.style.visibility='hidden'">
          <div class="offer-body">
            <h3>${offer.title}</h3>
            <span class="store-name">${offer.store}</span>
            <div>
              <span class="current-price">${moneyFormatter.format(offer.currentPrice)}</span>
              <span class="old-price">${moneyFormatter.format(offer.oldPrice)}</span>
            </div>
            <a href="${offer.affiliateUrl}" target="_blank" rel="sponsored noopener">Ver oferta</a>
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll(".favorite-button").forEach((button) => {
    button.addEventListener("click", () => {
      toggleFavorite(Number(button.dataset.offerId));
    });
  });

  resultsCount.textContent = `${filteredOffers.length} ${
    filteredOffers.length === 1 ? "oferta" : "ofertas"
  }${showFavoritesOnly ? " favoritas" : ""}`;
  emptyState.textContent = offers.length
    ? "Nenhuma oferta encontrada com esses filtros."
    : "Ainda nao ha ofertas reais publicadas. O bot continua monitorando as lojas.";
  emptyState.hidden = filteredOffers.length > 0;
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  searchTerm = searchInput.value;
  renderOffers();
  document.querySelector("#ofertas").scrollIntoView({ behavior: "smooth" });
});

searchInput.addEventListener("input", () => {
  searchTerm = searchInput.value;
  renderOffers();
});

storeFilter.addEventListener("change", () => {
  selectedStore = storeFilter.value;
  showFavoritesOnly = false;
  renderOffers();
});

categoryFilter.addEventListener("change", () => {
  selectedCategory = categoryFilter.value;
  showFavoritesOnly = false;
  renderOffers();
});

sortFilter.addEventListener("change", () => {
  selectedSort = sortFilter.value;
  renderOffers();
});

clearFilters.addEventListener("click", () => {
  searchTerm = "";
  selectedStore = "Todas";
  selectedCategory = "Todas";
  selectedSort = "discount";
  showFavoritesOnly = false;
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
  renderOffers();
});

document.querySelectorAll(".store-card").forEach((button) => {
  button.addEventListener("click", () => {
    showFavoritesOnly = false;
    selectedStore = button.dataset.store;
    storeFilter.value = selectedStore;
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
