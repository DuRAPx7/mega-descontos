const OFFERS_STORAGE_KEY = "mega_descontos_offers";
const API_OFFERS_URL = "/api/offers";

if (window.location.protocol === "file:") {
  document.body.innerHTML = `
    <main class="login-shell">
      <section class="login-card">
        <h1>Admin bloqueado</h1>
        <p>Abra o painel pelo servidor local usando iniciar_site.bat e acesse http://127.0.0.1:8000/admin.html.</p>
      </section>
    </main>
  `;
  throw new Error("Admin disponivel apenas pelo servidor local.");
}

let adminOffers = [...(window.DEFAULT_OFFERS || [])];
let offerCandidates = [];
let editingId = null;
let adminSearchTerm = "";

const form = document.querySelector("#offerForm");
const offerId = document.querySelector("#offerId");
const title = document.querySelector("#title");
const store = document.querySelector("#store");
const category = document.querySelector("#category");
const oldPrice = document.querySelector("#oldPrice");
const currentPrice = document.querySelector("#currentPrice");
const image = document.querySelector("#image");
const affiliateUrl = document.querySelector("#affiliateUrl");
const expiresAt = document.querySelector("#expiresAt");
const adminOfferList = document.querySelector("#adminOfferList");
const adminTotalOffers = document.querySelector("#adminTotalOffers");
const adminSearch = document.querySelector("#adminSearch");
const cancelEdit = document.querySelector("#cancelEdit");
const resetOffers = document.querySelector("#resetOffers");
const exportOffers = document.querySelector("#exportOffers");
const importOffersFile = document.querySelector("#importOffersFile");
const mergeImport = document.querySelector("#mergeImport");
const replaceImport = document.querySelector("#replaceImport");
const importStatus = document.querySelector("#importStatus");
const runBotNow = document.querySelector("#runBotNow");
const logoutAdmin = document.querySelector("#logoutAdmin");
const botStatusList = document.querySelector("#botStatusList");
const botStatusSummary = document.querySelector("#botStatusSummary");
const mercadoLivreStatus = document.querySelector("#mercadoLivreStatus");
const connectMercadoLivre = document.querySelector("#connectMercadoLivre");
const disconnectMercadoLivre = document.querySelector("#disconnectMercadoLivre");
const candidateList = document.querySelector("#candidateList");
const candidateStatus = document.querySelector("#candidateStatus");

const moneyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL"
});

function loadAdminOffers() {
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

function isHttpPage() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

function saveAdminOffers() {
  localStorage.setItem(OFFERS_STORAGE_KEY, JSON.stringify(adminOffers));
  if (!isHttpPage()) {
    return Promise.resolve();
  }

  return fetch(API_OFFERS_URL, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(adminOffers)
  }).then(async (response) => {
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Nao foi possivel salvar no servidor.");
    }
    return result;
  });
}

function loadAdminOffersFromApi() {
  if (!isHttpPage()) {
    adminOffers = loadAdminOffers();
    renderAdminOffers();
    return Promise.resolve();
  }

  return fetch(API_OFFERS_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("API indisponivel");
      }
      return response.json();
    })
    .then((apiOffers) => {
      adminOffers = Array.isArray(apiOffers) ? apiOffers : apiOffers.offers || loadAdminOffers();
      localStorage.setItem(OFFERS_STORAGE_KEY, JSON.stringify(adminOffers));
      renderAdminOffers();
    })
    .catch(() => {
      adminOffers = loadAdminOffers();
      renderAdminOffers();
    });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isMercadoLivreAffiliateUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" && (
      parsed.hostname === "meli.la" ||
      (parsed.hostname.endsWith("mercadolivre.com.br") && parsed.pathname.startsWith("/social/"))
    );
  } catch {
    return false;
  }
}

