const moneyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const detail = document.querySelector("#productDetail");
const productId = new URLSearchParams(window.location.search).get("id");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function renderProduct(offer) {
  document.title = `${offer.title} - Mega Descontos`;
  document.querySelector('meta[name="description"]').content =
    `${offer.title} por ${moneyFormatter.format(offer.currentPrice)} na ${offer.store}.`;
  document.querySelector("#breadcrumbCategory").textContent = offer.category;
  const quality = offer.quality || {};
  detail.innerHTML = `
    <div class="product-gallery">
      <span class="product-discount">-${offer.discount}%</span>
      <img src="${escapeHtml(offer.image)}" alt="${escapeHtml(offer.title)}">
    </div>
    <div class="product-info">
      <span class="product-store">${escapeHtml(offer.store)}</span>
      <h1>${escapeHtml(offer.title)}</h1>
      <p class="product-category">${escapeHtml(offer.category)}</p>
      <div class="product-price">
        <span>${moneyFormatter.format(offer.currentPrice)}</span>
        <del>${moneyFormatter.format(offer.oldPrice)}</del>
      </div>
      <p class="product-saving">Economia de ${moneyFormatter.format(offer.oldPrice - offer.currentPrice)}</p>
      ${quality.rating ? `<div class="product-quality"><span>Avaliacao ${quality.rating}</span><span>${quality.sales || 0} vendas</span></div>` : ""}
      ${offer.expiresAt ? `<p class="product-expiration">Oferta prevista para encerrar em ${new Date(offer.expiresAt).toLocaleString("pt-BR")}.</p>` : ""}
      <a class="product-buy-button" href="${escapeHtml(offer.affiliateUrl)}" target="_blank" rel="sponsored noopener">Ir para a oferta</a>
      <p class="affiliate-notice">Voce sera direcionado para a loja. Este link pode gerar comissao para o Mega Descontos.</p>
    </div>
  `;
}

function renderNotFound(message) {
  detail.innerHTML = `<div class="product-not-found"><h1>Oferta nao encontrada</h1><p>${escapeHtml(message)}</p><a href="index.html">Ver outras ofertas</a></div>`;
}

if (!productId) {
  renderNotFound("O endereço deste produto esta incompleto.");
} else {
  fetch("/api/offers", { cache: "no-store" })
    .then((response) => response.json())
    .then((payload) => {
      const offers = Array.isArray(payload) ? payload : payload.offers || [];
      const offer = offers.find((item) => String(item.id) === productId);
      if (!offer) throw new Error("A promocao pode ter terminado ou sido removida.");
      renderProduct(offer);
    })
    .catch((error) => renderNotFound(error.message));
}
