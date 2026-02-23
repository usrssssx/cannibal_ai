const tg = window.Telegram ? window.Telegram.WebApp : null;

const elements = {
  userName: document.getElementById("userName"),
  userStatus: document.getElementById("userStatus"),
  form: document.getElementById("runForm"),
  styleChannel: document.getElementById("styleChannel"),
  sourceChannels: document.getElementById("sourceChannels"),
  limit: document.getElementById("limit"),
  withImages: document.getElementById("withImages"),
  runButton: document.getElementById("runButton"),
  resetButton: document.getElementById("resetButton"),
  results: document.getElementById("results"),
  resultsMeta: document.getElementById("resultsMeta"),
  formHint: document.getElementById("formHint"),
  progressWrap: document.getElementById("progressWrap"),
  progressFill: document.getElementById("progressFill"),
  progressStep: document.getElementById("progressStep"),
  progressPercent: document.getElementById("progressPercent"),
  toast: document.getElementById("toast"),
  history: document.getElementById("history"),
};

const STORAGE_KEY = "cannibal_webapp_settings";

const state = {
  initData: "",
};

function setHint(message, tone = "muted") {
  elements.formHint.textContent = message;
  elements.formHint.style.color =
    tone === "error" ? "#f4b353" : "var(--muted)";
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
}

function hideToast() {
  elements.toast.classList.add("hidden");
  elements.toast.textContent = "";
}

function setUserStatus(text, tone = "muted") {
  elements.userStatus.textContent = text;
  elements.userStatus.style.color =
    tone === "ok" ? "var(--accent)" : "var(--accent-2)";
}

function loadSettings() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    elements.styleChannel.value = data.styleChannel || "";
    elements.sourceChannels.value = data.sourceChannels || "";
    elements.limit.value = data.limit || 1;
    elements.withImages.checked = Boolean(data.withImages);
  } catch (err) {
    console.warn("Failed to load settings", err);
  }
}