function renderCandidates() {
  const publishedIds = new Set(adminOffers.map((offer) => String(offer.id)));
  const visibleCandidates = offerCandidates.filter((candidate) => !publishedIds.has(String(candidate.id)));

  candidateStatus.textContent = `${visibleCandidates.length} ofertas aguardando link afiliado.`;
  candidateList.innerHTML = visibleCandidates
    .map((candidate) => `
      <article class="candidate-card">
        <img src="${escapeHtml(candidate.image)}" alt="${escapeHtml(candidate.title)}" onerror="this.style.visibility='hidden'">
        <div>
          <h3>${escapeHtml(candidate.title)}</h3>
          <p>${escapeHtml(candidate.store)} / ${escapeHtml(candidate.category)} / ${candidate.discount}% OFF</p>
          <p>${moneyFormatter.format(candidate.currentPrice)} antes ${moneyFormatter.format(candidate.oldPrice)}</p>
        </div>
        <div class="candidate-actions">
          <input type="url" data-candidate-link="${candidate.id}" placeholder="Cole o link meli.la deste produto">
          <a href="${escapeHtml(candidate.productUrl)}" target="_blank" rel="noopener">Abrir produto</a>
          <button type="button" data-activate-candidate="${candidate.id}">Publicar</button>
        </div>
      </article>
    `)
    .join("");

  if (!visibleCandidates.length) {
    candidateList.innerHTML = "<p>Nenhuma oferta candidata no momento.</p>";
  }

  document.querySelectorAll("[data-activate-candidate]").forEach((button) => {
    button.addEventListener("click", () => activateCandidate(Number(button.dataset.activateCandidate)));
  });
}

function loadCandidates() {
  if (!isHttpPage()) {
    offerCandidates = [];
    renderCandidates();
    return Promise.resolve();
  }

  return fetch("/api/candidates", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Nao foi possivel carregar as ofertas encontradas.");
      }
      return response.json();
    })
    .then((payload) => {
      offerCandidates = payload.candidates || [];
      renderCandidates();
    })
    .catch((error) => {
      candidateStatus.textContent = error.message;
    });
}

function activateCandidate(candidateId) {
  const candidate = offerCandidates.find((item) => Number(item.id) === candidateId);
  const input = document.querySelector(`[data-candidate-link="${candidateId}"]`);
  const affiliateLink = input?.value.trim() || "";
  if (!candidate || !isMercadoLivreAffiliateUrl(affiliateLink)) {
    candidateStatus.textContent = "Cole o link meli.la gerado para esse produto.";
    return;
  }

  const previousOffers = [...adminOffers];
  const offer = {
    ...candidate,
    affiliateUrl: affiliateLink,
    foundAt: new Date().toISOString(),
    source: "mercadolivre_candidate"
  };
  adminOffers = [offer, ...adminOffers.filter((item) => String(item.id) !== String(offer.id))];
  saveAdminOffers()
    .then(() => {
      candidateStatus.textContent = "Oferta publicada com o link afiliado.";
    })
    .catch((error) => {
      adminOffers = previousOffers;
      candidateStatus.textContent = error.message;
    })
    .finally(() => {
      renderAdminOffers();
      renderCandidates();
    });
}

function loadMercadoLivreIntegration() {
  return fetch("/api/integrations/mercadolivre", { cache: "no-store" })
    .then((response) => response.json().then((payload) => ({ response, payload })))
    .then(({ response, payload }) => {
      if (!response.ok) {
        throw new Error(payload.error || "Nao foi possivel verificar o Mercado Livre.");
      }
      if (!payload.configured) {
        mercadoLivreStatus.textContent = `Configure no Render: ${payload.missing.join(", ")}.`;
        connectMercadoLivre.disabled = true;
        disconnectMercadoLivre.hidden = true;
        return;
      }
      connectMercadoLivre.disabled = false;
      connectMercadoLivre.hidden = payload.connected;
      disconnectMercadoLivre.hidden = !payload.connected;
      mercadoLivreStatus.textContent = payload.connected
        ? `Conta conectada${payload.userId ? ` / usuario ${payload.userId}` : ""}. O token sera renovado automaticamente.`
        : "Configuracao pronta. Conecte sua conta para liberar as buscas.";
    })
    .catch((error) => {
      mercadoLivreStatus.textContent = error.message;
    });
}

