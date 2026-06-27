let adminOffers = [];
let reviewOffers = [];
let botSettings = {};

const moneyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const page = document.body.dataset.adminPage;
const byId = (id) => document.querySelector(`#${id}`);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Nao foi possivel concluir a operacao.");
  return payload;
}

function renderPublishedOffers() {
  const search = (byId("adminSearch")?.value || "").trim().toLowerCase();
  const visible = adminOffers.filter((offer) =>
    `${offer.title} ${offer.store} ${offer.category}`.toLowerCase().includes(search)
  );
  if (byId("adminTotalOffers")) byId("adminTotalOffers").textContent = adminOffers.length;
  if (!byId("adminOfferList")) return;
  byId("adminOfferList").innerHTML = visible.map((offer) => `
    <article class="admin-offer-card">
      <img src="${escapeHtml(offer.image)}" alt="${escapeHtml(offer.title)}">
      <div><h3>${escapeHtml(offer.title)}</h3><p>${escapeHtml(offer.store)} / ${escapeHtml(offer.category)} / ${offer.discount}% OFF</p><p>${moneyFormatter.format(offer.currentPrice)} antes ${moneyFormatter.format(offer.oldPrice)}</p></div>
      <div class="admin-card-actions">
        <a href="produto.html?id=${encodeURIComponent(offer.id)}">Pagina</a>
        <button type="button" data-delete-offer="${escapeHtml(offer.id)}">Excluir</button>
      </div>
    </article>
  `).join("") || "<p>Nenhuma oferta publicada.</p>";
  document.querySelectorAll("[data-delete-offer]").forEach((button) => {
    button.addEventListener("click", () => deletePublishedOffer(button.dataset.deleteOffer));
  });
}

async function loadPublishedOffers() {
  const payload = await api("/api/offers");
  adminOffers = payload.offers || [];
  renderPublishedOffers();
}

async function deletePublishedOffer(id) {
  const status = byId("publishedStatus");
  if (status) status.textContent = "Removendo oferta...";
  const previous = adminOffers;
  adminOffers = adminOffers.filter((offer) => String(offer.id) !== String(id));
  try {
    await api("/api/offers", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(adminOffers) });
    renderPublishedOffers();
    if (status) status.textContent = "Oferta removida.";
  } catch (error) {
    adminOffers = previous;
    if (status) status.textContent = error.message;
  }
}

function renderReviewOffers() {
  if (byId("reviewCount")) byId("reviewCount").textContent = reviewOffers.length;
  if (!byId("reviewOfferList")) return;
  byId("reviewOfferList").innerHTML = reviewOffers.map((offer) => `
    <article class="review-card">
      <img src="${escapeHtml(offer.image)}" alt="${escapeHtml(offer.title)}">
      <div><h3>${escapeHtml(offer.title)}</h3><p>${escapeHtml(offer.store)} / ${escapeHtml(offer.category)} / ${offer.discount}% OFF</p><p>${moneyFormatter.format(offer.currentPrice)} antes ${moneyFormatter.format(offer.oldPrice)}</p>${offer.quality?.rating ? `<p>Avaliacao ${offer.quality.rating} / ${offer.quality.sales || 0} vendas</p>` : ""}</div>
      <div class="review-actions"><a href="${escapeHtml(offer.affiliateUrl)}" target="_blank" rel="sponsored noopener">Conferir</a><button type="button" data-approve="${escapeHtml(offer.id)}">Aprovar</button><button type="button" data-reject="${escapeHtml(offer.id)}">Rejeitar</button></div>
    </article>
  `).join("") || "<p>Nenhuma oferta aguardando revisao.</p>";
  document.querySelectorAll("[data-approve]").forEach((button) => button.addEventListener("click", () => reviewAction("approve", button.dataset.approve)));
  document.querySelectorAll("[data-reject]").forEach((button) => button.addEventListener("click", () => reviewAction("reject", button.dataset.reject)));
}

async function loadReviewOffers() {
  const payload = await api("/api/review-offers");
  reviewOffers = payload.reviewOffers || [];
  renderReviewOffers();
}

