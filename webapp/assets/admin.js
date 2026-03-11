const elements = {
  tokenInput: document.getElementById("adminToken"),
  saveToken: document.getElementById("saveToken"),
  authStatus: document.getElementById("authStatus"),
  statusMeta: document.getElementById("statusMeta"),
  statusGrid: document.getElementById("statusGrid"),
  serviceGrid: document.getElementById("serviceGrid"),
  refreshStatus: document.getElementById("refreshStatus"),
  runList: document.getElementById("runList"),
  errorList: document.getElementById("errorList"),
  logSelect: document.getElementById("logSelect"),
  logLines: document.getElementById("logLines"),
  logRefresh: document.getElementById("logRefresh"),
  logContent: document.getElementById("logContent"),
};

const STORAGE_KEY = "cannibal_admin_token";

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let idx = 0;
  let value = bytes;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function formatUptime(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hrs}ч ${mins}м`;
}

function getToken() {
  return localStorage.getItem(STORAGE_KEY) || "";
}

function setToken(token) {
  if (token) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

async function apiGet(path) {
  const token = getToken();
  const response = await fetch(path, {
    headers: token ? { "X-Admin-Token": token } : {},
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Ошибка API");
  }
  return data;
}

function setAuthStatus(message, tone = "warn") {
  elements.authStatus.textContent = message;
  elements.authStatus.style.color =
    tone === "ok" ? "var(--accent)" : "var(--accent-2)";
}

function renderStatusCards(data) {
  const llmLabel = data.llm_provider === "llama_cpp" ? "llama.cpp" : "LLM";
  const llmValue =
    data.llm_status?.status === "ok"
      ? "OK"
      : data.llm_status?.status === "error"
      ? "Ошибка"
      : data.llm_status?.status === "external"
      ? "Внешний"
      : "—";
  const cards = [
    {
      label: "Uptime",
      value: formatUptime(data.uptime_sec),
    },
    {
      label: "WebApp URL",
      value: data.webapp_url || "—",
    },
    {
      label: llmLabel,
      value: llmValue,
    },
    {
      label: "База",
      value: data.db?.exists ? formatBytes(data.db.size) : "не найдена",
    },
    {
      label: "Chroma",
      value: data.chroma?.exists ? formatBytes(data.chroma.size) : "не найдена",
    },
    {
      label: "Посты",
      value: data.counts?.posts ?? 0,
    },
    {
      label: "Каналы",
      value: data.counts?.channels ?? 0,
    },
    {
      label: "Изображения",
      value: data.image_enabled ? "включены" : "выкл",
    },
  ];

  elements.statusGrid.innerHTML = "";
  cards.forEach((card) => {
    const el = document.createElement("div");
    el.className = "status-card";
    el.innerHTML = `
      <div class="status-label">${card.label}</div>
      <div class="status-value">${card.value}</div>
    `;
    elements.statusGrid.appendChild(el);
  });
}

function renderServices(list) {
  elements.serviceGrid.innerHTML = "";
  if (!list || !list.length) {
    elements.serviceGrid.innerHTML =
      '<div class="status-card"><div class="status-label">Сервисы</div><div class="status-value">Нет данных</div></div>';
    return;
  }
  list.forEach((service) => {
    const status = service.status || "unknown";
    const detail = service.detail || service.last_update || "";
    const label = service.name || "service";
    const badge =
      status === "ok"
        ? "OK"
        : status === "error"
        ? "Ошибка"
        : status === "stale"
        ? "Нет активности"
        : status;
    const card = document.createElement("div");
    card.className = "status-card";
    card.innerHTML = `
      <div class="status-label">${label}</div>
      <div class="status-value">${badge}</div>
      <div class="status-detail">${detail}</div>
    `;
    elements.serviceGrid.appendChild(card);
  });
}

function renderRuns(list) {
  elements.runList.innerHTML = "";
  if (!list.length) {
    elements.runList.innerHTML =
      '<div class="history-card">Запусков пока нет.</div>';
    return;
  }
  list.forEach((item) => {
    const card = document.createElement("div");
    card.className = "history-card";
    const sources = item.sources?.join(", ") || "—";
    card.innerHTML = `
      <div class="history-title">#${item.id} · ${item.created_at || "—"}</div>
      <div class="history-meta">Стиль: ${item.style_channel}</div>
      <div class="history-meta">Источники: ${sources}</div>
      <div class="history-meta">Лимит: ${item.limit} · Постов: ${
      item.posts_count
    }</div>
      <div class="history-meta">Статус: ${item.status}</div>
      ${item.error ? `<div class="history-meta">Ошибка: ${item.error}</div>` : ""}
    `;
    elements.runList.appendChild(card);
  });
}

function renderErrors(list) {
  elements.errorList.innerHTML = "";
  if (!list.length) {
    elements.errorList.innerHTML =
      '<div class="history-card">Ошибок нет.</div>';
    return;
  }
  list.forEach((item) => {
    const card = document.createElement("div");
    card.className = "history-card";
    card.innerHTML = `
      <div class="history-title">#${item.id} · ${item.created_at || "—"}</div>
      <div class="history-meta">Канал стиля: ${item.style_channel}</div>
      <div class="history-meta">Ошибка: ${item.error}</div>
    `;
    elements.errorList.appendChild(card);
  });
}

async function loadStatus() {
  try {
    const data = await apiGet("/api/admin/status");
    elements.statusMeta.textContent = `Обновлено: ${new Date(
      data.server_time
    ).toLocaleString("ru-RU")}`;
    renderStatusCards(data);
    renderServices(data.services || []);
    renderRuns(data.recent_runs || []);
    renderErrors(data.recent_errors || []);
    await loadLogsList(data.logs || []);
    setAuthStatus("Доступ подтверждён", "ok");
  } catch (err) {
    elements.statusMeta.textContent = err.message;
    setAuthStatus(err.message || "Нет доступа");
  }
}

async function loadLogsList(items) {
  const list = items.length ? items : (await apiGet("/api/admin/logs/list")).items;
  elements.logSelect.innerHTML = "";
  if (!list.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Логи не найдены";
    elements.logSelect.appendChild(option);
    return;
  }
  list.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = `${item.name} · ${formatBytes(item.size)}`;
    elements.logSelect.appendChild(option);
  });
}

async function loadLogContent() {
  const name = elements.logSelect.value;
  if (!name) {
    elements.logContent.textContent = "Лог не выбран.";
    return;
  }
  try {
    const lines = Number(elements.logLines.value || 200);
    const data = await apiGet(
      `/api/admin/logs?name=${encodeURIComponent(name)}&lines=${lines}`
    );
    elements.logContent.textContent = data.lines.join("\n") || "Пусто.";
  } catch (err) {
    elements.logContent.textContent = err.message;
  }
}

function initToken() {
  const params = new URLSearchParams(window.location.search);
  const tokenFromQuery = params.get("token");
  if (tokenFromQuery) {
    setToken(tokenFromQuery);
    history.replaceState(null, "", "/admin");
  }
  const saved = getToken();
  elements.tokenInput.value = saved;
  if (saved) {
    setAuthStatus("Токен сохранён", "ok");
  }
}

elements.saveToken.addEventListener("click", () => {
  const token = elements.tokenInput.value.trim();
  setToken(token);
  setAuthStatus(token ? "Токен сохранён" : "Токен не задан");
  loadStatus();
});

elements.refreshStatus.addEventListener("click", loadStatus);
elements.logRefresh.addEventListener("click", loadLogContent);
elements.logSelect.addEventListener("change", loadLogContent);

initToken();
loadStatus();
setInterval(() => {
  if (getToken()) {
    loadStatus();
    loadLogContent();
  }
}, 5000);