function renderBotStatus(status) {
  const sources = status.sources || [];
  botStatusSummary.textContent = status.checkedAt
    ? `Ultima execucao: ${new Date(status.checkedAt).toLocaleString("pt-BR")} / ${status.generatedOffers || 0} publicadas / ${status.rejectedOffers || 0} rejeitadas.`
    : "O bot ainda nao registrou uma execucao.";

  if (!sources.length) {
    botStatusList.innerHTML = "<p>Nenhuma fonte registrada ainda.</p>";
    return;
  }

  botStatusList.innerHTML = sources
    .map((source) => `
      <article class="bot-status-item ${source.ok ? "ok" : "error"}">
        <strong>${source.name || source.type}</strong>
        <span>${source.ok ? `${source.count || 0} itens capturados` : `Erro: ${source.error}`}</span>
        <span>${source.type}</span>
      </article>
    `)
    .join("");
}

function loadBotStatus() {
  if (!isHttpPage()) {
    renderBotStatus({ sources: [] });
    return Promise.resolve();
  }

  return fetch("/api/bot-status", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Nao foi possivel carregar o status do bot.");
      }
      return response.json();
    })
    .then(renderBotStatus)
    .catch((error) => {
      botStatusSummary.textContent = error.message;
    });
}

function calculateDiscount(oldValue, currentValue) {
  if (oldValue <= 0 || currentValue >= oldValue) {
    return 0;
  }
  return Math.round(((oldValue - currentValue) / oldValue) * 100);
}

function isRealUrl(value, imageUrl = false) {
  const markers = ["seu-codigo", "seucodigo", "seu_id", "seu-id", "produto-exemplo", "exemplo-"];
  const stockImages = ["images.unsplash.com", "pexels.com", "pixabay.com"];

  try {
    const parsed = new URL(value);
    const normalized = decodeURIComponent(value).toLowerCase();
    if (parsed.protocol !== "https:" || markers.some((marker) => normalized.includes(marker))) {
      return false;
    }
    if (!imageUrl && (!parsed.pathname || parsed.pathname === "/")) {
      return false;
    }
    return !imageUrl || !stockImages.some((host) => parsed.hostname.includes(host));
  } catch {
    return false;
  }
}

function normalizeImportedOffer(offer, fallbackId) {
  const oldValue = Number(offer.oldPrice);
  const currentValue = Number(offer.currentPrice);

  if (!offer.title || !offer.store || !offer.category || !offer.image || !offer.affiliateUrl) {
    return null;
  }

  if (!Number.isFinite(oldValue) || !Number.isFinite(currentValue)) {
    return null;
  }

  if (currentValue <= 0 || currentValue >= oldValue) {
    return null;
  }

  if (!isRealUrl(offer.affiliateUrl) || !isRealUrl(offer.image, true)) {
    return null;
  }

  return {
    id: Number(offer.id) || fallbackId,
    title: String(offer.title).trim(),
    store: String(offer.store).trim(),
    category: String(offer.category).trim(),
    oldPrice: oldValue,
    currentPrice: currentValue,
    discount: Number(offer.discount) || calculateDiscount(oldValue, currentValue),
    image: String(offer.image).trim(),
    affiliateUrl: String(offer.affiliateUrl).trim(),
    expiresAt: offer.expiresAt || "",
    foundAt: offer.foundAt || new Date().toISOString(),
    source: offer.source || "manual_import"
  };
}

function resetForm() {
  editingId = null;
  form.reset();
  offerId.value = "";
  form.querySelector(".primary-admin-button").textContent = "Salvar oferta";
}

function getVisibleOffers() {
  const normalizedSearch = adminSearchTerm.trim().toLowerCase();
  if (!normalizedSearch) {
    return adminOffers;
  }

  return adminOffers.filter((offer) =>
    `${offer.title} ${offer.store} ${offer.category}`.toLowerCase().includes(normalizedSearch)
  );
}

