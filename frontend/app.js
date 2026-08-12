const API = "/api";

const MOOD_COLORS = {
  "нейтрально": "var(--mood-нейтрально)",
  "радостно": "var(--mood-радостно)",
  "грустно": "var(--mood-грустно)",
  "иронично": "var(--mood-иронично)",
};

const state = {
  news: [],
  globalMood: "нейтрально",
  currentNewsId: null,
  currentMood: "нейтрально",
};

const el = {
  grid: document.getElementById("grid"),
  status: document.getElementById("status"),
  overlay: document.getElementById("overlay"),
  modalClose: document.getElementById("modalClose"),
  modalSource: document.getElementById("modalSource"),
  modalTitle: document.getElementById("modalTitle"),
  modalLink: document.getElementById("modalLink"),
  modalMoodDial: document.getElementById("modalMoodDial"),
  paneOriginal: document.getElementById("paneOriginal"),
  paneRewritten: document.getElementById("paneRewritten"),
  factBadge: document.getElementById("factBadge"),
  factDetails: document.getElementById("factDetails"),
  customMoodForm: document.getElementById("customMoodForm"),
  customMoodInput: document.getElementById("customMoodInput"),
};

function showStatus(text) {
  el.status.hidden = false;
  el.status.textContent = text;
}
function hideStatus() {
  el.status.hidden = true;
}

function formatDate(raw) {
  if (!raw) return "";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

async function loadNews() {
  showStatus("Загружаем новости…");
  try {
    const res = await fetch(`${API}/news`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.news = await res.json();
  } catch (e) {
    showStatus("Не удалось получить новости с сервера. Убедитесь, что backend запущен.");
    return;
  }

  if (state.news.length === 0) {
    showStatus(
      "Новостей пока нет. Backend не смог получить ленту Google News при старте " +
      "(нужен доступ в интернет с вашей машины). Перезапустите backend или дождитесь автообновления."
    );
    return;
  }

  hideStatus();
  renderGrid();
}

function renderGrid() {
  el.grid.innerHTML = "";
  for (const item of state.news) {
    const card = document.createElement("article");
    card.className = "card";
    card.tabIndex = 0;
    card.style.setProperty("--current-mood-color", MOOD_COLORS[state.globalMood] || MOOD_COLORS["нейтрально"]);

    card.innerHTML = `
      <div class="card-meta">
        <span>${escapeHtml(item.source || "")}</span>
        <span>${escapeHtml(formatDate(item.published_at))}</span>
      </div>
      <h2>${escapeHtml(item.title)}</h2>
      <p>${escapeHtml(item.original_text)}</p>
    `;

    const open = () => openModal(item);
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });

    el.grid.appendChild(card);
  }
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str ?? "";
  return d.innerHTML;
}

/* ---------- Global mood switcher ---------- */

document.querySelectorAll(".topbar .mood-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".topbar .mood-tab").forEach((b) => b.removeAttribute("data-active"));
    btn.setAttribute("data-active", "true");
    state.globalMood = btn.dataset.mood;
    renderGrid();
  });
});

el.customMoodForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const val = el.customMoodInput.value.trim();
  if (!val) return;
  document.querySelectorAll(".topbar .mood-tab").forEach((b) => b.removeAttribute("data-active"));
  state.globalMood = val;
  renderGrid();
});

/* ---------- Modal ---------- */

function openModal(item) {
  state.currentNewsId = item.id;
  state.currentMood = state.globalMood;

  el.modalSource.textContent = item.source || "";
  el.modalTitle.textContent = item.title;
  el.modalLink.href = item.link;
  el.paneOriginal.textContent = item.original_text;

  syncModalMoodButtons();
  el.overlay.hidden = false;
  document.body.style.overflow = "hidden";

  requestRewrite();
}

function closeModal() {
  el.overlay.hidden = true;
  document.body.style.overflow = "";
}

el.modalClose.addEventListener("click", closeModal);
el.overlay.addEventListener("click", (e) => { if (e.target === el.overlay) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !el.overlay.hidden) closeModal(); });

function syncModalMoodButtons() {
  const known = ["нейтрально", "радостно", "грустно", "иронично"];
  el.modalMoodDial.querySelectorAll(".mood-tab").forEach((b) => {
    b.toggleAttribute("data-active", b.dataset.mood === state.currentMood);
  });
  if (!known.includes(state.currentMood)) {
    // показать кастомное настроение как отдельную неактивную метку не обязательно —
    // просто ни одна кнопка не будет подсвечена
  }
}

el.modalMoodDial.querySelectorAll(".mood-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.currentMood = btn.dataset.mood;
    syncModalMoodButtons();
    requestRewrite();
  });
});

async function requestRewrite() {
  el.paneRewritten.textContent = "Переписываем…";
  el.paneRewritten.classList.add("loading-text");
  el.factBadge.textContent = "";
  el.factBadge.dataset.state = "loading";
  el.factDetails.hidden = true;

  try {
    const res = await fetch(`${API}/news/${state.currentNewsId}/rewrite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mood: state.currentMood }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    el.paneRewritten.classList.remove("loading-text");
    el.paneRewritten.textContent = data.rewritten_text;
    renderFactCheck(data.fact_check);
  } catch (e) {
    el.paneRewritten.classList.remove("loading-text");
    el.paneRewritten.textContent = `Ошибка: ${e.message}`;
    el.factBadge.textContent = "";
    el.factBadge.dataset.state = "";
  }
}

function renderFactCheck(fc) {
  if (!fc) return;
  const ok = fc.passed;
  el.factBadge.dataset.state = ok ? "ok" : "warn";
  el.factBadge.textContent = ok
    ? "факты сохранены"
    : `возможны расхождения (${Math.round(fc.score * 100)}%)`;

  const missingParts = [];
  for (const [k, arr] of Object.entries(fc.missing)) {
    if (arr.length) missingParts.push(`<b>${labelFor(k)}</b>: ${arr.map(escapeHtml).join(", ")}`);
  }

  if (missingParts.length) {
    el.factDetails.hidden = false;
    el.factDetails.innerHTML = `Не найдены в переписанном тексте — ${missingParts.join(" · ")}`;
  } else {
    el.factDetails.hidden = false;
    const checkedCount = Object.values(fc.checked).reduce((a, b) => a + b.length, 0);
    el.factDetails.innerHTML = checkedCount
      ? `Проверено фактов: ${checkedCount} (числа, даты, цитаты, имена собственные) — все найдены в переписанном тексте.`
      : `В оригинале не найдено чисел/дат/цитат/имён для автоматической проверки.`;
  }
}

function labelFor(key) {
  return { numbers: "числа", dates: "даты", quotes: "цитаты", name_stems: "имена" }[key] || key;
}

/* ---------- Init ---------- */

loadNews();
