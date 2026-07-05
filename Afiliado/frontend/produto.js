const moneyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const detail = document.querySelector("#productDetail");
const productId = new URLSearchParams(window.location.search).get("id");
const API_ANALYTICS_EVENTS_URL = "/api/analytics/events";
const FAVORITES_STORAGE_KEY = "mega_descontos_favorites";
let currentOffer = null;
let countdownTimer = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function trackAnalytics(type, offer) {
  const payload = JSON.stringify({
    type,
    offerId: String(offer.id),
    title: offer.title,
    category: offer.category,
    store: offer.store,
    path: window.location.pathname,
    occurredAt: new Date().toISOString()
  });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      API_ANALYTICS_EVENTS_URL,
      new Blob([payload], { type: "application/json" })
    );
  } else {
    fetch(API_ANALYTICS_EVENTS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true
    }).catch(() => {});
  }
}

function offerImages(offer) {
  return [...new Set([offer.image, ...(Array.isArray(offer.images) ? offer.images : [])].filter(Boolean))];
}

function starsFor(rating) {
  const rounded = Math.max(0, Math.min(5, Math.round(Number(rating || 0))));
  return `${"★".repeat(rounded)}${"☆".repeat(5 - rounded)}`;
}

function updateCountdown(expiresAt) {
  const target = document.querySelector("#offerCountdown");
  if (!target) return;
  const expiration = new Date(expiresAt).getTime();
  const difference = expiration - Date.now();
  if (!Number.isFinite(expiration) || difference <= 0) {
    target.innerHTML = "<span class='countdown-ended'>Consulte a disponibilidade na loja</span>";
    return;
  }
  const days = Math.floor(difference / 86400000);
  const hours = Math.floor((difference % 86400000) / 3600000);
  const minutes = Math.floor((difference % 3600000) / 60000);
  const seconds = Math.floor((difference % 60000) / 1000);
  target.innerHTML = `
    <span><b>${days}</b><small>Dias</small></span>
    <span><b>${String(hours).padStart(2, "0")}</b><small>Horas</small></span>
    <span><b>${String(minutes).padStart(2, "0")}</b><small>Min</small></span>
    <span><b>${String(seconds).padStart(2, "0")}</b><small>Seg</small></span>
  `;
}

function loadFavorites() {
  try {
    return JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY) || "[]").map(String);
  } catch {
    return [];
  }
}

function updateSaveButton() {
  const button = document.querySelector("#productSave");
  if (!button || !currentOffer) return;
  const saved = loadFavorites().includes(String(currentOffer.id));
  button.classList.toggle("active", saved);
  button.textContent = saved ? "♥ Salvo" : "♡ Salvar";
  const heart = document.querySelector(".product-heart");
  if (heart) {
    heart.classList.toggle("active", saved);
    heart.textContent = saved ? "♥" : "♡";
  }
}

