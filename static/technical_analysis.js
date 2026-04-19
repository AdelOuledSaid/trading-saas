const assetSelect = document.getElementById("assetSelect");
const timeframeSelect = document.getElementById("timeframeSelect");
const indicatorSelect = document.getElementById("indicatorSelect");
const runAnalysisBtn = document.getElementById("runAnalysisBtn");

let currentController = null;
let isLoading = false;
let lastFetchAt = 0;
const FETCH_COOLDOWN_MS = 1200;

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const num = Number(value);

  if (Math.abs(num) >= 1_000_000_000) return `$${(num / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(num) >= 1_000_000) return `$${(num / 1_000_000).toFixed(2)}M`;
  if (Math.abs(num) >= 1_000) return `$${(num / 1_000).toFixed(2)}K`;

  return `$${num.toFixed(2)}`;
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const num = Number(value);

  if (num >= 1000) {
    return `$${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
  if (num >= 1) {
    return `$${num.toFixed(4)}`;
  }
  return `$${num.toFixed(6)}`;
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  return `${num >= 0 ? "+" : ""}${num.toFixed(2)}%`;
}

function fillFromLine(path, large = false) {
  return large ? `${path} L900,380 L0,380 Z` : `${path} L600,260 L0,260 Z`;
}

function setSignalPill(el, signal) {
  if (!el) return;

  const map = {
    buy: ["Bullish", "ta-signal-buy"],
    sell: ["Bearish", "ta-signal-sell"],
    neutral: ["Neutral", "ta-signal-neutral"],
  };

  const key = String(signal || "").toLowerCase();
  const [label, cls] = map[key] || map.neutral;

  el.textContent = label;
  el.className = `ta-signal-pill ${cls}`;
}

function setBiasBadge(el, bias) {
  if (!el) return;

  const map = {
    bullish: ["Bullish Bias", "ta-bias-bullish"],
    bearish: ["Bearish Bias", "ta-bias-bearish"],
    mixed: ["Mixed Bias", "ta-bias-neutral"],
    neutral: ["Neutral Bias", "ta-bias-neutral"],
  };

  const key = String(bias || "").toLowerCase();
  const [label, cls] = map[key] || map.neutral;

  el.textContent = label;
  el.className = `ta-bias-pill ${cls}`;
}

function buildSummaryTags(data) {
  const tags = [];

  if (data.signal) tags.push(String(data.signal).toUpperCase());
  if (data.indicator) tags.push(String(data.indicator).toUpperCase());
  if (data.summary_context?.trend) tags.push(String(data.summary_context.trend).toUpperCase());
  if (data.summary_context?.volume_trend) {
    tags.push(`VOL ${String(data.summary_context.volume_trend).toUpperCase()}`);
  }

  return tags.slice(0, 4);
}

function renderWatchlist(items) {
  const container = document.getElementById("watchlistContainer");
  if (!container) return;

  container.innerHTML = "";

  (items || []).forEach((item) => {
    const row = document.createElement("div");
    row.className = "ta-watch-item";
    row.innerHTML = `
      <div>
        <strong>${item.symbol || "--"}</strong>
        <small>${item.name || ""}</small>
      </div>
      <div class="ta-watch-price">
        <strong>${formatPrice(item.price)}</strong>
        <span class="${Number(item.change_24h) >= 0 ? "up" : "down"}">${formatPct(item.change_24h)}</span>
      </div>
    `;
    container.appendChild(row);
  });

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="ta-watch-item">
        <div>
          <strong>Data limited</strong>
          <small>Watchlist temporarily unavailable</small>
        </div>
      </div>
    `;
  }
}

function renderTrending(items) {
  const container = document.getElementById("trendingContainer");
  if (!container) return;

  container.innerHTML = "";

  (items || []).forEach((item) => {
    const row = document.createElement("div");
    row.className = "ta-indicator-row";
    row.innerHTML = `
      <div>
        <strong>${item.symbol || "--"} • ${item.name || ""}</strong>
        <p>Prix: ${formatPrice(item.price)} · 24H: ${formatPct(item.change_24h)} · Rank: ${item.market_cap_rank ?? "--"}</p>
      </div>
      <span class="ta-status-chip ${Number(item.change_24h) >= 0 ? "green" : "gold"}">
        ${Number(item.change_24h) >= 0 ? "Positive" : "Watch"}
      </span>
    `;
    container.appendChild(row);
  });

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="ta-indicator-row">
        <div>
          <strong>Trending unavailable</strong>
          <p>Market list temporarily limited by provider rate limits.</p>
        </div>
        <span class="ta-status-chip gold">Limited</span>
      </div>
    `;
  }
}

