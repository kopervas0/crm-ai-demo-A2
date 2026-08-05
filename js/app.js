/* ============================================================
   CRM · Воронка сделок — демо-раздел
   Данные хранятся в localStorage поверх начального data/deals.json,
   чтобы изменения переживали перезагрузку страницы (эмуляция REST API).
   ============================================================ */

const STAGES = [
  { id: "new",           title: "Новый лид" },
  { id: "qualification", title: "Квалификация" },
  { id: "negotiation",   title: "Переговоры" },
  { id: "invoice",       title: "Счёт выставлен" },
  { id: "won",           title: "Сделка закрыта" },
  { id: "lost",          title: "Отказ" },
];

let deals = [];
let clients = [];
let customFields = []; // [{id, name, type}]
let currentDealId = null;
let currentClientId = null;

const board = document.getElementById("board");
const statsEl = document.getElementById("stats");
const toastEl = document.getElementById("toast");
const clientsGrid = document.getElementById("clientsGrid");
const clientStatsEl = document.getElementById("clientStats");

/* ---------------- Слой REST API ----------------
   Сделки и клиенты теперь живут в бэкенде (SQLite), а не в localStorage.
   Эти четыре функции — единственное место, где фронтенд общается с сервером. */

async function apiList(collection) {
  const res = await fetch(`/api/${collection}`);
  if (!res.ok) throw new Error(`GET /api/${collection} → ${res.status}`);
  return res.json();
}

async function apiCreate(collection, obj) {
  const res = await fetch(`/api/${collection}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj),
  });
  if (!res.ok) throw new Error(`POST /api/${collection} → ${res.status}`);
  return res.json();
}

async function apiUpdate(collection, id, obj) {
  const res = await fetch(`/api/${collection}/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj),
  });
  if (!res.ok) throw new Error(`PUT /api/${collection}/${id} → ${res.status}`);
  return res.json();
}

async function apiDelete(collection, id) {
  const res = await fetch(`/api/${collection}/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE /api/${collection}/${id} → ${res.status}`);
  return res.json();
}

/* ---------------- Загрузка данных ---------------- */

async function loadDeals() {
  deals = await apiList("deals");
}

async function loadClients() {
  clients = await apiList("clients");
}

async function loadCustomFields() {
  customFields = await apiList("fields");
}

/* ---------------- Рендер доски ---------------- */

function money(n) {
  return new Intl.NumberFormat("ru-RU").format(n) + " ₽";
}

function isOverdue(due, stage) {
  if (stage === "won" || stage === "lost") return false;
  return new Date(due) < new Date(new Date().toDateString());
}