function renderAdminOffers() {
  const visibleOffers = getVisibleOffers();

  adminTotalOffers.textContent = adminOffers.length;
  adminOfferList.innerHTML = visibleOffers
    .map((offer) => `
      <article class="admin-offer-card">
        <img src="${offer.image}" alt="${offer.title}" onerror="this.style.visibility='hidden'">
        <div>
          <h3>${offer.title}</h3>
          <p>${offer.store} / ${offer.category} / ${offer.discount}% OFF</p>
          <p>${moneyFormatter.format(offer.currentPrice)} antes ${moneyFormatter.format(offer.oldPrice)}</p>
          ${offer.expiresAt ? `<p>Encerra em ${new Date(offer.expiresAt).toLocaleString("pt-BR")}</p>` : ""}
        </div>
        <div class="admin-card-actions">
          <a href="${offer.affiliateUrl}" target="_blank" rel="sponsored noopener">Abrir link</a>
          <button type="button" data-action="edit" data-id="${offer.id}">Editar</button>
          <button type="button" data-action="delete" data-id="${offer.id}">Excluir</button>
        </div>
      </article>
    `)
    .join("");

  if (!visibleOffers.length) {
    adminOfferList.innerHTML = "<p>Nenhuma oferta encontrada.</p>";
  }

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = Number(button.dataset.id);
      if (button.dataset.action === "edit") {
        editOffer(id);
      } else {
        deleteOffer(id);
      }
    });
  });
}