function renderAnalysis(data) {
  const heroPrice = document.getElementById("heroPrice");
  const heroMarketCap = document.getElementById("heroMarketCap");
  const heroVolume = document.getElementById("heroVolume");

  const heroAsset = document.getElementById("heroAsset");
  const heroSignal = document.getElementById("heroSignal");
  const heroTrend = document.getElementById("heroTrend");
  const heroRsi = document.getElementById("heroRsi");
  const heroMfi = document.getElementById("heroMfi");
  const heroConfidence = document.getElementById("heroConfidence");

  const biasBadge = document.getElementById("biasBadge");
  const signalValue = document.getElementById("signalValue");
  const confidenceValue = document.getElementById("confidenceValue");
  const emaValue = document.getElementById("emaValue");
  const volumeValue = document.getElementById("volumeValue");
  const summaryText = document.getElementById("summaryText");

  const trendValue = document.getElementById("trendValue");
  const rsiValue = document.getElementById("rsiValue");
  const stochValue = document.getElementById("stochValue");
  const mfiValue = document.getElementById("mfiValue");
  const macdValue = document.getElementById("macdValue");
  const riskValue = document.getElementById("riskValue");

  const res1 = document.getElementById("res1");
  const res2 = document.getElementById("res2");
  const pivot = document.getElementById("pivot");
  const sup1 = document.getElementById("sup1");
  const sup2 = document.getElementById("sup2");

  const executionPlan = document.getElementById("executionPlan");
  const summaryTags = document.getElementById("summaryTags");

  if (heroAsset) heroAsset.textContent = data.token || "--";
  setSignalPill(heroSignal, data.signal);
  setBiasBadge(biasBadge, data.bias);

  if (heroPrice) heroPrice.textContent = formatPrice(data.current_price);
  if (heroMarketCap) heroMarketCap.textContent = formatMoney(data.market_cap);
  if (heroVolume) heroVolume.textContent = formatMoney(data.volume_24h);

  if (heroTrend) heroTrend.textContent = data.summary_context?.trend || "--";
  if (heroRsi) heroRsi.textContent = data.indicators?.rsi ?? "--";
  if (heroMfi) heroMfi.textContent = data.indicators?.mfi ?? "--";
  if (heroConfidence) heroConfidence.textContent = `${data.confidence ?? "--"}%`;

  if (signalValue) signalValue.textContent = String(data.signal || "--").toUpperCase();
  if (confidenceValue) confidenceValue.textContent = `${data.confidence ?? "--"}%`;
  if (emaValue) emaValue.textContent = data.summary_context?.trend || "--";
  if (volumeValue) volumeValue.textContent = data.summary_context?.volume_trend || "--";
  if (summaryText) summaryText.textContent = data.ai_summary || "No summary.";

  if (trendValue) trendValue.textContent = data.summary_context?.trend || "--";
  if (rsiValue) rsiValue.textContent = data.indicators?.rsi ?? "--";
  if (stochValue) stochValue.textContent = data.indicators?.stochastic_rsi_k ?? "--";
  if (mfiValue) mfiValue.textContent = data.indicators?.mfi ?? "--";
  if (macdValue) macdValue.textContent = data.indicators?.macd ?? "--";
  if (riskValue) {
    riskValue.textContent =
      data.confidence >= 72 ? "Controlled" :
      data.confidence <= 45 ? "Aggressive" :
      "Medium";
  }

  if (res1) res1.textContent = data.levels?.resistance_1 ?? "--";
  if (res2) res2.textContent = data.levels?.resistance_2 ?? "--";
  if (pivot) pivot.textContent = data.levels?.pivot ?? "--";
  if (sup1) sup1.textContent = data.levels?.support_1 ?? "--";
  if (sup2) sup2.textContent = data.levels?.support_2 ?? "--";

  if (executionPlan) {
    executionPlan.innerHTML = `
      <p><strong>Asset:</strong> ${data.token || "--"}</p>
      <p><strong>Timeframe:</strong> ${String(data.interval || "--").toUpperCase()}</p>
      <p><strong>Indicator:</strong> ${data.indicator || "--"}</p>
      <p><strong>Live Price:</strong> ${formatPrice(data.current_price)}</p>
      <p><strong>24H Change:</strong> ${formatPct(data.price_change_24h)}</p>
      <p><strong>Bias:</strong> ${data.bias || "--"}</p>
    `;
  }

  if (summaryTags) {
    summaryTags.innerHTML = "";
    buildSummaryTags(data).forEach((tag) => {
      const span = document.createElement("span");
      span.textContent = tag;
      summaryTags.appendChild(span);
    });
  }

  renderWatchlist(data.watchlist || []);
  renderTrending(data.trending || []);

  const mainPath = document.getElementById("mainPath");
  const fillPath = document.getElementById("fillPath");
  const bigMainPath = document.getElementById("bigMainPath");
  const bigFillPath = document.getElementById("bigFillPath");

  const bullishSmall = "M0,190 C40,182 70,165 100,154 C125,145 150,128 180,125 C220,122 245,138 270,116 C298,92 330,80 360,96 C390,112 420,110 445,88 C470,68 500,60 530,72 C560,84 580,98 600,62";
  const bearishSmall = "M0,92 C42,88 84,102 126,110 C170,118 205,138 240,145 C278,152 315,150 350,164 C392,180 430,202 470,198 C515,194 552,160 600,214";
  const bullishBig = "M0,285 C55,270 85,220 130,210 C175,200 220,238 270,205 C320,172 360,145 400,160 C450,180 500,200 555,155 C610,110 650,105 700,125 C760,148 810,185 860,130 C880,112 890,95 900,90";
  const bearishBig = "M0,112 C75,130 144,148 210,166 C266,182 320,205 376,220 C440,238 506,220 576,248 C654,280 748,286 820,312 C850,322 875,330 900,340";

  const smallPath = String(data.bias || "").toLowerCase() === "bearish" ? bearishSmall : bullishSmall;
  const largePath = String(data.bias || "").toLowerCase() === "bearish" ? bearishBig : bullishBig;

  if (mainPath) mainPath.setAttribute("d", smallPath);
  if (fillPath) fillPath.setAttribute("d", fillFromLine(smallPath, false));
  if (bigMainPath) bigMainPath.setAttribute("d", largePath);
  if (bigFillPath) bigFillPath.setAttribute("d", fillFromLine(largePath, true));
}

