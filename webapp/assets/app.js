const tg = window.Telegram ? window.Telegram.WebApp : null;

const elements = {
  userName: document.getElementById("userName"),
  userStatus: document.getElementById("userStatus"),
  form: document.getElementById("topicForm"),
  styleChannel: document.getElementById("styleChannel"),
  sourceChannels: document.getElementById("sourceChannels"),
  withImages: document.getElementById("withImages"),
  refreshTopicsButton: document.getElementById("refreshTopicsButton"),
  resetButton: document.getElementById("resetButton"),
  generateButton: document.getElementById("generateButton"),
  savedSources: document.getElementById("savedSources"),
  topicMeta: document.getElementById("topicMeta"),
  topicList: document.getElementById("topicList"),
  topicPostsMeta: document.getElementById("topicPostsMeta"),
  topicPosts: document.getElementById("topicPosts"),
  results: document.getElementById("results"),
  resultsMeta: document.getElementById("resultsMeta"),
  formHint: document.getElementById("formHint"),
  progressWrap: document.getElementById("progressWrap"),
  progressFill: document.getElementById("progressFill"),
  progressStep: document.getElementById("progressStep"),
  progressPercent: document.getElementById("progressPercent"),
  toast: document.getElementById("toast"),
};

const state = {
  initData: "",
  activeTopicId: null,
  selectedPostIds: new Set(),
  latestReport: null,
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

function parseSources(raw) {
  return raw
    .split(/[,\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
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

function resetSelection() {
  state.activeTopicId = null;
  state.selectedPostIds = new Set();
  elements.generateButton.disabled = true;
  elements.topicPosts.innerHTML = "";
  elements.topicPostsMeta.textContent =
    "Выберите тему, чтобы увидеть исходные посты.";
}

function clearResults() {
  elements.results.innerHTML = "";
}

function renderSavedSources(items) {
  elements.savedSources.innerHTML = "";
  if (!items || !items.length) {
    return;
  }
  items.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "history-card";
    const title = document.createElement("div");
    title.className = "history-title";
    title.textContent = item.channel_title || item.channel_ref;
    const meta = document.createElement("div");
    meta.className = "history-meta";
    meta.textContent = item.channel_ref;
    chip.appendChild(title);
    chip.appendChild(meta);
    elements.savedSources.appendChild(chip);
  });
}

function renderTopics(report) {
  state.latestReport = report || null;
  elements.topicList.innerHTML = "";
  resetSelection();
  if (!report || !report.topics || !report.topics.length) {
    elements.topicMeta.textContent = report
      ? "Подходящие категории пока не найдены."
      : "Сводка пока не построена.";
    return;
  }

  const createdAt = report.created_at
    ? new Date(report.created_at).toLocaleString("ru-RU")
    : "—";
  elements.topicMeta.textContent = `Последний отчет: ${createdAt}. Категорий: ${report.categories_count}, постов: ${report.posts_count}.`;

  report.topics.forEach((topic) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "result-card topic-card";
    card.dataset.topicId = String(topic.id);

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const label = document.createElement("span");
    label.textContent = topic.label;
    const count = document.createElement("span");
    count.className = "chip";
    count.textContent = `${topic.post_count} постов`;
    meta.appendChild(label);
    meta.appendChild(count);

    const summary = document.createElement("div");
    summary.className = "result-text";
    summary.textContent = topic.summary;

    card.appendChild(meta);
    card.appendChild(summary);
    card.addEventListener("click", () => loadTopicPosts(topic.id));
    elements.topicList.appendChild(card);
  });
}

function updateGenerateButton() {
  const count = state.selectedPostIds.size;
  elements.generateButton.disabled = count === 0;
  elements.generateButton.textContent = count
    ? `Сгенерировать (${count})`
    : "Сгенерировать";
}

function renderTopicPosts(items) {
  elements.topicPosts.innerHTML = "";
  if (!items.length) {
    elements.topicPostsMeta.textContent = "В этой теме пока нет постов.";
    updateGenerateButton();
    return;
  }
  elements.topicPostsMeta.textContent =
    "Выберите один или несколько постов для генерации.";
  items.forEach((item) => {
    const card = document.createElement("label");
    card.className = "result-card post-card";

    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "post-select";
    check.checked = state.selectedPostIds.has(item.id);
    check.addEventListener("change", () => {
      if (check.checked) {
        state.selectedPostIds.add(item.id);
      } else {
        state.selectedPostIds.delete(item.id);
      }
      updateGenerateButton();
    });

    const content = document.createElement("div");
    content.className = "post-content";

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const source = document.createElement("span");
    source.textContent = item.source_title || item.source_ref;
    const date = document.createElement("span");
    date.textContent = item.published_at
      ? new Date(item.published_at).toLocaleString("ru-RU")
      : "—";
    meta.appendChild(source);
    meta.appendChild(date);

    const text = document.createElement("div");
    text.className = "result-text";
    text.textContent = item.text;

    content.appendChild(meta);
    content.appendChild(text);
    card.appendChild(check);
    card.appendChild(content);
    elements.topicPosts.appendChild(card);
  });
  updateGenerateButton();
}

function renderResults(posts, errors) {
  clearResults();
  elements.resultsMeta.textContent = posts.length
    ? `Готово. Постов: ${posts.length}. Они уже отправлены и в чат с ботом.`
    : "Пока ничего не сгенерировано.";

  errors.forEach((err) => {
    const card = document.createElement("div");
    card.className = "result-card";
    const meta = document.createElement("div");
    meta.className = "result-meta";
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = "Ошибка";
    meta.appendChild(chip);
    const text = document.createElement("div");
    text.className = "result-text";
    text.textContent = err;
    card.appendChild(meta);
    card.appendChild(text);
    elements.results.appendChild(card);
  });

  posts.forEach((post) => {
    const card = document.createElement("div");
    card.className = "result-card";

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const source = document.createElement("span");
    source.textContent = post.source;
    const date = document.createElement("span");
    date.textContent = new Date(post.created_at).toLocaleString("ru-RU");
    meta.appendChild(source);
    meta.appendChild(date);

    card.appendChild(meta);
    if (post.image_url || post.image_file) {
      const media = document.createElement("div");
      media.className = "result-meta";
      if (post.image_url) {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = "IMAGE_URL";
        media.appendChild(chip);
      }
      if (post.image_file) {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = "IMAGE_FILE";
        media.appendChild(chip);
      }
      card.appendChild(media);
    }
    const text = document.createElement("div");
    text.className = "result-text";
    text.textContent = post.text;
    card.appendChild(text);
    elements.results.appendChild(card);
  });
}

async function apiGet(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Ошибка API");
  }
  return data;
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Ошибка API");
  }
  return data;
}

