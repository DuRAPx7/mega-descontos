let adminOffers = [];
let reviewOffers = [];
let discountRequests = [];
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
  const [reviewPayload, requestPayload] = await Promise.all([
    api("/api/review-offers"),
    api("/api/discount-requests")
  ]);
  reviewOffers = reviewPayload.reviewOffers || [];
  discountRequests = requestPayload.requests || [];
  renderReviewOffers();
  renderDiscountRequests();
}

function renderDiscountRequests() {
  if (byId("discountRequestCount")) byId("discountRequestCount").textContent = discountRequests.length;
  if (!byId("discountRequestList")) return;
  byId("discountRequestList").innerHTML = discountRequests.map((request) => `
    <article class="discount-request-admin-card">
      <div>
        <h3>${escapeHtml(request.product)}</h3>
        <p>${request.contact ? `Contato: ${escapeHtml(request.contact)}` : "Cliente não informou contato."}</p>
      </div>
      <span>${request.createdAt ? new Date(request.createdAt).toLocaleString("pt-BR") : ""}</span>
    </article>
  `).join("") || "<p>Nenhuma solicitação de desconto recebida.</p>";
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

function formatDashboardDate(value) {
  return value ? new Date(value).toLocaleString("pt-BR") : "—";
}

function sourceBelongsToStore(source, store) {
  const value = `${source.name || ""} ${source.type || ""}`.toLowerCase();
  const terms = {
    ml: ["mercadolivre", "mercado livre"],
    shopee: ["shopee"],
    amazon: ["amazon"]
  };
  return terms[store].some((term) => value.includes(term));
}

function summarizeStore(status, offers, store, agentStatus = null) {
  const sources = (status.sources || []).filter((source) => sourceBelongsToStore(source, store));
  const storeNames = { ml: "Mercado Livre", shopee: "Shopee", amazon: "Amazon" };
  const published = offers.filter((offer) => offer.store === storeNames[store]).length;
  const approvedFromRun = sources
    .filter((source) => source.ok)
    .reduce((total, source) => total + Number(source.count || 0), 0);
  const failed = sources.filter((source) => !source.ok).length + Number(agentStatus?.failed || 0);
  const timestamps = sources.map((source) => source.checkedAt).filter(Boolean);
  if (agentStatus?.updatedAt) timestamps.push(agentStatus.updatedAt);
  return {
    approved: approvedFromRun || published,
    failed,
    checkedAt: timestamps.sort().at(-1) || status.checkedAt || "",
  };
}

function setStoreDashboard(store, summary, active) {
  if (byId(`${store}Approved`)) byId(`${store}Approved`).textContent = summary.approved;
  if (byId(`${store}Failed`)) byId(`${store}Failed`).textContent = summary.failed;
  if (byId(`${store}LastRun`)) byId(`${store}LastRun`).textContent = formatDashboardDate(summary.checkedAt);
  const state = byId(`${store}StoreState`);
  if (state) {
    state.textContent = active ? "● Ativo" : "● Offline";
    state.className = `store-active ${active ? "" : "offline"}`;
  }
}

function renderBotStatus(status, offers = [], agents = {}) {
  const sources = status.sources || [];
  const mlSummary = summarizeStore(status, offers, "ml", agents.mercadoLivre);
  const shopeeSummary = summarizeStore(status, offers, "shopee");
  const amazonSummary = summarizeStore(status, offers, "amazon", agents.amazon);
  setStoreDashboard("ml", mlSummary, agentIsOnline(agents.mercadoLivre || {}));
  setStoreDashboard("shopee", shopeeSummary, !sources.some((source) => sourceBelongsToStore(source, "shopee") && !source.ok));
  setStoreDashboard("amazon", amazonSummary, agentIsOnline(agents.amazon || {}));

  const approved = mlSummary.approved + shopeeSummary.approved + amazonSummary.approved;
  const failures = mlSummary.failed + shopeeSummary.failed + amazonSummary.failed;
  if (byId("dashboardTotalOffers")) byId("dashboardTotalOffers").textContent = offers.length;
  if (byId("dashboardApproved")) byId("dashboardApproved").textContent = approved;
  if (byId("dashboardFailures")) byId("dashboardFailures").textContent = failures;
  if (byId("dashboardLastRun")) byId("dashboardLastRun").textContent = formatDashboardDate(status.checkedAt);
  if (byId("botStatusList")) {
    byId("botStatusList").innerHTML = sources.map((source) => `
      <article class="bot-status-item ${source.ok ? "ok" : "error"}"><strong>${escapeHtml(source.name || source.type)}</strong><span>${source.ok ? `${source.count || 0} itens aprovados pelo filtro` : `Erro: ${escapeHtml(source.error)}`}</span><span>${escapeHtml(source.type)}</span></article>
    `).join("") || "<p>Nenhuma execucao registrada.</p>";
  }
  if (byId("botStatusSummary")) byId("botStatusSummary").textContent = status.checkedAt ? `Ultima execucao: ${formatDashboardDate(status.checkedAt)}` : "O bot ainda nao registrou uma execucao.";
}

async function loadStatus() {
  const [health, status, offers, agent, amazonAgent] = await Promise.all([
    api("/healthz"),
    api("/api/bot-status"),
    api("/api/offers"),
    api("/api/automation-agent/status"),
    api("/api/amazon-automation-agent/status")
  ]);
  byId("storageStatus").textContent = health.persistent ? "Banco persistente" : "Banco temporario";
  byId("storageStatus").className = `status-pill ${health.persistent ? "ok" : "error"}`;
  const publishedOffers = offers.offers || [];
  byId("adminTotalOffers").textContent = publishedOffers.length;
  renderBotStatus(status, publishedOffers, {
    mercadoLivre: agent.status || {},
    amazon: amazonAgent.status || {}
  });
  renderAutomationAgentStatus(agent.status || {}, "automationAgentState", "automationAgentMessage", "Mercado Livre", "automationAgentTime");
  renderAutomationAgentStatus(amazonAgent.status || {}, "amazonAgentState", "amazonAgentMessage", "Amazon", "amazonAgentTime");
  return {
    mercadoLivre: agent.status || {},
    amazon: amazonAgent.status || {}
  };
}

function agentIsOnline(status) {
  const updatedAt = status.updatedAt ? new Date(status.updatedAt).getTime() : 0;
  return Boolean(updatedAt && Date.now() - updatedAt < 70000);
}

function renderAutomationAgentStatus(status, stateId, messageId, store, timeId = "") {
  if (!byId(stateId)) return;
  const online = agentIsOnline(status);
  const state = online ? status.state || "idle" : "offline";
  const labels = { idle: "Agente online", processing: "Processando", completed: "Concluído", error: "Erro no agente", offline: "Agente offline" };
  byId(stateId).textContent = labels[state] || "Agente local";
  byId(stateId).className = `status-pill ${state === "error" || state === "offline" ? "error" : "ok"}`;
  byId(messageId).textContent = status.message || `Inicie o agente local da ${store}.`;
  if (timeId && byId(timeId)) byId(timeId).textContent = status.updatedAt ? new Date(status.updatedAt).toLocaleTimeString("pt-BR") : "—";
}

async function waitForAutomationAgent(startedAt, endpoint, stateId, messageId, store) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    const payload = await api(endpoint);
    const status = payload.status || {};
    renderAutomationAgentStatus(status, stateId, messageId, store);
    const updatedAt = status.updatedAt ? new Date(status.updatedAt).getTime() : 0;
    if (updatedAt >= startedAt && status.state === "completed") return status;
    if (updatedAt >= startedAt && status.state === "error") throw new Error(status.message || "Falha no agente local.");
  }
  throw new Error(`A coleta terminou, mas o agente ${store} nao respondeu.`);
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
  const startedAt = Date.now();
  byId("runBotNow").disabled = true;
  byId("runBotNow").textContent = "Automação em andamento...";
  byId("runBotStatus").textContent = "Coletando ofertas, preparando links e atualizando o catálogo...";
  try {
    const payload = await api("/api/run-bot", { method: "POST" });
    const removed = (payload.cleanup?.publishedRemoved || 0) + (payload.cleanup?.reviewRemoved || 0);
    const shopee = payload.storeSummary?.shopee || {};
    const mercadoLivre = payload.storeSummary?.mercadolivre || {};
    byId("runBotStatus").textContent = `Shopee: ${shopee.found || 0} encontradas. Mercado Livre: ${mercadoLivre.found || 0} encontradas, ${mercadoLivre.candidates || 0} aguardando geracao dos links.`;
    const agents = await loadStatus();
    const waits = [];
    if ((payload.automationJob?.total || 0) > 0 && agentIsOnline(agents.mercadoLivre)) {
      waits.push(waitForAutomationAgent(startedAt, "/api/automation-agent/status", "automationAgentState", "automationAgentMessage", "Mercado Livre"));
    }
    if (payload.amazonAutomationJob?.state === "pending" && agentIsOnline(agents.amazon)) {
      waits.push(waitForAutomationAgent(startedAt, "/api/amazon-automation-agent/status", "amazonAgentState", "amazonAgentMessage", "Amazon"));
    }
    const completedAgents = await Promise.all(waits);
    const localProcessed = completedAgents.reduce((total, agent) => total + Number(agent.processed || 0), 0);
    const localFailed = completedAgents.reduce((total, agent) => total + Number(agent.failed || 0), 0);
    const waiting = [];
    if ((payload.automationJob?.total || 0) > 0 && !agentIsOnline(agents.mercadoLivre)) waiting.push("Mercado Livre");
    if (payload.amazonAutomationJob?.state === "pending" && !agentIsOnline(agents.amazon)) waiting.push("Amazon");
    byId("runBotStatus").textContent = `${payload.autoPublished || 0} ofertas da Shopee e ${localProcessed} ofertas dos agentes publicadas; ${localFailed} falharam e ${removed} antigas foram removidas.${waiting.length ? ` Aguardando agente: ${waiting.join(" e ")}.` : ""}`;
    await loadStatus();
  } catch (error) {
    byId("runBotStatus").textContent = error.message;
  } finally {
    byId("runBotNow").disabled = false;
    byId("runBotNow").textContent = "Rodar automação completa";
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