function editOffer(id) {
  const offer = adminOffers.find((item) => item.id === id);
  if (!offer) {
    return;
  }

  editingId = id;
  offerId.value = offer.id;
  title.value = offer.title;
  store.value = offer.store;
  category.value = offer.category;
  oldPrice.value = offer.oldPrice;
  currentPrice.value = offer.currentPrice;
  image.value = offer.image;
  affiliateUrl.value = offer.affiliateUrl;
  expiresAt.value = toDatetimeLocalValue(offer.expiresAt);
  form.querySelector(".primary-admin-button").textContent = "Atualizar oferta";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function deleteOffer(id) {
  adminOffers = adminOffers.filter((offer) => offer.id !== id);
  saveAdminOffers()
    .catch((error) => {
      importStatus.textContent = error.message;
    })
    .finally(renderAdminOffers);
}

function buildOfferFromForm() {
  const oldValue = Number(oldPrice.value);
  const currentValue = Number(currentPrice.value);

  return {
    id: editingId || Date.now(),
    title: title.value.trim(),
    store: store.value,
    category: category.value,
    oldPrice: oldValue,
    currentPrice: currentValue,
    discount: calculateDiscount(oldValue, currentValue),
    image: image.value.trim(),
    affiliateUrl: affiliateUrl.value.trim(),
    expiresAt: fromDatetimeLocalValue(expiresAt.value),
    foundAt: new Date().toISOString(),
    source: "manual_admin"
  };
}

function toDatetimeLocalValue(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return offsetDate.toISOString().slice(0, 16);
}

function fromDatetimeLocalValue(value) {
  if (!value) {
    return "";
  }
  return new Date(value).toISOString();
}

function readImportFile() {
  const file = importOffersFile.files[0];
  if (!file) {
    importStatus.textContent = "Escolha um arquivo JSON primeiro.";
    return Promise.resolve(null);
  }

  return file.text()
    .then((content) => JSON.parse(content))
    .then((data) => {
      if (!Array.isArray(data)) {
        throw new Error("O JSON precisa conter uma lista de ofertas.");
      }

      const importedOffers = data
        .map((offer, index) => normalizeImportedOffer(offer, Date.now() + index))
        .filter(Boolean);

      if (!importedOffers.length) {
        throw new Error("Nenhuma oferta valida encontrada no arquivo.");
      }

      return importedOffers;
    })
    .catch((error) => {
      importStatus.textContent = `Erro ao importar: ${error.message}`;
      return null;
    });
}

function mergeOffers(importedOffers) {
  const existingById = new Map(adminOffers.map((offer) => [offer.id, offer]));

  importedOffers.forEach((offer) => {
    existingById.set(offer.id, offer);
  });

  return Array.from(existingById.values());
}

function importOffers(mode) {
  readImportFile().then((importedOffers) => {
    if (!importedOffers) {
      return;
    }

    adminOffers = mode === "replace" ? importedOffers : mergeOffers(importedOffers);
    saveAdminOffers()
      .then(() => {
        importStatus.textContent = `${importedOffers.length} ofertas importadas com sucesso.`;
      })
      .catch((error) => {
        importStatus.textContent = error.message;
      })
      .finally(() => {
        resetForm();
        renderAdminOffers();
      });
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();

  const offer = buildOfferFromForm();
  if (!isRealUrl(offer.affiliateUrl)) {
    importStatus.textContent = "Use o link real do produto gerado no seu painel de afiliados.";
    return;
  }
  if (!isRealUrl(offer.image, true)) {
    importStatus.textContent = "Use a URL HTTPS da imagem oficial do produto.";
    return;
  }
  if (offer.currentPrice <= 0 || offer.currentPrice >= offer.oldPrice) {
    importStatus.textContent = "O preco atual precisa ser menor que o preco antigo.";
    return;
  }

  const previousOffers = [...adminOffers];
  if (editingId) {
    adminOffers = adminOffers.map((item) => (item.id === editingId ? offer : item));
  } else {
    adminOffers = [offer, ...adminOffers];
  }

  saveAdminOffers()
    .then(() => {
      importStatus.textContent = "Oferta salva no servidor.";
    })
    .catch((error) => {
      adminOffers = previousOffers;
      importStatus.textContent = error.message;
    })
    .finally(() => {
      resetForm();
      renderAdminOffers();
    });
});

adminSearch.addEventListener("input", () => {
  adminSearchTerm = adminSearch.value;
  renderAdminOffers();
});

cancelEdit.addEventListener("click", resetForm);

resetOffers.addEventListener("click", () => {
  if (!window.confirm("Remover todas as ofertas cadastradas?")) {
    return;
  }
  adminOffers = [];
  saveAdminOffers()
    .catch((error) => {
      importStatus.textContent = error.message;
    })
    .finally(() => {
      resetForm();
      renderAdminOffers();
    });
});

exportOffers.addEventListener("click", () => {
  const data = JSON.stringify(adminOffers, null, 2);
  const blob = new Blob([data], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "ofertas-mega-descontos.json";
  link.click();
  URL.revokeObjectURL(url);
});

mergeImport.addEventListener("click", () => {
  importOffers("merge");
});

replaceImport.addEventListener("click", () => {
  importOffers("replace");
});

runBotNow.addEventListener("click", () => {
  importStatus.textContent = "Rodando bot...";
  fetch("/api/run-bot", { method: "POST" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Nao foi possivel rodar o bot.");
      }
      return response.json();
    })
    .then(() => Promise.all([loadAdminOffersFromApi().then(loadCandidates), loadBotStatus()]))
    .then(() => {
      importStatus.textContent = "Bot executado e ofertas atualizadas.";
    })
    .catch((error) => {
      importStatus.textContent = error.message;
    });
});

logoutAdmin.addEventListener("click", () => {
  fetch("/api/logout", { method: "POST" }).finally(() => {
    window.location.href = "login.html";
  });
});

connectMercadoLivre.addEventListener("click", () => {
  window.location.href = "/api/mercadolivre/connect";
});

disconnectMercadoLivre.addEventListener("click", () => {
  fetch("/api/integrations/mercadolivre/disconnect", { method: "POST" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Nao foi possivel desconectar a conta.");
      }
      return Promise.all([loadMercadoLivreIntegration(), loadCandidates()]);
    })
    .catch((error) => {
      mercadoLivreStatus.textContent = error.message;
    });
});

const mercadoLivreResult = new URLSearchParams(window.location.search).get("ml");
if (mercadoLivreResult === "connected") {
  importStatus.textContent = "Mercado Livre conectado. A primeira busca foi iniciada.";
} else if (mercadoLivreResult === "not-configured") {
  importStatus.textContent = "Configure as credenciais OAuth do Mercado Livre no Render.";
} else if (mercadoLivreResult === "error") {
  importStatus.textContent = "Nao foi possivel concluir a conexao com o Mercado Livre.";
}

loadAdminOffersFromApi().then(loadCandidates);
loadBotStatus();
loadMercadoLivreIntegration();