function renderProduct(offer) {
  currentOffer = offer;
  const quality = offer.quality || {};
  const rating = Number(quality.rating || 0);
  const sales = Number(quality.sales || 0);
  const images = offerImages(offer);
  const saving = Math.max(0, Number(offer.oldPrice) - Number(offer.currentPrice));
  const description = offer.description ||
    `${offer.title} com ${offer.discount}% de desconto. Confira disponibilidade, prazo e condições diretamente na ${offer.store}.`;
  const expirationText = offer.expiresAt
    ? new Date(offer.expiresAt).toLocaleString("pt-BR")
    : "Consulte na loja";

  document.title = `${offer.title} - Mega Descontos`;
  document.querySelector('meta[name="description"]').content =
    `${offer.title} por ${moneyFormatter.format(offer.currentPrice)} na ${offer.store}.`;
  document.querySelector("#breadcrumbCategory").textContent = offer.category;

  detail.innerHTML = `
    <div class="product-showcase">
      <section class="product-gallery product-gallery-2026">
        <div class="product-main-image">
          <span class="product-discount">-${offer.discount}%</span>
          ${offer.discount >= 50 ? `<span class="flash-offer">🔥 Oferta relâmpago</span>` : ""}
          <img id="productMainImage" src="${escapeHtml(images[0])}" alt="${escapeHtml(offer.title)}">
          ${images.length > 1 ? `<button class="gallery-arrow previous" type="button" aria-label="Imagem anterior">‹</button><button class="gallery-arrow next" type="button" aria-label="Próxima imagem">›</button>` : ""}
        </div>
        <div class="product-thumbnails">
          ${images.map((image, index) => `<button type="button" class="${index === 0 ? "active" : ""}" data-gallery-index="${index}"><img src="${escapeHtml(image)}" alt="Imagem ${index + 1} de ${escapeHtml(offer.title)}"></button>`).join("")}
        </div>
      </section>

      <section class="product-info product-info-2026">
        <button class="product-heart" type="button" aria-label="Salvar oferta">♡</button>
        <span class="product-store">${escapeHtml(offer.store)} <b>●</b></span>
        <h1>${escapeHtml(offer.title)}</h1>
        ${rating ? `<div class="product-rating-line"><span>${starsFor(rating)}</span><b>${rating.toLocaleString("pt-BR")}</b>${sales ? `<small>• ${sales.toLocaleString("pt-BR")} vendas</small>` : ""}</div>` : ""}

        <div class="product-price-card">
          <div class="product-price-main">
            <p><span>-${offer.discount}%</span> Por apenas</p>
            <div><strong>${moneyFormatter.format(offer.currentPrice)}</strong><del>${moneyFormatter.format(offer.oldPrice)}</del></div>
            <b>Economia de ${moneyFormatter.format(saving)}</b>
          </div>
          <div class="product-countdown"><p>Oferta termina em:</p><div id="offerCountdown"></div></div>
          <div class="product-benefits">
            <span>▣ <b>Oferta verificada</b><small>Preço monitorado</small></span>
            <span>⟳ <b>Atualização frequente</b><small>Dados recentes</small></span>
            <span>↗ <b>Compra na loja</b><small>Você decide por lá</small></span>
            <span>♢ <b>Link seguro</b><small>Parceiro verificado</small></span>
          </div>
        </div>

        <div class="product-secure"><span>♢</span><div><b>Compra 100% segura</b><small>Você finaliza o pedido no ambiente protegido da ${escapeHtml(offer.store)}.</small></div></div>
        <a class="product-buy-button" href="${escapeHtml(offer.affiliateUrl)}" target="_blank" rel="sponsored noopener">🛒 &nbsp; Ir para a oferta</a>
        <a class="product-store-button" href="${escapeHtml(offer.affiliateUrl)}" target="_blank" rel="sponsored noopener">Ver na loja ↗</a>
        <p class="affiliate-notice">Você será direcionado para a loja. Este link pode gerar comissão para o Mega Descontos.</p>
      </section>
    </div>

    <div class="product-extra-grid">
      <article>
        <h2>Sobre o produto</h2>
        <p>${escapeHtml(description)}</p>
        <ul>
          <li>✓ ${escapeHtml(offer.category)}</li>
          <li>✓ Desconto monitorado de ${offer.discount}%</li>
          <li>✓ Oferta encontrada na ${escapeHtml(offer.store)}</li>
        </ul>
      </article>
      <article>
        <h2>Informações da oferta</h2>
        <dl><div><dt>Válida até</dt><dd>${escapeHtml(expirationText)}</dd></div><div><dt>Disponibilidade</dt><dd>Consulte na loja</dd></div><div><dt>Categoria</dt><dd>${escapeHtml(offer.category)}</dd></div><div><dt>Loja</dt><dd>${escapeHtml(offer.store)}</dd></div></dl>
      </article>
      <article class="product-review-summary">
        <h2>Avaliação do produto</h2>
        ${rating ? `<strong>${rating.toLocaleString("pt-BR")}</strong><span>${starsFor(rating)}</span><p>${sales ? `${sales.toLocaleString("pt-BR")} vendas informadas pela loja` : "Avaliação informada pela loja"}</p><div class="rating-progress"><i style="width:${(rating / 5) * 100}%"></i></div>` : `<p>A loja ainda não informou uma avaliação para este produto.</p>`}
      </article>
    </div>

    <section class="product-trust-strip"><span>✺ <b>Melhores descontos</b><small>Atualizados em tempo real</small></span><span>☆ <b>Cupons exclusivos</b><small>Economize ainda mais</small></span><span>♧ <b>Alertas personalizados</b><small>Receba ofertas do seu interesse</small></span><span>◉ <b>Suporte dedicado</b><small>Estamos aqui para ajudar</small></span></section>
  `;

  let activeImage = 0;
  const setActiveImage = (index) => {
    activeImage = (index + images.length) % images.length;
    document.querySelector("#productMainImage").src = images[activeImage];
    document.querySelectorAll("[data-gallery-index]").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.galleryIndex) === activeImage);
    });
  };
  document.querySelectorAll("[data-gallery-index]").forEach((button) => {
    button.addEventListener("click", () => setActiveImage(Number(button.dataset.galleryIndex)));
  });
  document.querySelector(".gallery-arrow.previous")?.addEventListener("click", () => setActiveImage(activeImage - 1));
  document.querySelector(".gallery-arrow.next")?.addEventListener("click", () => setActiveImage(activeImage + 1));
  document.querySelector(".product-heart").addEventListener("click", () => document.querySelector("#productSave").click());
  document.querySelectorAll(".product-buy-button, .product-store-button").forEach((link) => {
    link.addEventListener("click", () => trackAnalytics("outbound_click", offer));
  });

  updateCountdown(offer.expiresAt);
  if (countdownTimer) clearInterval(countdownTimer);
  if (offer.expiresAt) countdownTimer = setInterval(() => updateCountdown(offer.expiresAt), 1000);
  updateSaveButton();
  trackAnalytics("product_view", offer);
}

