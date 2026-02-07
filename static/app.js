const tbody = document.querySelector("#arb-table tbody");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const oppCount = document.getElementById("opp-count");
const bestSpread = document.getElementById("best-spread");
const lastUpdate = document.getElementById("last-update");
const dataSource = document.getElementById("data-source");
const loadingOverlay = document.getElementById("loading");

let isFirstLoad = true;
let lastGoodData = null;

function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleString();
}

function formatNumber(value, decimals = 2) {
  return Number(value).toFixed(decimals);
}

function renderRows(rows) {
  if (rows.length === 0) {
    tbody.innerHTML = `
      <tr class="empty-state">
        <td colspan="7">
          <div class="empty-message">
            <p>No arbitrage opportunities detected</p>
            <small>System scans every 2 seconds</small>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = "";

  for (const row of rows) {
    const tr = document.createElement("tr");
    const spreadClass = row.net_spread_bps > 0 ? "spread-positive" : "spread-negative";

    tr.innerHTML = `
      <td><strong>${row.symbol}</strong></td>
      <td><span class="badge badge-buy">${row.exchange_buy}</span></td>
      <td><span class="badge badge-sell">${row.exchange_sell}</span></td>
      <td>${formatNumber(row.buy_price, 6)}</td>
      <td>${formatNumber(row.sell_price, 6)}</td>
      <td class="${spreadClass}">${formatNumber(row.net_spread_bps, 2)}</td>
      <td class="muted">${formatTime(row.timestamp)}</td>
    `;

    tbody.appendChild(tr);
  }
}

function updateStats(data) {
  const opportunities = data.opportunities;
  oppCount.textContent = opportunities.length;

  if (opportunities.length > 0) {
    const maxSpread = Math.max(...opportunities.map(o => o.net_spread_bps));
    bestSpread.textContent = `${formatNumber(maxSpread, 2)} bps`;
    bestSpread.style.color = "var(--success)";

    dataSource.textContent = "Simulated";
    dataSource.style.color = "var(--text)";
  } else {
    bestSpread.textContent = "--";
    bestSpread.style.color = "var(--text-muted)";
    dataSource.textContent = "Simulated";
    dataSource.style.color = "var(--text-muted)";
  }

  lastUpdate.textContent = formatTime(data.timestamp);
}

function updateStatus(isConnected, detail = "") {
  if (isConnected) {
    statusDot.classList.add("active");
    statusText.textContent = "Live";
    statusText.style.color = "var(--success)";
  } else {
    statusDot.classList.remove("active");
    statusText.textContent = detail ? `Disconnected (${detail})` : "Disconnected";
    statusText.style.color = "var(--danger)";
  }
}

async function refresh() {
  try {
    const res = await fetch("/api/opportunities");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    lastGoodData = data;

    if (isFirstLoad) {
      loadingOverlay.classList.add("hidden");
      isFirstLoad = false;
    }

    renderRows(data.opportunities);
    updateStats(data);
    updateStatus(true);
  } catch (error) {
    updateStatus(false, error.message);
    if (lastGoodData) {
      lastUpdate.textContent = "stale";
      return;
    }
    tbody.innerHTML = `
      <tr class="empty-state">
        <td colspan="7">
          <div class="empty-message">
            <p>Connection Error</p>
            <small>Retrying... ${error.message}</small>
          </div>
        </td>
      </tr>
    `;
  }
}

async function init() {
  await refresh();
  setInterval(refresh, 2000);
}

init();
