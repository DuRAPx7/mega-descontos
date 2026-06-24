let adminOffers = [];
let reviewOffers = [];
let botSettings = {};

const moneyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const adminTotalOffers = document.querySelector("#adminTotalOffers");
const adminOfferList = document.querySelector("#adminOfferList");
const adminSearch = document.querySelector("#adminSearch");
const reviewOfferList = document.querySelector("#reviewOfferList");
const reviewCount = document.querySelector("#reviewCount");
const reviewStatus = document.querySelector("#reviewStatus");
const botStatusList = document.querySelector("#botStatusList");
const botStatusSummary = document.querySelector("#botStatusSummary");
const runBotStatus = document.querySelector("#runBotStatus");
const storageStatus = document.querySelector("#storageStatus");
const runBotNow = document.querySelector("#runBotNow");
const logoutAdmin = document.querySelector("#logoutAdmin");
const botSettingsForm = document.querySelector("#botSettingsForm");
const settingsStatus = document.querySelector("#settingsStatus");
const publishedStatus = document.querySelector("#publishedStatus");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Nao foi possivel concluir a operacao.");
  }
  return payload;
}

function renderPublishedOffers() {
  const search = adminSearch.value.trim().toLowerCase();
  const visible = adminOffers.filter((offer) =>
    `${offer.title} ${offer.store} ${offer.category}`.toLowerCase().includes(search)
  );
  adminTotalOffers.textContent = adminOffers.length;
  adminOfferList.innerHTML = visible.map((offer) => `
    <article class="admin-offer-card">
      <img src="${escapeHtml(offer.image)}" alt="${escapeHtml(offer.title)}">
      <div>
        <h3>${escapeHtml(offer.title)}</h3>
        <p>${escapeHtml(offer.store)} / ${escapeHtml(offer.category)} / ${offer.discount}% OFF</p>
        <p>${moneyFormatter.format(offer.currentPrice)} antes ${moneyFormatter.format(offer.oldPrice)}</p>
      </div>
      <div class="admin-card-actions">
        <a href="${escapeHtml(offer.affiliateUrl)}" target="_blank" rel="sponsored noopener">Abrir</a>
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
  publishedStatus.textContent = "Removendo oferta...";
  const previous = adminOffers;
  adminOffers = adminOffers.filter((offer) => String(offer.id) !== String(id));
  try {
    await api("/api/offers", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(adminOffers)
    });
    renderPublishedOffers();
    publishedStatus.textContent = "Oferta removida.";
  } catch (error) {
    adminOffers = previous;
    publishedStatus.textContent = error.message;
  }
}

function renderReviewOffers() {
  reviewCount.textContent = reviewOffers.length;
  reviewOfferList.innerHTML = reviewOffers.map((offer) => `
    <article class="review-card">
      <img src="${escapeHtml(offer.image)}" alt="${escapeHtml(offer.title)}">
      <div>
        <h3>${escapeHtml(offer.title)}</h3>
        <p>${escapeHtml(offer.store)} / ${escapeHtml(offer.category)} / ${offer.discount}% OFF</p>
        <p>${moneyFormatter.format(offer.currentPrice)} antes ${moneyFormatter.format(offer.oldPrice)}</p>
        ${offer.quality?.rating ? `<p>Avaliacao ${offer.quality.rating} / ${offer.quality.sales || 0} vendas</p>` : ""}
      </div>
      <div class="review-actions">
        <a href="${escapeHtml(offer.affiliateUrl)}" target="_blank" rel="sponsored noopener">Conferir</a>
        <button type="button" data-approve="${escapeHtml(offer.id)}">Aprovar</button>
        <button type="button" data-reject="${escapeHtml(offer.id)}">Rejeitar</button>
      </div>
    </article>
  `).join("") || "<p>Nenhuma oferta aguardando revisao.</p>";

  document.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", () => reviewAction("approve", button.dataset.approve));
  });
  document.querySelectorAll("[data-reject]").forEach((button) => {
    button.addEventListener("click", () => reviewAction("reject", button.dataset.reject));
  });
}

async function loadReviewOffers() {
  const payload = await api("/api/review-offers");
  reviewOffers = payload.reviewOffers || [];
  renderReviewOffers();
}

async function reviewAction(action, id) {
  reviewStatus.textContent = action === "approve" ? "Publicando oferta..." : "Removendo oferta...";
  try {
    const payload = await api(`/api/review-offers/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    reviewOffers = payload.reviewOffers || [];
    renderReviewOffers();
    await loadPublishedOffers();
    reviewStatus.textContent = action === "approve" ? "Oferta publicada." : "Oferta rejeitada.";
  } catch (error) {
    reviewStatus.textContent = error.message;
  }
}

