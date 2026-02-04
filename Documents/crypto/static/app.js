const tbody = document.querySelector("#arb-table tbody");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const oppCount = document.getElementById("opp-count");
const bestSpread = document.getElementById("best-spread");
const avgConfidence = document.getElementById("avg-confidence");
const lastUpdate = document.getElementById("last-update");
const loadingOverlay = document.getElementById("loading");

let isFirstLoad = true;

/**
 * Format timestamp to readable format
 */
function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleTimeString("en-US", { 
    hour: "2-digit", 
    minute: "2-digit", 
    second: "2-digit" 
  });
}

/**
 * Format confidence as colored badge
 */
function formatConfidence(score) {
  let level = "low";
  if (score >= 0.8) level = "high";
  else if (score >= 0.6) level = "medium";
  
  return `<span class="confidence-badge confidence-${level}">${(score * 100).toFixed(1)}%</span>`;
}

/**
 * Calculate estimated profit per BTC
 */
function calculateProfit(symbol, spreadBps) {
  // Approximate BTC value (in production, fetch real-time price)
  const btcPrice = 70000;
  const profitPercent = spreadBps / 10000;
  const profitUsd = btcPrice * profitPercent;
  
  return `$${profitUsd.toFixed(2)}`;
}

/**
 * Render table rows with opportunities
 */
function renderRows(rows) {
  if (rows.length === 0) {
    tbody.innerHTML = `
      <tr class="empty-state">
        <td colspan="8">
          <div class="empty-message">
            <span class="empty-icon">📊</span>
            <p>No arbitrage opportunities detected</p>
            <small>System scans every 2 seconds...</small>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = "";
  
  for (const row of rows) {
    const tr = document.createElement("tr");
    
    // Highlight profitable spreads
    const spreadClass = row.adjusted_spread_bps > 0 ? "spread-positive" : "spread-negative";
    
    tr.innerHTML = `
      <td><strong>${row.symbol}</strong></td>
      <td>
        <span style="background: rgba(59, 130, 246, 0.1); padding: 4px 8px; border-radius: 4px; font-size: 0.85rem;">
          ${row.exchange_buy}
        </span>
      </td>
      <td>
        <span style="background: rgba(16, 185, 129, 0.1); padding: 4px 8px; border-radius: 4px; font-size: 0.85rem;">
          ${row.exchange_sell}
        </span>
      </td>
      <td class="${spreadClass}">${row.spread_bps.toFixed(2)}</td>
      <td class="${spreadClass}"><strong>${row.adjusted_spread_bps.toFixed(2)}</strong></td>
      <td>${formatConfidence(row.confidence)}</td>
      <td style="color: var(--success); font-weight: 600;">${calculateProfit(row.symbol, row.adjusted_spread_bps)}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${formatTime(row.timestamp)}</td>
    `;
    
    tbody.appendChild(tr);
  }
}

/**
 * Update stats dashboard
 */
function updateStats(data) {
  const opportunities = data.opportunities;
  
  // Count
  oppCount.textContent = opportunities.length;
  
  // Best spread
  if (opportunities.length > 0) {
    const maxSpread = Math.max(...opportunities.map(o => o.adjusted_spread_bps));
    bestSpread.textContent = `${maxSpread.toFixed(2)} bps`;
    bestSpread.style.color = "var(--success)";
  } else {
    bestSpread.textContent = "—";
    bestSpread.style.color = "var(--text-muted)";
  }
  
  // Average confidence
  if (opportunities.length > 0) {
    const avgConf = opportunities.reduce((sum, o) => sum + o.confidence, 0) / opportunities.length;
    avgConfidence.textContent = `${(avgConf * 100).toFixed(1)}%`;
    
    if (avgConf >= 0.8) avgConfidence.style.color = "var(--success)";
    else if (avgConf >= 0.6) avgConfidence.style.color = "var(--warning)";
    else avgConfidence.style.color = "var(--danger)";
  } else {
    avgConfidence.textContent = "—";
    avgConfidence.style.color = "var(--text-muted)";
  }
  
  // Last update
  lastUpdate.textContent = formatTime(data.timestamp);
}

/**
 * Update connection status
 */
function updateStatus(isConnected) {
  if (isConnected) {
    statusDot.classList.add("active");
    statusText.textContent = "Live";
    statusText.style.color = "var(--success)";
  } else {
    statusDot.classList.remove("active");
    statusText.textContent = "Disconnected";
    statusText.style.color = "var(--danger)";
  }
}

/**
 * Fetch opportunities from API
 */
async function refresh() {
  try {
    const res = await fetch("/api/opportunities");
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    
    const data = await res.json();
    
    // Hide loading overlay after first successful load
    if (isFirstLoad) {
      loadingOverlay.classList.add("hidden");
      isFirstLoad = false;
    }
    
    // Update UI
    renderRows(data.opportunities);
    updateStats(data);
    updateStatus(true);
    
  } catch (error) {
    console.error("Failed to fetch opportunities:", error);
    updateStatus(false);
    
    // Show error in table if first load fails
    if (isFirstLoad) {
      tbody.innerHTML = `
        <tr class="empty-state">
          <td colspan="8">
            <div class="empty-message">
              <span class="empty-icon">⚠️</span>
              <p>Connection Error</p>
              <small>Retrying... ${error.message}</small>
            </div>
          </td>
        </tr>
      `;
    }
  }
}

/**
 * Initialize
 */
async function init() {
  console.log("🚀 Arbitrage Monitor initializing...");
  
  // First refresh
  await refresh();
  
  // Auto-refresh every 2 seconds
  setInterval(refresh, 2000);
  
  console.log("✅ Monitor active");
}

// Start on page load
init();