async function loadContext() {
  if (!state.initData) return;
  try {
    const data = await apiGet(
      `/api/editor/context?init_data=${encodeURIComponent(state.initData)}`
    );
    const settings = data.settings || {};
    const savedSources = data.sources || [];
    if (settings.style_channel) {
      elements.styleChannel.value = settings.style_channel;
    }
    elements.withImages.checked = Boolean(settings.with_images);
    if (Array.isArray(settings.sources) && settings.sources.length) {
      elements.sourceChannels.value = settings.sources.join(", ");
    } else if (savedSources.length) {
      elements.sourceChannels.value = savedSources
        .map((item) => item.channel_ref)
        .join(", ");
    }
    renderSavedSources(savedSources);
    renderTopics(data.latest_report || null);
  } catch (err) {
    console.warn("Failed to load editorial context", err);
  }
}

async function refreshTopics() {
  const styleChannel = elements.styleChannel.value.trim();
  const sources = parseSources(elements.sourceChannels.value);
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
  setHint("Обновляю темы за 30 дней…");
  setProgress("Сбор источников", 15);
  elements.refreshTopicsButton.disabled = true;

  try {
    const data = await apiPost("/api/editor/topics/refresh", {
      init_data: state.initData,
      style_channel: styleChannel,
      sources,
      days: 30,
      save_settings: true,
    });
    setProgress("Категоризация", 75);
    renderTopics(data.report || null);
    await loadContext();
    setProgress("Готово", 100);
    setHint("Темы обновлены.");
    if (data.errors && data.errors.length) {
      showToast(data.errors.join("\n"));
    }
  } catch (err) {
    console.error(err);
    showToast(err.message || "Ошибка обновления тем");
    setHint(err.message || "Ошибка обновления тем", "error");
  } finally {
    elements.refreshTopicsButton.disabled = false;
    setTimeout(hideProgress, 800);
  }
}

async function loadTopicPosts(topicId) {
  state.activeTopicId = topicId;
  elements.topicPostsMeta.textContent = "Загружаю посты…";
  try {
    const data = await apiGet(
      `/api/editor/topics/${topicId}/posts?init_data=${encodeURIComponent(
        state.initData
      )}`
    );
    renderTopicPosts(data.items || []);
  } catch (err) {
    console.error(err);
    elements.topicPostsMeta.textContent = err.message || "Ошибка загрузки постов";
  }
}

async function generateSelected() {
  const styleChannel = elements.styleChannel.value.trim();
  const selectedPostIds = Array.from(state.selectedPostIds);
  if (!styleChannel) {
    setHint("Укажите канал для стиля.", "error");
    return;
  }
  if (!selectedPostIds.length) {
    setHint("Выберите хотя бы один пост.", "error");
    return;
  }

  hideToast();
  setHint("Генерирую посты и отправляю их в чат с ботом…");
  setProgress("Генерация", 30);
  elements.generateButton.disabled = true;

  try {
    const data = await apiPost("/api/editor/generate", {
      init_data: state.initData,
      style_channel: styleChannel,
      selected_post_ids: selectedPostIds,
      with_images: elements.withImages.checked,
    });
    renderResults(data.posts || [], data.errors || []);
    setProgress("Отправка в чат", 100);
    setHint("Готово. Результаты отправлены в чат с ботом.");
  } catch (err) {
    console.error(err);
    showToast(err.message || "Ошибка генерации");
    setHint(err.message || "Ошибка генерации", "error");
  } finally {
    updateGenerateButton();
    setTimeout(hideProgress, 800);
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  refreshTopics();
});

elements.resetButton.addEventListener("click", () => {
  elements.styleChannel.value = "";
  elements.sourceChannels.value = "";
  elements.withImages.checked = false;
  resetSelection();
  clearResults();
  renderTopics(null);
  setHint("Поля очищены.");
});

elements.generateButton.addEventListener("click", generateSelected);

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

loadContext();