function saveSettings() {
  const payload = {
    styleChannel: elements.styleChannel.value.trim(),
    sourceChannels: elements.sourceChannels.value.trim(),
    limit: Number(elements.limit.value || 1),
    withImages: elements.withImages.checked,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function parseSources(raw) {
  return raw
    .split(/[,\\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function clearResults() {
  elements.results.innerHTML = "";
}

function setProgress(step, percent) {
  elements.progressWrap.classList.remove("hidden");
  elements.progressStep.textContent = step;
  elements.progressPercent.textContent = `${percent}%`;
  elements.progressFill.style.width = `${percent}%`;
}

function hideProgress() {
  elements.progressWrap.classList.add("hidden");
  elements.progressFill.style.width = "0%";
}

function renderResults(posts, errors) {
  clearResults();
  const total = posts.length;
  elements.resultsMeta.textContent = total
    ? `Готово. Постов: ${total}.`
    : "Нет результатов.";

  if (errors.length) {
    errors.forEach((err) => {
      const card = document.createElement("div");
      card.className = "result-card";
      card.innerHTML = `<div class="result-meta"><span class="chip">Ошибка</span></div><div class="result-text">${err}</div>`;
      elements.results.appendChild(card);
    });
  }

  posts.forEach((post) => {
    const card = document.createElement("div");
    card.className = "result-card";
    const chips = [];
    if (post.image_url) chips.push(`<span class="chip">IMAGE_URL</span>`);
    if (post.image_file) chips.push(`<span class="chip">IMAGE_FILE</span>`);

    card.innerHTML = `
      <div class="result-meta">
        <span>${post.source}</span>
        <span>${new Date(post.created_at).toLocaleString("ru-RU")}</span>
      </div>
      ${chips.length ? `<div class="result-meta">${chips.join("")}</div>` : ""}
      <div class="result-text">${post.text}</div>
    `;
    elements.results.appendChild(card);
  });
}

function renderHistory(items) {
  elements.history.innerHTML = "";
  if (!items.length) {
    elements.history.innerHTML = `<div class="history-card">История пока пустая.</div>`;
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "history-card";
    const sources = item.sources?.join(", ") || "—";
    card.innerHTML = `
      <div class="history-title">
        ${new Date(item.created_at).toLocaleString("ru-RU")}
      </div>
      <div class="history-meta">Стиль: ${item.style_channel}</div>
      <div class="history-meta">Источники: ${sources}</div>
      <div class="history-meta">Лимит: ${item.limit}</div>
      <div class="history-meta">Статус: ${item.status} · Постов: ${item.posts_count}</div>
      ${item.error ? `<div class="history-meta">Ошибка: ${item.error}</div>` : ""}
    `;
    elements.history.appendChild(card);
  });
}

async function runGeneration() {
  const styleChannel = elements.styleChannel.value.trim();
  const sources = parseSources(elements.sourceChannels.value);
  const limit = Number(elements.limit.value || 1);

  if (!styleChannel) {
    setHint("Укажите канал для стиля.", "error");
    return;
  }
  if (!sources.length) {
    setHint("Укажите хотя бы один источник.", "error");
    return;
  }

  if (!state.initData) {
    setHint("Откройте WebApp через Telegram-бота.", "error");
    return;
  }

  hideToast();
  setHint("Запуск…");
  setProgress("Проверка доступа", 10);
  elements.runButton.disabled = true;

  try {
    setProgress("Отправка запроса", 25);
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        init_data: state.initData,
        style_channel: styleChannel,
        sources,
        limit,
        with_images: elements.withImages.checked,
        save_settings: true,
      }),
    });
    setProgress("Получение ответа", 70);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Ошибка сервера");
    }
    renderResults(data.posts || [], data.errors || []);
    setProgress("Готово", 100);
    await loadHistory();
    setHint("Готово.");
  } catch (err) {
    console.error(err);
    showToast(err.message || "Ошибка запроса");
    setHint(err.message || "Ошибка запроса", "error");
  } finally {
    elements.runButton.disabled = false;
    setTimeout(hideProgress, 800);
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  saveSettings();
  runGeneration();
});

elements.resetButton.addEventListener("click", () => {
  localStorage.removeItem(STORAGE_KEY);
  elements.styleChannel.value = "";
  elements.sourceChannels.value = "";
  elements.limit.value = 1;
  elements.withImages.checked = false;
  setHint("Поля очищены.");
});

if (tg) {
  tg.ready();
  tg.expand();
  state.initData = tg.initData;
  const user = tg.initDataUnsafe?.user;
  const name = user?.username
    ? `@${user.username}`
    : [user?.first_name, user?.last_name].filter(Boolean).join(" ");
  elements.userName.textContent = name || "Пользователь";
  setUserStatus("Сессия подтверждена", "ok");
} else {
  elements.userName.textContent = "Гость";
  setUserStatus("Откройте внутри Telegram", "warn");
}

loadSettings();

async function loadServerSettings() {
  if (!state.initData) return;
  try {
    const response = await fetch(`/api/settings?init_data=${encodeURIComponent(state.initData)}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Ошибка настроек");
    }
    if (data.style_channel) {
      elements.styleChannel.value = data.style_channel;
    }
    if (Array.isArray(data.sources) && data.sources.length) {
      elements.sourceChannels.value = data.sources.join(", ");
    }
    if (data.limit) {
      elements.limit.value = data.limit;
    }
    if (typeof data.with_images === "boolean") {
      elements.withImages.checked = data.with_images;
    }
  } catch (err) {
    console.warn("Failed to load settings", err);
  }
}

async function loadHistory() {
  if (!state.initData) return;
  try {
    const response = await fetch(`/api/history?init_data=${encodeURIComponent(state.initData)}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Ошибка истории");
    }
    renderHistory(data.items || []);
  } catch (err) {
    console.warn("Failed to load history", err);
  }
}

loadServerSettings();
loadHistory();
