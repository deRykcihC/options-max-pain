const state = {
  symbol: "SNDK",
  expiration: "",
  expirations: [],
};

const elements = {
  symbol: document.querySelector("#symbol"),
  headingSymbol: document.querySelector("#heading-symbol"),
  expiration: document.querySelector("#expiration"),
  refresh: document.querySelector("#refresh"),
  status: document.querySelector("#status"),
  source: document.querySelector("#source"),
  timestamp: document.querySelector("#timestamp"),
  underlying: document.querySelector("#underlying"),
  maxPain: document.querySelector("#max-pain"),
  payout: document.querySelector("#payout"),
  rows: document.querySelector("#rows"),
  quickPicks: document.querySelector(".quick-picks"),
};

function money(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function compactNumber(value) {
  return Number(value || 0).toLocaleString(undefined, {
    maximumFractionDigits: 0,
  });
}

function setStatus(message, kind = "muted") {
  elements.status.textContent = message;
  elements.status.dataset.kind = kind;
}

function renderExpirationOptions(expirations, selected) {
  elements.expiration.innerHTML = "";
  for (const expiration of expirations) {
    const option = document.createElement("option");
    option.value = expiration;
    option.textContent = expiration;
    option.selected = expiration === selected;
    elements.expiration.appendChild(option);
  }
}

function renderTable(rows) {
  elements.rows.innerHTML = "";

  for (const row of rows.slice(0, 80)) {
    const tr = document.createElement("tr");
    const isBest = row.price === Number(elements.maxPain.dataset.price);
    if (isBest) tr.className = "best";

    tr.innerHTML = `
      <td>${money(row.price)}</td>
      <td>${compactNumber(row.call_open_interest)}</td>
      <td>${compactNumber(row.put_open_interest)}</td>
      <td>${money(row.call_payout, 0)}</td>
      <td>${money(row.put_payout, 0)}</td>
      <td>${money(row.total_payout, 0)}</td>
    `;
    elements.rows.appendChild(tr);
  }
}

async function loadMaxPain() {
  const symbol = elements.symbol.value.trim().toUpperCase() || "SNDK";
  const symbolChanged = symbol !== state.symbol;
  const params = new URLSearchParams({ symbol });
  if (state.expiration && !symbolChanged) params.set("expiration", state.expiration);

  setStatus("Loading delayed options chain...", "muted");
  elements.refresh.disabled = true;
  elements.expiration.disabled = true;

  try {
    const response = await fetch(`/api/max-pain?${params.toString()}`);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || `Request failed with ${response.status}`);
    }

    state.symbol = payload.symbol;
    state.expiration = payload.expiration;
    state.expirations = payload.expirations;

    elements.symbol.value = payload.symbol;
    elements.headingSymbol.textContent = payload.symbol;
    document.title = `${payload.symbol} Max Pain`;
    renderExpirationOptions(payload.expirations, payload.expiration);

    elements.source.textContent = payload.source;
    elements.timestamp.textContent = payload.timestamp || "n/a";
    elements.underlying.textContent = money(payload.underlying_price);
    elements.maxPain.textContent = money(payload.max_pain.price);
    elements.maxPain.dataset.price = String(payload.max_pain.price);
    elements.payout.textContent = money(payload.max_pain.total_payout, 0);

    renderTable(payload.rows);
    setStatus(`Loaded ${payload.contract_count.toLocaleString()} contracts.`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    elements.refresh.disabled = false;
    elements.expiration.disabled = false;
  }
}

elements.refresh.addEventListener("click", () => {
  const requestedSymbol = elements.symbol.value.trim().toUpperCase() || "SNDK";
  state.expiration = requestedSymbol === state.symbol ? elements.expiration.value : "";
  loadMaxPain();
});

elements.symbol.addEventListener("input", () => {
  elements.symbol.value = elements.symbol.value.toUpperCase();
});

elements.symbol.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    state.expiration = "";
    loadMaxPain();
  }
});

elements.symbol.addEventListener("change", () => {
  state.expiration = "";
  loadMaxPain();
});

elements.expiration.addEventListener("change", () => {
  state.expiration = elements.expiration.value;
  loadMaxPain();
});

elements.quickPicks.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-symbol]");
  if (!button) return;
  elements.symbol.value = button.dataset.symbol;
  state.expiration = "";
  loadMaxPain();
});

loadMaxPain();