function renderBotStatus(status) {
  const sources = status.sources || [];
  botStatusList.innerHTML = sources.map((source) => `
    <article class="bot-status-item ${source.ok ? "ok" : "error"}">
      <strong>${escapeHtml(source.name || source.type)}</strong>
      <span>${source.ok ? `${source.count || 0} itens aprovados pelo filtro` : `Erro: ${escapeHtml(source.error)}`}</span>
      <span>${escapeHtml(source.type)}</span>
    </article>
  `).join("") || "<p>Nenhuma execucao registrada.</p>";
  botStatusSummary.textContent = status.checkedAt
    ? `Ultima execucao: ${new Date(status.checkedAt).toLocaleString("pt-BR")}`
    : "O bot ainda nao registrou uma execucao.";
}

async function loadStatus() {
  const [health, status] = await Promise.all([api("/healthz"), api("/api/bot-status")]);
  storageStatus.textContent = health.persistent ? "Banco persistente" : "Banco temporario";
  storageStatus.className = `status-pill ${health.persistent ? "ok" : "error"}`;
  renderBotStatus(status);
}

function fillSettings() {
  for (const [key, value] of Object.entries(botSettings)) {
    const input = document.querySelector(`#${key}`);
    if (!input) continue;
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else {
      input.value = value;
    }
  }
}

async function loadSettings() {
  const payload = await api("/api/bot-settings");
  botSettings = payload.settings || {};
  fillSettings();
}

botSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const settings = {
    minimumDiscount: Number(document.querySelector("#minimumDiscount").value),
    minimumRating: Number(document.querySelector("#minimumRating").value),
    minimumSales: Number(document.querySelector("#minimumSales").value),
    minimumCommissionRate: Number(document.querySelector("#minimumCommissionRate").value),
    maxPages: Number(document.querySelector("#maxPages").value),
    autoPublishShopee: document.querySelector("#autoPublishShopee").checked
  };
  settingsStatus.textContent = "Salvando...";
  try {
    const payload = await api("/api/bot-settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings)
    });
    botSettings = payload.settings;
    fillSettings();
    settingsStatus.textContent = "Configuracoes salvas.";
  } catch (error) {
    settingsStatus.textContent = error.message;
  }
});

runBotNow.addEventListener("click", async () => {
  runBotNow.disabled = true;
  runBotStatus.textContent = "Executando coleta, qualidade e limpeza...";
  try {
    const payload = await api("/api/run-bot", { method: "POST" });
    const captured = payload.shopee?.count || 0;
    const removed = (payload.cleanup?.publishedRemoved || 0) + (payload.cleanup?.reviewRemoved || 0);
    runBotStatus.textContent = `${captured} ofertas da Shopee passaram pelo filtro. ${payload.autoPublished || 0} foram publicadas automaticamente e ${removed} antigas foram removidas.`;
    await Promise.all([loadStatus(), loadReviewOffers(), loadPublishedOffers()]);
  } catch (error) {
    runBotStatus.textContent = error.message;
  } finally {
    runBotNow.disabled = false;
  }
});

adminSearch.addEventListener("input", renderPublishedOffers);
logoutAdmin.addEventListener("click", () => {
  fetch("/api/logout", { method: "POST" }).finally(() => {
    window.location.href = "login.html";
  });
});

Promise.all([loadStatus(), loadSettings(), loadReviewOffers(), loadPublishedOffers()])
  .catch((error) => {
    runBotStatus.textContent = error.message;
  });