function setLoadingState(loading) {
  isLoading = loading;

  if (!runAnalysisBtn) return;

  runAnalysisBtn.disabled = loading;
  runAnalysisBtn.textContent = loading ? "Loading..." : "Get Analysis";
}

async function fetchAnalysis(force = false) {
  const now = Date.now();

  if (!force && now - lastFetchAt < FETCH_COOLDOWN_MS) {
    return;
  }

  if (isLoading) {
    return;
  }

  const token = assetSelect?.value || "BTC";
  const interval = timeframeSelect?.value || "1h";
  const indicator = indicatorSelect?.value || "stochasticrsi";

  lastFetchAt = now;
  setLoadingState(true);

  if (currentController) {
    currentController.abort();
  }
  currentController = new AbortController();

  try {
    const url = `/api/technical-analysis?token=${encodeURIComponent(token)}&interval=${encodeURIComponent(interval)}&indicator=${encodeURIComponent(indicator)}`;

    const response = await fetch(url, {
      method: "GET",
      headers: { "Accept": "application/json" },
      signal: currentController.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    renderAnalysis(data);
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }

    console.error("Technical analysis fetch error:", error);

    const summaryText = document.getElementById("summaryText");
    if (summaryText) {
      summaryText.textContent = "Erreur pendant le chargement des données réelles.";
    }
  } finally {
    setLoadingState(false);
  }
}

if (runAnalysisBtn) {
  runAnalysisBtn.addEventListener("click", () => fetchAnalysis(true));
}

// Pas d'auto-fetch sur change pour éviter le spam API
// assetSelect?.addEventListener("change", fetchAnalysis);
// timeframeSelect?.addEventListener("change", fetchAnalysis);
// indicatorSelect?.addEventListener("change", fetchAnalysis);

// Un seul chargement initial
fetchAnalysis(true);