async function reviewAction(action, id) {
  const status = byId("reviewStatus");
  if (status) status.textContent = action === "approve" ? "Publicando oferta..." : "Removendo oferta...";
  try {
    const payload = await api(`/api/review-offers/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
    reviewOffers = payload.reviewOffers || [];
    renderReviewOffers();
    if (status) status.textContent = action === "approve" ? "Oferta publicada." : "Oferta rejeitada.";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function renderBotStatus(status) {
  const sources = status.sources || [];
  byId("botStatusList").innerHTML = sources.map((source) => `
    <article class="bot-status-item ${source.ok ? "ok" : "error"}"><strong>${escapeHtml(source.name || source.type)}</strong><span>${source.ok ? `${source.count || 0} itens aprovados pelo filtro` : `Erro: ${escapeHtml(source.error)}`}</span><span>${escapeHtml(source.type)}</span></article>
  `).join("") || "<p>Nenhuma execucao registrada.</p>";
  byId("botStatusSummary").textContent = status.checkedAt ? `Ultima execucao: ${new Date(status.checkedAt).toLocaleString("pt-BR")}` : "O bot ainda nao registrou uma execucao.";
}

async function loadStatus() {
  const [health, status, offers] = await Promise.all([api("/healthz"), api("/api/bot-status"), api("/api/offers")]);
  byId("storageStatus").textContent = health.persistent ? "Banco persistente" : "Banco temporario";
  byId("storageStatus").className = `status-pill ${health.persistent ? "ok" : "error"}`;
  byId("adminTotalOffers").textContent = (offers.offers || []).length;
  renderBotStatus(status);
}

function fillSettings() {
  Object.entries(botSettings).forEach(([key, value]) => {
    const input = byId(key);
    if (!input) return;
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = value;
  });
}

async function loadSettings() {
  const payload = await api("/api/bot-settings");
  botSettings = payload.settings || {};
  fillSettings();
}

async function saveSettings(event) {
  event.preventDefault();
  const settings = {
    minimumDiscount: Number(byId("minimumDiscount").value),
    minimumRating: Number(byId("minimumRating").value),
    minimumSales: Number(byId("minimumSales").value),
    minimumCommissionRate: Number(byId("minimumCommissionRate").value),
    maxPages: Number(byId("maxPages").value),
    mercadoLivreMaxPages: Number(byId("mercadoLivreMaxPages").value),
    autoPublishShopee: byId("autoPublishShopee").checked,
    autoPublishMercadoLivre: byId("autoPublishMercadoLivre").checked
  };
  byId("settingsStatus").textContent = "Salvando...";
  try {
    const payload = await api("/api/bot-settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings) });
    botSettings = payload.settings;
    fillSettings();
    byId("settingsStatus").textContent = "Configuracoes salvas.";
  } catch (error) {
    byId("settingsStatus").textContent = error.message;
  }
}

async function runBot() {
  byId("runBotNow").disabled = true;
  byId("runBotStatus").textContent = "Executando Shopee, Mercado Livre, qualidade e limpeza...";
  try {
    const payload = await api("/api/run-bot", { method: "POST" });
    const removed = (payload.cleanup?.publishedRemoved || 0) + (payload.cleanup?.reviewRemoved || 0);
    const shopee = payload.storeSummary?.shopee || {};
    const mercadoLivre = payload.storeSummary?.mercadolivre || {};
    byId("runBotStatus").textContent = `Shopee: ${shopee.found || 0} encontradas. Mercado Livre: ${mercadoLivre.found || 0} encontradas, ${mercadoLivre.candidates || 0} novas oportunidades. ${payload.autoPublished || 0} publicadas, ${payload.addedToReview || 0} em revisao e ${removed} antigas removidas.`;
    await loadStatus();
  } catch (error) {
    byId("runBotStatus").textContent = error.message;
  } finally {
    byId("runBotNow").disabled = false;
  }
}

byId("logoutAdmin")?.addEventListener("click", () => fetch("/api/logout", { method: "POST" }).finally(() => { window.location.href = "login.html"; }));
byId("adminSearch")?.addEventListener("input", renderPublishedOffers);
byId("botSettingsForm")?.addEventListener("submit", saveSettings);
byId("runBotNow")?.addEventListener("click", runBot);

const loaders = {
  status: loadStatus,
  review: loadReviewOffers,
  offers: loadPublishedOffers,
  settings: loadSettings
};
loaders[page]?.().catch((error) => {
  const status = byId("runBotStatus") || byId("reviewStatus") || byId("publishedStatus") || byId("settingsStatus");
  if (status) status.textContent = error.message;
});