function applyFilters(list) {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const manager = document.getElementById("managerFilter").value;
  const source = document.getElementById("sourceFilter").value;
  const onlyOverdue = document.getElementById("onlyOverdue").checked;

  return list.filter((d) => {
    if (q) {
      const hay = `${d.client} ${d.company} ${d.phone}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (manager && d.manager !== manager) return false;
    if (source && d.source !== source) return false;
    if (onlyOverdue && !isOverdue(d.due, d.stage)) return false;
    return true;
  });
}

function renderStats(filtered) {
  const totalCount = filtered.length;
  const totalSum = filtered.reduce((s, d) => s + Number(d.amount || 0), 0);
  const won = filtered.filter((d) => d.stage === "won");
  const wonSum = won.reduce((s, d) => s + Number(d.amount || 0), 0);
  const overdueCount = filtered.filter((d) => isOverdue(d.due, d.stage)).length;

  statsEl.innerHTML = `
    <div class="stat-card">
      <div class="stat-card__label">Сделок в работе</div>
      <div class="stat-card__value">${totalCount}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card__label">Сумма воронки</div>
      <div class="stat-card__value">${money(totalSum)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card__label">Закрыто (выигрыш)</div>
      <div class="stat-card__value">${won.length} · ${money(wonSum)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card__label">Просрочено</div>
      <div class="stat-card__value">${overdueCount}</div>
    </div>
  `;
}

function renderBoard() {
  const filtered = applyFilters(deals);
  renderStats(filtered);
  board.innerHTML = "";

  STAGES.forEach((stage) => {
    const stageDeals = filtered.filter((d) => d.stage === stage.id);
    const stageSum = stageDeals.reduce((s, d) => s + Number(d.amount || 0), 0);

    const col = document.createElement("div");
    col.className = "column";
    col.innerHTML = `
      <div class="column__header">
        <span class="column__title">${stage.title}</span>
        <span class="column__count">${stageDeals.length}</span>
      </div>
      <div class="column__sum">${money(stageSum)}</div>
      <div class="column__body" data-stage="${stage.id}"></div>
    `;

    const body = col.querySelector(".column__body");
    stageDeals.forEach((deal) => body.appendChild(renderCard(deal)));

    attachDropZone(body);
    board.appendChild(col);
  });
}

function renderCard(deal) {
  const card = document.createElement("div");
  card.className = "card";
  card.draggable = true;
  card.dataset.id = deal.id;

  const overdue = isOverdue(deal.due, deal.stage);
  const tags = (deal.tags || [])
    .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
    .join("");

  card.innerHTML = `
    <div class="card__top">
      <div>
        <div class="card__client">${escapeHtml(deal.client)}</div>
        <div class="card__company">${escapeHtml(deal.company || "")}</div>
      </div>
      <div class="card__amount">${money(deal.amount)}</div>
    </div>
    <div class="card__meta">
      <span>${escapeHtml(deal.manager || "")}</span>
      <span class="card__due ${overdue ? "overdue" : ""}">${formatDate(deal.due)}</span>
    </div>
    ${tags ? `<div class="card__tags">${tags}</div>` : ""}
  `;

  card.addEventListener("dragstart", () => {
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
  });
  card.addEventListener("click", () => openDealModal(deal.id));

  return card;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

/* ---------------- Валидация телефона / email (правило для всего проекта) ---------------- */

function isValidPhone(value) {
  return /^\d+$/.test(value);
}

function isValidEmail(value) {
  return /^\S+@\S+$/.test(value);
}

function bindPhoneDigitsOnly(input) {
  input.addEventListener("input", () => {
    const cursor = input.selectionStart;
    const digitsOnly = input.value.replace(/\D/g, "");
    if (digitsOnly !== input.value) {
      input.value = digitsOnly;
      input.setSelectionRange(cursor - 1, cursor - 1);
    }
  });
}

/* ---------------- Drag & Drop ---------------- */

function attachDropZone(body) {
  body.addEventListener("dragover", (e) => {
    e.preventDefault();
    body.classList.add("drag-over");
  });
  body.addEventListener("dragleave", () => body.classList.remove("drag-over"));
  body.addEventListener("drop", async (e) => {
    e.preventDefault();
    body.classList.remove("drag-over");
    const dragging = document.querySelector(".card.dragging");
    if (!dragging) return;
    const id = dragging.dataset.id;
    const newStage = body.dataset.stage;
    const deal = deals.find((d) => d.id === id);
    if (deal && deal.stage !== newStage) {
      const prevStage = deal.stage;
      deal.stage = newStage; // оптимистично обновляем UI сразу
      renderBoard();
      showToast(`Сделка «${deal.client}» перенесена в «${STAGES.find((s) => s.id === newStage).title}»`);
      try {
        await apiUpdate("deals", deal.id, deal);
      } catch (err) {
        deal.stage = prevStage; // откат, если сервер не принял
        renderBoard();
        showToast("Не удалось сохранить перенос: " + err.message);
      }
    }
  });
}

/* ---------------- Модалка сделки ---------------- */

const dealOverlay = document.getElementById("dealModalOverlay");
const clientOverlay = document.getElementById("clientModalOverlay");

function openDealModal(id) {
  currentDealId = id;
  const deal = id ? deals.find((d) => d.id === id) : null;

  document.getElementById("modalTitle").textContent = deal ? "Сделка" : "Новая сделка";
  document.getElementById("f_client").value = deal?.client || "";
  document.getElementById("f_company").value = deal?.company || "";
  document.getElementById("f_phone").value = deal?.phone || "";
  document.getElementById("f_amount").value = deal?.amount || "";
  document.getElementById("f_manager").value = deal?.manager || "Алина С.";
  document.getElementById("f_source").value = deal?.source || "Wildberries";
  document.getElementById("f_due").value = deal?.due || "";
  document.getElementById("f_tags").value = (deal?.tags || []).join(", ");

  const stageSelect = document.getElementById("f_stage");
  stageSelect.innerHTML = STAGES.map((s) => `<option value="${s.id}">${s.title}</option>`).join("");
  stageSelect.value = deal?.stage || "new";

  renderCustomFieldsInModal(deal);

  document.getElementById("deleteDealBtn").style.display = deal ? "inline-block" : "none";

  dealOverlay.classList.add("open");
}

function renderCustomFieldsInModal(deal) {
  const container = document.getElementById("customFieldsList");
  if (customFields.length === 0) {
    container.innerHTML = `<div class="hint">Пользовательских полей пока нет — добавьте их в конструкторе.</div>`;
    return;
  }
  container.innerHTML = customFields
    .map((f) => {
      const value = deal?.customValues?.[f.id] ?? "";
      return `
        <label>
          ${escapeHtml(f.name)}
          <input type="${f.type}" data-custom-field="${f.id}" value="${escapeHtml(value)}">
        </label>
      `;
    })
    .join("");
}

function closeModals() {
  dealOverlay.classList.remove("open");
  fieldOverlay.classList.remove("open");
  clientOverlay.classList.remove("open");
}

bindPhoneDigitsOnly(document.getElementById("f_phone"));
bindPhoneDigitsOnly(document.getElementById("fc_phone"));

document.getElementById("addDealBtn").addEventListener("click", () => openDealModal(null));

document.getElementById("saveDealBtn").addEventListener("click", async () => {
  const client = document.getElementById("f_client").value.trim();
  if (!client) {
    showToast("Укажите имя клиента");
    return;
  }

  const phone = document.getElementById("f_phone").value.trim();
  if (phone && !isValidPhone(phone)) {
    showToast("Телефон может содержать только цифры");
    return;
  }

  const customValues = {};
  document.querySelectorAll("[data-custom-field]").forEach((input) => {
    customValues[input.dataset.customField] = input.value;
  });

  const payload = {
    client,
    company: document.getElementById("f_company").value.trim(),
    phone,
    amount: Number(document.getElementById("f_amount").value) || 0,
    manager: document.getElementById("f_manager").value,
    source: document.getElementById("f_source").value,
    due: document.getElementById("f_due").value,
    stage: document.getElementById("f_stage").value,
    tags: document
      .getElementById("f_tags")
      .value.split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    customValues,
  };

  try {
    if (currentDealId) {
      const updated = await apiUpdate("deals", currentDealId, { ...payload, id: currentDealId });
      const idx = deals.findIndex((d) => d.id === currentDealId);
      deals[idx] = updated;
    } else {
      const created = await apiCreate("deals", payload);
      deals.push(created);
    }
    renderBoard();
    closeModals();
    showToast("Сделка сохранена");
  } catch (err) {
    showToast("Ошибка сохранения: " + err.message);
  }
});

document.getElementById("deleteDealBtn").addEventListener("click", async () => {
  if (!currentDealId) return;
  try {
    await apiDelete("deals", currentDealId);
    deals = deals.filter((d) => d.id !== currentDealId);
    renderBoard();
    closeModals();
    showToast("Сделка удалена");
  } catch (err) {
    showToast("Ошибка удаления: " + err.message);
    return;
  }
});

/* ---------------- Конструктор пользовательских полей ---------------- */

const fieldOverlay = document.getElementById("fieldModalOverlay");

document.getElementById("fieldBuilderBtn").addEventListener("click", () => {
  renderFieldDefsList();
  fieldOverlay.classList.add("open");
});

document.getElementById("addFieldBtn").addEventListener("click", async () => {
  const name = document.getElementById("newFieldName").value.trim();
  const type = document.getElementById("newFieldType").value;
  if (!name) {
    showToast("Введите название поля");
    return;
  }
  try {
    const created = await apiCreate("fields", { name, type });
    customFields.push(created);
    document.getElementById("newFieldName").value = "";
    renderFieldDefsList();
    showToast("Поле добавлено");
  } catch (err) {
    showToast("Ошибка добавления поля: " + err.message);
  }
});

function renderFieldDefsList() {
  const list = document.getElementById("fieldDefsList");
  if (customFields.length === 0) {
    list.innerHTML = `<li class="hint">Пока нет ни одного поля.</li>`;
    return;
  }
  list.innerHTML = customFields
    .map(
      (f) => `
      <li>
        <span>${escapeHtml(f.name)} <span class="hint">(${f.type})</span></span>
        <button data-remove-field="${f.id}">Удалить</button>
      </li>
    `
    )
    .join("");

  list.querySelectorAll("[data-remove-field]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.removeField;
      try {
        await apiDelete("fields", id);
        customFields = customFields.filter((f) => f.id !== id);
        renderFieldDefsList();
      } catch (err) {
        showToast("Ошибка удаления поля: " + err.message);
      }
    });
  });
}

/* ---------------- Общие обработчики ---------------- */

document.querySelectorAll("[data-close]").forEach((btn) =>
  btn.addEventListener("click", closeModals)
);
[dealOverlay, fieldOverlay, clientOverlay].forEach((overlay) => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModals();
  });
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModals();
});

["search", "managerFilter", "sourceFilter", "onlyOverdue"].forEach((id) => {
  document.getElementById(id).addEventListener("input", renderBoard);
});

let toastTimer;
function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2200);
}

/* ---------------- Клиенты ---------------- */

function dealsForClient(client) {
  return deals.filter((d) => d.phone && d.phone === client.phone);
}

function applyClientFilters(list) {
  const q = document.getElementById("clientSearch").value.trim().toLowerCase();
  const manager = document.getElementById("clientManagerFilter").value;
  const source = document.getElementById("clientSourceFilter").value;

  return list.filter((c) => {
    if (q) {
      const hay = `${c.name} ${c.company} ${c.phone}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (manager && c.manager !== manager) return false;
    if (source && c.source !== source) return false;
    return true;
  });
}

function renderClientStats(filtered) {
  const totalCount = filtered.length;
  const withDeals = filtered.filter((c) => dealsForClient(c).length > 0).length;
  const totalSum = filtered.reduce(
    (s, c) => s + dealsForClient(c).reduce((ss, d) => ss + Number(d.amount || 0), 0),
    0
  );

  clientStatsEl.innerHTML = `
    <div class="stat-card">
      <div class="stat-card__label">Клиентов</div>
      <div class="stat-card__value">${totalCount}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card__label">Со сделками</div>
      <div class="stat-card__value">${withDeals}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card__label">Сумма их сделок</div>
      <div class="stat-card__value">${money(totalSum)}</div>
    </div>
  `;
}

function renderClients() {
  const filtered = applyClientFilters(clients);
  renderClientStats(filtered);
  clientsGrid.innerHTML = "";

  if (filtered.length === 0) {
    clientsGrid.innerHTML = `<div class="hint">Клиенты не найдены.</div>`;
    return;
  }

  filtered.forEach((client) => clientsGrid.appendChild(renderClientCard(client)));
}

function renderClientCard(client) {
  const card = document.createElement("div");
  card.className = "client-card";

  const clientDeals = dealsForClient(client);
  const dealsSum = clientDeals.reduce((s, d) => s + Number(d.amount || 0), 0);
  const tags = (client.tags || [])
    .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
    .join("");

  card.innerHTML = `
    <div class="client-card__name">${escapeHtml(client.name)}</div>
    <div class="client-card__company">${escapeHtml(client.company || "")}</div>
    <div class="client-card__phone">${escapeHtml(client.phone || "")}</div>
    <div class="client-card__meta">
      <span>${escapeHtml(client.manager || "")}</span>
      <span class="client-card__deals-badge">${clientDeals.length} сделок · ${money(dealsSum)}</span>
    </div>
    ${tags ? `<div class="client-card__tags">${tags}</div>` : ""}
  `;

  card.addEventListener("click", () => openClientModal(client.id));
  return card;
}

function openClientModal(id) {
  currentClientId = id;
  const client = id ? clients.find((c) => c.id === id) : null;

  document.getElementById("clientModalTitle").textContent = client ? "Клиент" : "Новый клиент";
  document.getElementById("fc_name").value = client?.name || "";
  document.getElementById("fc_company").value = client?.company || "";
  document.getElementById("fc_phone").value = client?.phone || "";
  document.getElementById("fc_email").value = client?.email || "";
  document.getElementById("fc_manager").value = client?.manager || "Алина С.";
  document.getElementById("fc_source").value = client?.source || "Wildberries";
  document.getElementById("fc_tags").value = (client?.tags || []).join(", ");
  document.getElementById("fc_notes").value = client?.notes || "";

  const dealsList = document.getElementById("clientDealsList");
  const clientDeals = client ? dealsForClient(client) : [];
  if (clientDeals.length === 0) {
    dealsList.innerHTML = `<div class="hint">Сделок пока нет.</div>`;
  } else {
    dealsList.innerHTML = clientDeals
      .map((d) => {
        const stageTitle = STAGES.find((s) => s.id === d.stage)?.title || d.stage;
        return `
          <div class="client-deal-row">
            <span class="client-deal-row__stage">${escapeHtml(stageTitle)}</span>
            <span class="client-deal-row__amount">${money(d.amount)}</span>
          </div>
        `;
      })
      .join("");
  }

  document.getElementById("deleteClientBtn").style.display = client ? "inline-block" : "none";

  clientOverlay.classList.add("open");
}

document.getElementById("addClientBtn").addEventListener("click", () => openClientModal(null));

document.getElementById("saveClientBtn").addEventListener("click", async () => {
  const name = document.getElementById("fc_name").value.trim();
  if (!name) {
    showToast("Укажите имя клиента");
    return;
  }

  const phone = document.getElementById("fc_phone").value.trim();
  if (phone && !isValidPhone(phone)) {
    showToast("Телефон может содержать только цифры");
    return;
  }

  const email = document.getElementById("fc_email").value.trim();
  if (!isValidEmail(email)) {
    showToast("Укажите корректный email (обязательно с @)");
    return;
  }

  const payload = {
    name,
    company: document.getElementById("fc_company").value.trim(),
    phone,
    email,
    manager: document.getElementById("fc_manager").value,
    source: document.getElementById("fc_source").value,
    tags: document
      .getElementById("fc_tags")
      .value.split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    notes: document.getElementById("fc_notes").value.trim(),
  };

  try {
    if (currentClientId) {
      const updated = await apiUpdate("clients", currentClientId, { ...payload, id: currentClientId });
      const idx = clients.findIndex((c) => c.id === currentClientId);
      clients[idx] = updated;
    } else {
      const created = await apiCreate("clients", payload);
      clients.push(created);
    }
    renderClients();
    closeModals();
    showToast("Клиент сохранён");
  } catch (err) {
    showToast("Ошибка сохранения: " + err.message);
  }
});

document.getElementById("deleteClientBtn").addEventListener("click", async () => {
  if (!currentClientId) return;
  try {
    await apiDelete("clients", currentClientId);
    clients = clients.filter((c) => c.id !== currentClientId);
    renderClients();
    closeModals();
    showToast("Клиент удалён");
  } catch (err) {
    showToast("Ошибка удаления: " + err.message);
  }
});

["clientSearch", "clientManagerFilter", "clientSourceFilter"].forEach((id) => {
  document.getElementById(id).addEventListener("input", renderClients);
});

/* ---------------- Переключение вкладок (Сделки / Клиенты) ---------------- */

const dealsView = document.getElementById("dealsView");
const clientsView = document.getElementById("clientsView");
const tabDeals = document.getElementById("tabDeals");
const tabClients = document.getElementById("tabClients");

function switchView(view) {
  const showClients = view === "clients";
  dealsView.classList.toggle("view--active", !showClients);
  clientsView.classList.toggle("view--active", showClients);
  tabDeals.classList.toggle("tab--active", !showClients);
  tabClients.classList.toggle("tab--active", showClients);
}

tabDeals.addEventListener("click", (e) => {
  e.preventDefault();
  switchView("deals");
});
tabClients.addEventListener("click", (e) => {
  e.preventDefault();
  switchView("clients");
});

/* ---------------- Роль (демо переключения прав) ---------------- */

document.getElementById("roleSelect").addEventListener("change", (e) => {
  const isAdmin = e.target.value === "admin";
  document.getElementById("fieldBuilderBtn").style.display = isAdmin ? "inline-block" : "none";
  showToast(isAdmin ? "Роль: администратор — доступен конструктор полей" : "Роль: менеджер");
});

/* ---------------- Инициализация ---------------- */

(async function init() {
  await Promise.all([loadDeals(), loadClients(), loadCustomFields()]);
  renderBoard();
  renderClients();
})();