function renderNotFound(message) {
  detail.innerHTML = `<div class="product-not-found"><h1>Oferta não encontrada</h1><p>${escapeHtml(message)}</p><a href="index.html">Ver outras ofertas</a></div>`;
}

document.querySelector("#productSearch").addEventListener("submit", (event) => {
  event.preventDefault();
  const term = document.querySelector("#productSearchInput").value.trim();
  window.location.href = `index.html${term ? `?busca=${encodeURIComponent(term)}` : ""}`;
});

document.querySelector("#productSave").addEventListener("click", () => {
  if (!currentOffer) return;
  const id = String(currentOffer.id);
  const favorites = loadFavorites();
  const next = favorites.includes(id) ? favorites.filter((favoriteId) => favoriteId !== id) : [...favorites, id];
  localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(next));
  updateSaveButton();
});

document.querySelector("#productShare").addEventListener("click", async () => {
  if (!currentOffer) return;
  const data = { title: currentOffer.title, text: `Confira esta oferta na ${currentOffer.store}`, url: window.location.href };
  try {
    if (navigator.share) await navigator.share(data);
    else {
      await navigator.clipboard.writeText(window.location.href);
      document.querySelector("#productShare").textContent = "✓ Link copiado";
    }
  } catch {
    // O visitante pode cancelar o compartilhamento sem gerar erro na página.
  }
});

if (!productId) {
  renderNotFound("O endereço deste produto está incompleto.");
} else {
  fetch("/api/offers", { cache: "no-store" })
    .then((response) => response.json())
    .then((payload) => {
      const offers = Array.isArray(payload) ? payload : payload.offers || [];
      const offer = offers.find((item) => String(item.id) === productId);
      if (!offer) throw new Error("A promoção pode ter terminado ou sido removida.");
      renderProduct(offer);
    })
    .catch((error) => renderNotFound(error.message));
}
