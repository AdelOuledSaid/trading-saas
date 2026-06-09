const assetSelect = document.getElementById("assetSelect");
const timeframeSelect = document.getElementById("timeframeSelect");
const indicatorSelect = document.getElementById("indicatorSelect");
const runAnalysisBtn = document.getElementById("runAnalysisBtn");

const tabButtons = document.querySelectorAll(".ta-tab");
const interactiveCards = document.querySelectorAll(".ta-interactive-card");

const insightModal = document.getElementById("taInsightModal");
const insightClose = document.getElementById("taInsightClose");
const insightBadge = document.getElementById("taInsightBadge");
const insightTitle = document.getElementById("taInsightTitle");
const insightSubtitle = document.getElementById("taInsightSubtitle");
const insightContent = document.getElementById("taInsightContent");

let currentController = null;
let isLoading = false;
let lastFetchAt = 0;
let currentTab = "price";
let lastAnalysisData = null;

const FETCH_COOLDOWN_MS = 3000;

const shellRoot = document.querySelector(".ta-shell");

const accessState = {
  plan: shellRoot?.dataset.userPlan || "free",
  isPremium: shellRoot?.dataset.isPremium === "true",
  isVip: shellRoot?.dataset.isVip === "true",
  telegramLinked: shellRoot?.dataset.telegramLinked === "true",
  upgradeUrl: shellRoot?.dataset.upgradeUrl || "#"
};

function ensureSectionLocked(section) {
  if (!section) return;
  if (accessState.isPremium || accessState.isVip) return;
  if (section.querySelector(".ta-section-lock")) return;
  if (section.querySelector(".ta-card-lock")) return;

  const overlay = document.createElement("div");
  overlay.className = "ta-section-lock";
  overlay.innerHTML = `
    <div class="ta-section-lock-inner">
      <span class="ta-membership-badge ta-membership-badge-premium">PREMIUM</span>
      <strong>Réservé Premium</strong>
      <p>Débloque cette section pour accéder à la lecture avancée.</p>
      <a href="${accessState.upgradeUrl}" class="ta-btn ta-btn-primary ta-lock-cta">Passer Premium</a>
    </div>
  `;

  section.classList.add("ta-force-locked");
  section.appendChild(overlay);
}

function applyMembershipLocks() {
  document.querySelectorAll(".ta-gated-card, [data-required-plan='premium']").forEach((section) => {
    ensureSectionLocked(section);
  });
}

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
  // Arrondir selon la magnitude
  if (num >= 10000)      return "$" + Math.round(num).toLocaleString("en-US");
  if (num >= 1000)       return "$" + num.toLocaleString("en-US", {maximumFractionDigits: 1});
  if (num >= 100)        return "$" + num.toLocaleString("en-US", {maximumFractionDigits: 2});
  if (num >= 1)          return "$" + num.toLocaleString("en-US", {maximumFractionDigits: 3});
  return "$" + num.toLocaleString("en-US", {maximumFractionDigits: 6});
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  return `${num >= 0 ? "+" : ""}${num.toFixed(2)}%`;
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function formatRatio(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function formatText(value, fallback = "--") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function capitalize(value) {
  const text = formatText(value, "");
  if (!text) return "--";

  return text
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function prettifyMarketStructure(value) {
  const map = {
    bullish_trend_structure: "Structure haussière",
    bearish_trend_structure: "Structure baissière",
    neutral_range_structure: "Neutral structure",
    bullish: "Bullish",
    bearish: "Bearish",
    mixed: "Mixte",
    neutral: "Neutral",
    inside_balance: "Internal equilibrium",
    seller_absorption: "Seller absorptioneuse",
    buyer_absorption: "Absorption acheteuse",
    strong_bullish_momentum: "Strong bullish momentum",
    strong_bearish_momentum: "Strong bearish momentum",
    bullish_continuation: "Continuation haussière",
    bearish_continuation: "Continuation baissière",
    reversal_risk: "Risque de retournement",
    supported: "Soutenu",
    positive_cross: "Croisement positif",
    negative_cross: "Croisement négatif",
    normal: "Normal",
    selective: "Selective",
    balanced: "Balanced",
    aggressive: "Agressif",
    defensive: "Défensif",
    weak: "Faible",
    medium: "Moyen",
    strong: "Fort",
    ranging: "En range",
    trending: "Tendance en cours"
  };

  const key = String(value || "").toLowerCase().trim();
  return map[key] || capitalize(value);
}

function showToast(message, success = true) {
  const existing = document.querySelector(".ta-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = `ta-toast ${success ? "success" : "error"}`;
  toast.textContent = message;

  Object.assign(toast.style, {
    position: "fixed",
    right: "18px",
    bottom: "18px",
    zIndex: "9999",
    padding: "12px 16px",
    borderRadius: "12px",
    color: "#fff",
    fontWeight: "700",
    background: success ? "rgba(46, 217, 139, 0.92)" : "rgba(255, 109, 135, 0.92)",
    boxShadow: "0 18px 40px rgba(0,0,0,0.25)"
  });

  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
}

function setText(id, value, fallback = "--") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ?? fallback;
}

function setHTML(id, value, fallback = "") {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = value ?? fallback;
}

function setSignalPill(el, signal) {
  if (!el) return;

  const map = {
    buy: ["Achat", "ta-signal-pill ta-signal-buy"],
    sell: ["Vente", "ta-signal-pill ta-signal-sell"],
    neutral: ["Neutral", "ta-signal-pill ta-signal-neutral"]
  };

  const key = String(signal || "").toLowerCase();
  const [label, cls] = map[key] || map.neutral;

  el.textContent = label;
  el.className = cls;
}

function setBiasBadge(el, bias) {
  if (!el) return;

  const map = {
    bullish: ["Bullish bias", "ta-bias-pill ta-bias-bullish"],
    bearish: ["Bearish bias", "ta-bias-pill ta-bias-bearish"],
    mixed: ["Mixed bias", "ta-bias-pill ta-bias-neutral"],
    neutral: ["Neutral bias", "ta-bias-pill ta-bias-neutral"]
  };

  const key = String(bias || "").toLowerCase();
  const [label, cls] = map[key] || map.mixed;

  el.textContent = label;
  el.className = cls;
}

function getScoreTone(score) {
  const num = Number(score);

  if (Number.isNaN(num)) {
    return {
      label: "Neutral",
      color: "var(--ta-gold)",
      className: "ta-neutral-text"
    };
  }

  if (num >= 70) {
    return {
      label: "Bullish",
      color: "var(--ta-green)",
      className: "ta-bullish-text"
    };
  }

  if (num <= 40) {
    return {
      label: "Bearish",
      color: "var(--ta-red)",
      className: "ta-bearish-text"
    };
  }

  return {
    label: "Neutral",
    color: "var(--ta-gold)",
    className: "ta-neutral-text"
  };
}

function updateScoreGauge(score) {
  const gauge = document.getElementById("scoreGauge");
  const progress = document.getElementById("scoreGaugeProgress");
  const valueEl = document.getElementById("heroConfidence");
  const labelEl = document.getElementById("heroConfidenceLabel");

  if (!gauge || !progress || !valueEl || !labelEl) return;

  const num = Number(score);
  const safeScore = Number.isNaN(num) ? 0 : Math.max(0, Math.min(100, num));
  const tone = getScoreTone(safeScore);

  gauge.dataset.score = safeScore;
  valueEl.textContent = `${safeScore}`;
  labelEl.textContent = tone.label;

  progress.style.stroke = tone.color;
  progress.style.strokeDashoffset = `${100 - safeScore}`;

  valueEl.classList.remove("ta-bullish-text", "ta-bearish-text", "ta-neutral-text");
  labelEl.classList.remove("ta-bullish-text", "ta-bearish-text", "ta-neutral-text");

  valueEl.classList.add(tone.className);
  labelEl.classList.add(tone.className);
}

function applyDirectionalCardState(elementId, value) {
  const el = document.getElementById(elementId);
  if (!el) return;

  const text = String(value || "").toLowerCase();
  const card = el.closest(".ta-tv-mini-stat, .ta-tv-confluence-box, .ta-mtf-card, .ta-orderflow-box, .ta-mini-box, .ta-level-box");

  el.classList.remove("ta-bullish-text", "ta-bearish-text", "ta-neutral-text");
  if (card) {
    card.classList.remove("ta-bullish-card", "ta-bearish-card", "ta-neutral-card");
  }

  if (text.includes("bull") || text.includes("hauss")) {
    el.classList.add("ta-bullish-text");
    if (card) card.classList.add("ta-bullish-card");
  } else if (text.includes("bear") || text.includes("baiss")) {
    el.classList.add("ta-bearish-text");
    if (card) card.classList.add("ta-bearish-card");
  } else {
    el.classList.add("ta-neutral-text");
    if (card) card.classList.add("ta-neutral-card");
  }
}

function buildSummaryTags(data) {
  const tags = [];
  const confluenceScore = data?.multi_timeframe?.confluence?.score;
  const orderflowState = data?.orderflow?.state;
  const replayCount = data?.setup_replay?.count;

  if (data.signal) tags.push(String(data.signal).toUpperCase());
  if (data.indicator) tags.push(String(data.indicator).toUpperCase());
  if (data.summary_context?.trend) tags.push(prettifyMarketStructure(data.summary_context.trend));
  if (data.summary_context?.volume_trend) tags.push(`VOL ${capitalize(data.summary_context.volume_trend)}`);
  if (confluenceScore !== undefined && confluenceScore !== null) tags.push(`CONF ${confluenceScore}`);
  if (orderflowState) tags.push(prettifyMarketStructure(orderflowState));
  if (replayCount !== undefined && replayCount !== null) tags.push(`REPLAY ${replayCount}`);

  return tags.slice(0, 6);
}

function renderWatchlist(items) {
  const container = document.getElementById("watchlistContainer");
  if (!container) return;

  container.innerHTML = "";

  (items || []).slice(0, 8).forEach((item) => {
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
          <strong>Données limitées</strong>
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
        ${Number(item.change_24h) >= 0 ? "Positive" : "Surveille"}
      </span>
    `;
    container.appendChild(row);
  });

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="ta-indicator-row">
        <div>
          <strong>Market trend unavailable</strong>
          <p>Temporarily limited list.</p>
        </div>
        <span class="ta-status-chip gold">Limited</span>
      </div>
    `;
  }
}

function normalizeSeries(series, minTarget = 90, maxTarget = 300) {
  if (!series || !series.length) return [];
  const nums = series.map((v) => Number(v)).filter((v) => !Number.isNaN(v));
  if (!nums.length) return [];

  const min = Math.min(...nums);
  const max = Math.max(...nums);

  if (max === min) {
    return nums.map(() => (minTarget + maxTarget) / 2);
  }

  return nums.map((v) => {
    const ratio = (v - min) / (max - min);
    return maxTarget - ratio * (maxTarget - minTarget);
  });
}

function buildSvgPathFromSeries(series, width = 900, minY = 90, maxY = 300) {
  if (!series || series.length < 2) return "";

  const normalized = normalizeSeries(series, minY, maxY);
  if (normalized.length < 2) return "";

  const stepX = width / (normalized.length - 1);
  let path = `M0,${normalized[0].toFixed(2)}`;

  for (let i = 1; i < normalized.length; i += 1) {
    const x = i * stepX;
    const y = normalized[i];
    path += ` L${x.toFixed(2)},${y.toFixed(2)}`;
  }

  return path;
}

function buildFillPath(path, width = 900, height = 380) {
  if (!path) return "";
  return `${path} L${width},${height} L0,${height} Z`;
}

function renderBigChartByTab(data, tabName) {
  const bigMainPath = document.getElementById("bigMainPath");
  const bigFillPath = document.getElementById("bigFillPath");
  if (!bigMainPath || !bigFillPath) return;

  const series = data?.chart_series || {};
  let selectedSeries = [];

  if (tabName === "rsi") {
    selectedSeries = series.rsi || [];
  } else if (tabName === "mfi") {
    selectedSeries = series.mfi || [];
  } else {
    selectedSeries = series.price || [];
  }

  const path = buildSvgPathFromSeries(selectedSeries, 900, 90, 300);
  if (!path) return;

  bigMainPath.setAttribute("d", path);
  bigFillPath.setAttribute("d", buildFillPath(path, 900, 380));
}

function setActiveTab(tabName) {
  currentTab = tabName;
  tabButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });

  if (lastAnalysisData) {
    renderBigChartByTab(lastAnalysisData, currentTab);
  }
}

function openInsightModal({ tier, title, subtitle, html }) {
  if (!insightModal || !insightContent || !insightBadge || !insightTitle || !insightSubtitle) return;

  insightBadge.textContent = tier.toUpperCase();
  insightBadge.className = "ta-insight-badge ta-membership-badge-premium";
  insightTitle.textContent = title;
  insightSubtitle.textContent = subtitle;
  insightContent.innerHTML = html;

  insightModal.classList.add("is-open");
  insightModal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeInsightModal() {
  if (!insightModal) return;
  insightModal.classList.remove("is-open");
  insightModal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

function getTf(data, tf) {
  return data?.multi_timeframe?.timeframes?.[tf] || {};
}

function buildTfBox(label, tfData) {
  return `
    <div class="ta-insight-box">
      <span>${label}</span>
      <strong>${prettifyMarketStructure(tfData.bias || tfData.trend || "unknown")}</strong>
      <small>RSI ${tfData.rsi ?? "--"} · Conf ${tfData.confidence ?? "--"}</small>
    </div>
  `;
}

function buildReplayRows(replay) {
  const rows = replay?.last_setups || [];
  if (!rows.length) {
    return "<p>Aucun replay disponible pour le moment.</p>";
  }

  return `
    <div class="ta-insight-replay">
      ${rows.map((row) => `
        <div class="ta-insight-box">
          <span>${formatText(row.interval).toUpperCase()} • ${formatText(row.signal).toUpperCase()}</span>
          <strong>${prettifyMarketStructure(row.bias)}</strong>
          <small>Conf ${row.confidence ?? "--"} · Outcome ${row.simulated_outcome_pct ?? "--"}%</small>
        </div>
      `).join("")}
    </div>
  `;
}

function buildInsightContent(type, data) {
  const rsi = data?.indicators?.rsi ?? "--";
  const mfi = data?.indicators?.mfi ?? "--";
  const macd = data?.indicators?.macd ?? "--";
  const confidence = data?.confidence ?? "--";
  const trend = data?.summary_context?.trend ?? "--";
  const orderflow = data?.orderflow || {};
  const confluence = data?.multi_timeframe?.confluence || {};
  const premium = data?.premium || {};
  const replay = data?.setup_replay || {};

  const tf15m = getTf(data, "15m");
  const tf1h = getTf(data, "1h");
  const tf4h = getTf(data, "4h");
  const tf1d = getTf(data, "1d");

  const map = {
    "premium-alignment": {
      tier: "premium",
      title: "Confluence multi-timeframe",
      subtitle: "Lecture alignée des horizons de temps",
      html: `
        <p>Confluence score: <strong>${confluence.score ?? data?.multi_timeframe?.confluence?.score ?? "--"}</strong> · Dominant bias: <strong>${prettifyMarketStructure(confluence.dominant_bias)}</strong></p>
        <div class="ta-insight-grid">
          ${buildTfBox("15M", tf15m)}
          ${buildTfBox("1H", tf1h)}
          ${buildTfBox("4H", tf4h)}
          ${buildTfBox("1D", tf1d)}
        </div>
        <ul class="ta-insight-list">
          <li>Alignement: ${prettifyMarketStructure(confluence.alignment)}</li>
          <li>Qualité d'entrée: ${prettifyMarketStructure(confluence.entry_quality ?? data?.multi_timeframe?.confluence?.entry_quality)}</li>
          <li>Orderflow: ${prettifyMarketStructure(orderflow.state)}</li>
        </ul>
      `
    },
    "premium-breakdown": {
      tier: "premium",
      title: "Breakdown indicateurs",
      subtitle: "Lecture détaillée du momentum et des signaux",
      html: `
        <div class="ta-insight-grid">
          <div class="ta-insight-box"><span>RSI</span><strong>${rsi}</strong></div>
          <div class="ta-insight-box"><span>MFI</span><strong>${mfi}</strong></div>
          <div class="ta-insight-box"><span>MACD</span><strong>${macd}</strong></div>
          <div class="ta-insight-box"><span>Confiance</span><strong>${confidence}%</strong></div>
          <div class="ta-insight-box"><span>État RSI</span><strong>${prettifyMarketStructure(premium?.indicator_breakdown?.rsi_state)}</strong></div>
          <div class="ta-insight-box"><span>État MFI</span><strong>${prettifyMarketStructure(premium?.indicator_breakdown?.mfi_state)}</strong></div>
          <div class="ta-insight-box"><span>Régime MACD</span><strong>${prettifyMarketStructure(premium?.indicator_breakdown?.macd_regime)}</strong></div>
          <div class="ta-insight-box"><span>Qualité volume</span><strong>${prettifyMarketStructure(premium?.indicator_breakdown?.volume_quality)}</strong></div>
        </div>
      `
    },
    "premium-ai": {
      tier: "premium",
      title: "Contexte IA premium",
      subtitle: "Lecture enrichie du desk",
      html: `
        <p>${premium?.premium_ai_context || data?.ai_summary || "Aucun contexte IA disponible."}</p>
        <ul class="ta-insight-list">
          <li>Régime de tendance: ${prettifyMarketStructure(trend)}</li>
          <li>Bias: ${prettifyMarketStructure(data?.bias)}</li>
          <li>Confiance exécution: ${confidence}%</li>
          <li>Force orderflow: ${orderflow?.strength ?? "--"}</li>
        </ul>
        ${buildReplayRows(replay)}
      `
    }
  };

  return map[type] || {
    tier: "premium",
    title: "Insight avancé",
    subtitle: "Lecture du desk",
    html: "<p>Aucun insight disponible.</p>"
  };
}

function renderConfluencePanel(data) {
  const confluence = data?.multi_timeframe?.confluence || {};

  setText("confluenceScore", confluence.score ?? "--");
  setText("confluenceBias", prettifyMarketStructure(confluence.dominant_bias));
  setText("confluenceAlignment", prettifyMarketStructure(confluence.alignment));
  setText("confluenceEntryQuality", prettifyMarketStructure(confluence.entry_quality));

  setText("sideConfluenceScore", confluence.score ?? "--");
  setText("sideConfluenceLabel", prettifyMarketStructure(confluence.entry_quality || "Pas de donnée"));
}

function renderTimeframeCard(tfName, biasId, metaId, data) {
  const tf = getTf(data, tfName);
  // Si pas de données MTF, utiliser le biais principal comme fallback
  const tfBias = tf.bias || tf.trend || null;
  if (!tfBias) {
    setText(biasId, prettifyMarketStructure(data?.bias || "neutral"));
    setText(metaId, "No MTF data");
  } else {
    setText(biasId, prettifyMarketStructure(tfBias));
    setText(metaId, `RSI ${tf.rsi ?? "--"} · Conf ${tf.confidence ?? "--"}`);
  }
}

function renderMultiTimeframeSummary(data) {
  renderTimeframeCard("15m", "mtf15mBias", "mtf15mMeta", data);
  renderTimeframeCard("1h", "mtf1hBias", "mtf1hMeta", data);
  renderTimeframeCard("4h", "mtf4hBias", "mtf4hMeta", data);
  renderTimeframeCard("1d", "mtf1dBias", "mtf1dMeta", data);

  const tf15m = getTf(data, "15m");
  const tf1h = getTf(data, "1h");
  const tf4h = getTf(data, "4h");
  const tf1d = getTf(data, "1d");

  setText("premiumBias15m", prettifyMarketStructure(tf15m.bias || tf15m.trend || "unknown"));
  setText("premiumBias1h", prettifyMarketStructure(tf1h.bias || tf1h.trend || "unknown"));
  setText("premiumBias4h", prettifyMarketStructure(tf4h.bias || tf4h.trend || "unknown"));
  setText("premiumBias1d", prettifyMarketStructure(tf1d.bias || tf1d.trend || "unknown"));
}

function renderOrderflowPanel(data) {
  const orderflow = data?.orderflow || {};

  setText("orderflowState", prettifyMarketStructure(orderflow.state));
  setText("orderflowStrength", orderflow.strength ?? "--");
  setText("orderflowImbalance", prettifyMarketStructure(orderflow.imbalance));
  setText("orderflowAbsorption", prettifyMarketStructure(orderflow.absorption));
  setText("buyPressureValue", formatNumber(orderflow.buy_pressure, 2));
  setText("sellPressureValue", formatNumber(orderflow.sell_pressure, 2));

  setText("buyerAggression", `${formatNumber(orderflow.buyer_aggression, 2)} / 100`);
  setText("sellerAggression", `${formatNumber(orderflow.seller_aggression, 2)} / 100`);
  setText("bodyRatio", formatRatio(orderflow.body_ratio, 3));
  setText("closePosition", formatRatio(orderflow.close_position, 3));
  setText("upperWickRatio", formatRatio(orderflow.upper_wick_ratio, 3));
  setText("lowerWickRatio", formatRatio(orderflow.lower_wick_ratio, 3));
  setText("volumeAcceleration", `${formatRatio(orderflow.volume_acceleration, 2)}x`);
  setText("orderflowExhaustion", orderflow.exhaustion ? "Oui" : "Non");

  setText("sideOrderflowState", prettifyMarketStructure(orderflow.state));
  setText("sideOrderflowStrength", `Force ${orderflow.strength ?? "--"}`);
}

function renderReplayPanel(data) {
  const replay = data?.setup_replay || {};
  const historyEl = document.getElementById("replayHistory");

  setText("replayCount", replay.count ?? "--");
  setText("replayWinrate", replay.winrate !== null && replay.winrate !== undefined ? `${replay.winrate}%` : "--");
  setText("replayAvgConfidence", replay.avg_confidence !== null && replay.avg_confidence !== undefined ? `${replay.avg_confidence}%` : "--");
  setText("replayBestBias", prettifyMarketStructure(replay.best_bias));

  setText("sideReplayWinrate", replay.winrate !== null && replay.winrate !== undefined ? `${replay.winrate}%` : "--");
  setText("sideReplayCount", `${replay.count ?? 0} setup${Number(replay.count) > 1 ? "s" : ""}`);

  if (!historyEl) return;

  const rows = replay?.last_setups || [];
  if (!rows.length) {
    historyEl.innerHTML = "<p>Aucun replay chargé.</p>";
    return;
  }

  historyEl.innerHTML = rows.map((row) => `
    <div class="ta-indicator-row">
      <div>
        <strong>${formatText(row.signal).toUpperCase()} • ${formatText(row.interval).toUpperCase()}</strong>
        <p>Bias: ${prettifyMarketStructure(row.bias)} · Conf: ${row.confidence ?? "--"} · Outcome: ${row.simulated_outcome_pct ?? "--"}%</p>
      </div>
      <span class="ta-status-chip ${Number(row.simulated_outcome_pct) >= 0 ? "green" : "gold"}">
        ${Number(row.simulated_outcome_pct) >= 0 ? "Positif" : "Surveille"}
      </span>
    </div>
  `).join("");
}

function renderTelegramPanel(data) {
  const premium = data?.premium || {};

  setText("telegramLinked", accessState.telegramLinked ? "Oui" : "Non");
  setText("telegramReady", premium.telegram_alert_candidate ? "Oui" : "Non");
  setText("telegramExecutionMode", prettifyMarketStructure(premium.execution_mode || "selective"));
  setText("telegramRiskProfile", prettifyMarketStructure(premium.risk_profile || "balanced"));
  setText(
    "telegramNote",
    premium.telegram_alert_candidate
      ? "Les conditions d’alerte premium sont alignées. Le setup est prêt pour l’automation."
      : "Les conditions de l’alerte premium ne sont pas encore totalement alignées."
  );
}

function renderPremiumBlocks(data) {
  const premium = data?.premium || {};
  const replay = data?.setup_replay || {};
  const orderflow = data?.orderflow || {};
  const confluence = data?.multi_timeframe?.confluence || {};

  setText("premiumRsiState", prettifyMarketStructure(premium?.indicator_breakdown?.rsi_state || "unknown"));
  setText("premiumMfiState", prettifyMarketStructure(premium?.indicator_breakdown?.mfi_state || "unknown"));
  setText("premiumMacdState", prettifyMarketStructure(premium?.indicator_breakdown?.macd_regime || "unknown"));
  setText(
    "premiumVolumeState",
    prettifyMarketStructure(premium?.indicator_breakdown?.volume_quality || data?.summary_context?.volume_trend || "unknown")
  );
  setText("premiumAiSummary", premium?.premium_ai_context || data?.ai_summary || "Aucun contexte premium disponible.");

  // Entry / TP / SL dans le plan side
  const _planEntry = data?.levels?.pivot ?? data?.current_price ?? null;
  const _planTp = data?.levels?.resistance_1 ?? null;
  const _planSl = data?.levels?.support_1 ?? null;
  setText("planEntry", _planEntry ? formatPrice(_planEntry) : "--");
  setText("planTp",    _planTp    ? formatPrice(_planTp)    : "--");
  setText("planSl",    _planSl    ? formatPrice(_planSl)    : "--");
  setText("vipExecutionMode", prettifyMarketStructure(premium?.execution_mode || "selective"));
  setText("vipRiskProfile", prettifyMarketStructure(premium?.risk_profile || "balanced"));
  setText(
    "vipBullScenario",
    premium?.bullish_scenario || `Continuation haussière au-dessus du pivot ${data?.levels?.pivot ?? "--"} avec amélioration du flux.`
  );
  setText(
    "vipBearScenario",
    premium?.bearish_scenario || `Pression vendeuse valide sous ${data?.levels?.resistance_1 ?? "--"} si le support cède.`
  );
  setText(
    "vipNeutralScenario",
    premium?.neutral_scenario || "Neutral regime as long as confluence remains mixed and the market lacks momentum."
  );
  setText(
    "vipDeskNotes",
    premium?.desk_notes ||
      `Desk reading: bias ${prettifyMarketStructure(data?.bias || "mixed")}, confluence ${confluence?.score ?? "--"}, replay ${replay?.winrate ?? "--"}%, flow ${prettifyMarketStructure(orderflow.state)}.`
  );
}

function cleanStructureText(raw) {
  if (!raw) return "--";
  return raw
    .replace(/\s*\|\s*(Location|Score|location|score|Conf|conf)=[\d.]+/gi, "")
    .replace(/\s*\|\s*[\w_]+=[\w\d._-]+/g, "")
    .replace(/\s*\|+\s*/g, " ")
    .trim();
}

function cleanExecutionNote(raw) {
  if (!raw) return "";
  if (!raw.includes("signal=") && !raw.includes("bias=")) {
    return raw.replace(/_/g, " ");
  }
  const parts = {};
  raw.split("|").forEach(function(p) {
    var kv = p.trim().split("=");
    if (kv.length >= 2) parts[kv[0].trim()] = kv.slice(1).join("=").trim();
  });
  var lines = [];
  if (parts.signal)     lines.push("Signal: <strong>" + parts.signal.toUpperCase() + "</strong>");
  if (parts.bias)       lines.push("Bias: <strong>" + parts.bias + "</strong>");
  if (parts.confidence) lines.push("Confidence: <strong>" + parts.confidence + "%</strong>");
  if (parts.trend)      lines.push("Trend: <strong>" + parts.trend + "</strong>");
  if (parts.RSI)        lines.push("RSI: <strong>" + parts.RSI + "</strong>");
  if (parts.MFI)        lines.push("MFI: <strong>" + parts.MFI + "</strong>");
  if (parts.orderflow)  lines.push("Orderflow: <strong>" + parts.orderflow.replace(/_/g," ") + "</strong>");
  if (parts.volatility) lines.push("Volatility: <strong>" + parts.volatility + "</strong>");
  var result = lines.join(" &nbsp;&middot;&nbsp; ");
  var execStyle = raw.split("Execution style:");
  if (execStyle.length > 1) {
    result += "<br><em style='color:#b2b5be;font-size:11px;'>Execution style: " + execStyle[1].split("Replay")[0].trim() + "</em>";
  }
  var replayMem = raw.split("Replay memory:");
  if (replayMem.length > 1) {
    result += "<br><span style='font-size:11px;color:#787b86;'>Replay: " + replayMem[1].trim() + "</span>";
  }
  return result;
}

function renderAdvancedAI(data) {
  const adv = data?.ai_advanced_analysis || {};
  const simulated = adv?.simulated_orderflow || {};
  const tradePlan = adv?.trade_plan || {};
  const advancedAiBias = document.getElementById("advancedAiBias");

  setBiasBadge(advancedAiBias, tradePlan.bias || data?.bias || "mixed");

  const rawStructure = adv.market_structure || data?.summary_context?.market_structure || data?.summary_context?.trend || "unknown";
  const structure     = cleanStructureText(rawStructure);
  const momentum      = cleanStructureText(adv.momentum || data?.summary_context?.momentum_regime || "neutral");
  const location      = adv.location_score ?? adv.location ?? null;
  const score         = adv.score ?? null;
  const momentumScore = adv.momentum_score ?? score ?? null;

  function scoreColor(s) { return s >= 70 ? "#26a69a" : s >= 50 ? "#f57c00" : "#ef5350"; }
  function scoreBadge(s) {
    if (s === null) return "";
    return '<span style="display:inline-block;font-size:11px;font-weight:700;color:' + scoreColor(s) + ';background:rgba(255,255,255,0.05);padding:2px 7px;border-radius:4px;margin-top:4px;">' + s + '</span>';
  }

  setHTML("aiMarketStructure",
    '<span style="font-size:14px;font-weight:700;color:#d1d4dc;display:block;margin-bottom:4px;">' + prettifyMarketStructure(structure) + '</span>' +
    (location !== null ? '<span style="font-size:11px;color:#787b86;">Loc <strong style="color:#b2b5be;">' + Number(location).toFixed(2) + '</strong></span>' : "") +
    scoreBadge(score)
  );

  setHTML("aiMomentum",
    '<span style="font-size:14px;font-weight:700;color:#d1d4dc;display:block;margin-bottom:4px;">' + prettifyMarketStructure(momentum) + '</span>' +
    scoreBadge(momentumScore)
  );

  setHTML("aiDeltaPressure",
    '<span style="font-size:14px;font-weight:700;color:#d1d4dc;">' +
    prettifyMarketStructure(simulated.delta_pressure || data?.orderflow?.delta_pressure || "balanced_pressure") + '</span>'
  );

  setHTML("aiImbalanceZone",
    '<span style="font-size:14px;font-weight:700;color:#d1d4dc;">' +
    prettifyMarketStructure(simulated.imbalance_zone || data?.orderflow?.imbalance_zone || "inside_balance") + '</span>'
  );

  const rawNote = adv.execution_note || data?.premium?.premium_ai_context || data?.ai_summary || "";
  setHTML("aiExecutionNote", cleanExecutionNote(rawNote) || "No execution note loaded.");

  const rawInval = adv.invalidation || "";
  setText("aiInvalidation", rawInval.replace(/_/g, " ") || "No invalidation loaded.");
}

function renderExecutionPlan(data) {
  const executionPlan = document.getElementById("executionPlan");
  if (!executionPlan) return;

  const confluence = data?.multi_timeframe?.confluence || {};
  const orderflow = data?.orderflow || {};
  const replay = data?.setup_replay || {};
  const premium = data?.premium || {};
  const adv = data?.ai_advanced_analysis || {};
  const tradePlan = adv?.trade_plan || {};

  const score = premium?.score ?? data.confidence ?? 0;
  const scoreColor = score >= 70 ? "#26a69a" : score >= 40 ? "#f57c00" : "#ef5350";
  const changeVal = data.price_change_24h ?? 0;
  const changeColor = changeVal >= 0 ? "#26a69a" : "#ef5350";
  const changeSign = ""; // formatPct gère déjà le signe
  const userPlan = window.VELWOLEF_CONFIG?.plan 
    || document.querySelector(".ta-shell-tv")?.dataset?.userPlan 
    || "free";
  const isPremium = ["basic", "premium", "vip"].includes(userPlan);

  executionPlan.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
      <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:10px 12px;">
        <div style="font-size:10px;color:#787b86;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Asset</div>
        <div style="font-size:16px;font-weight:700;color:#d1d4dc;">${data.token || "--"}</div>
      </div>
      <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:10px 12px;">
        <div style="font-size:10px;color:#787b86;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Live price</div>
        <div style="font-size:15px;font-weight:700;color:#d1d4dc;">${formatPrice(data.current_price)}</div>
        <div style="font-size:11px;font-weight:600;color:${changeColor};">${changeSign}${formatPct(data.price_change_24h)}</div>
      </div>
      <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:10px 12px;">
        <div style="font-size:10px;color:#787b86;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Timeframe</div>
        <div style="font-size:15px;font-weight:700;color:#d1d4dc;">${String(data.interval || "--").toUpperCase()}</div>
      </div>
      <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:10px 12px;">
        <div style="font-size:10px;color:#787b86;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Indicator</div>
        <div style="font-size:13px;font-weight:600;color:#d1d4dc;">${data.indicator || "--"}</div>
      </div>
    </div>

    ${isPremium ? `
    <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:12px 14px;margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-size:10px;color:#787b86;text-transform:uppercase;letter-spacing:.5px;">AI Score</span>
        <span style="font-size:18px;font-weight:800;color:${scoreColor};">${score} <span style="font-size:12px;color:#787b86;font-weight:400;">/ 100</span></span>
      </div>
      <div style="height:4px;background:#2a2e39;border-radius:2px;overflow:hidden;">
        <div style="height:100%;width:${score}%;background:${scoreColor};border-radius:2px;transition:width .4s;"></div>
      </div>
    </div>` : `
    <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:12px 14px;margin-bottom:8px;text-align:center;">
      <div style="font-size:22px;margin-bottom:6px;">🔒</div>
      <div style="font-size:12px;font-weight:700;color:#d1d4dc;margin-bottom:4px;">AI Score — Premium</div>
      <div style="font-size:11px;color:#787b86;">Available on Basic, Premium & VIP plans</div>
      <a href="pricing" style="display:inline-block;margin-top:10px;padding:6px 16px;background:#2962ff;color:#fff;border-radius:4px;font-size:11px;font-weight:700;text-decoration:none;">See offers →</a>
    </div>`}

    <div style="display:flex;flex-direction:column;gap:1px;background:#2a2e39;border-radius:8px;overflow:hidden;">
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Bias</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${prettifyMarketStructure(data.bias)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Confluence score</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${confluence.score ?? data?.multi_timeframe?.confluence?.score ?? "--"}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Entry quality</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${prettifyMarketStructure(confluence.entry_quality ?? data?.multi_timeframe?.confluence?.entry_quality)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Orderflow</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${prettifyMarketStructure(orderflow.state)} (${orderflow.strength ?? "--"})</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Replay winrate</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${isPremium ? (replay.winrate ?? data?.setup_replay?.winrate ?? "--") + "%" : "🔒"}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Execution mode</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${prettifyMarketStructure(premium.execution_mode || "selective")}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 12px;background:#1e222d;">
        <span style="color:#787b86;font-size:12px;">Plan confidence</span>
        <span style="color:#d1d4dc;font-weight:600;font-size:12px;">${tradePlan.confidence ?? data.confidence ?? "--"}%</span>
      </div>
    </div>
  `;
}

function renderAnalysis(data) {
  const heroSignal = document.getElementById("heroSignal");
  const biasBadge = document.getElementById("biasBadge");
  const summaryTags = document.getElementById("summaryTags");
  const premium = data?.premium || {};

  setText("heroAsset", data.token || "--");
  setSignalPill(heroSignal, data.signal);
  setBiasBadge(biasBadge, data.bias);

  setText("heroPrice", formatPrice(data.current_price));
  setText("heroMarketCap", formatMoney(data.market_cap));
  setText("heroVolume", formatMoney(data.volume_24h));

  // Score : confidence est toujours calculé, premium.score seulement pour VIP
  const deskScore = (premium?.score && premium.score > 0)
    ? premium.score
    : (data?.ai_advanced_analysis?.trade_plan?.confidence && data.ai_advanced_analysis.trade_plan.confidence > 0)
    ? data.ai_advanced_analysis.trade_plan.confidence
    : (data.confidence && data.confidence > 0)
    ? data.confidence
    : 0;
  updateScoreGauge(deskScore);

  setText("heroTrend", prettifyMarketStructure(data.summary_context?.trend));
  setText("heroRsi", data.indicators?.rsi ?? "--");
  setText("heroMfi", data.indicators?.mfi ?? "--");
  setText("heroDeskMode", prettifyMarketStructure(premium.execution_mode || "neutral"));

  setText("signalValue", String(data.signal || "--").toUpperCase());
  setText("confidenceValue", `${data.confidence ?? "--"}%`);
  setText("volumeValue", prettifyMarketStructure(data.summary_context?.volume_trend));
  setText("summaryText", data.ai_summary || data?.premium?.premium_ai_context || "Aucun résumé disponible.");

  setText("trendValue", prettifyMarketStructure(data.summary_context?.trend));
  setText("rsiValue", data.indicators?.rsi ?? "--");
  setText("stochValue", data.indicators?.stochastic_rsi_k ?? "--");
  setText("mfiValue", data.indicators?.mfi ?? "--");
  setText("macdValue", data.indicators?.macd ?? "--");
  setText("riskValue", prettifyMarketStructure(premium?.risk_profile || "medium"));

  setText("res1",  data.levels?.resistance_1 ? formatPrice(data.levels.resistance_1) : "--");
  setText("res2",  data.levels?.resistance_2 ? formatPrice(data.levels.resistance_2) : "--");
  setText("pivot", data.levels?.pivot        ? formatPrice(data.levels.pivot)        : "--");
  setText("sup1",  data.levels?.support_1    ? formatPrice(data.levels.support_1)    : "--");
  setText("sup2",  data.levels?.support_2    ? formatPrice(data.levels.support_2)    : "--");

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
  renderConfluencePanel(data);
  renderMultiTimeframeSummary(data);
  renderOrderflowPanel(data);
  renderReplayPanel(data);
  renderTelegramPanel(data);
  renderPremiumBlocks(data);
  renderAdvancedAI(data);
  renderExecutionPlan(data);

  applyDirectionalCardState("heroTrend", data.summary_context?.trend);
  applyDirectionalCardState("trendValue", data.summary_context?.trend);
  applyDirectionalCardState("confluenceBias", data.multi_timeframe?.confluence?.dominant_bias);
  applyDirectionalCardState("mtf15mBias", getTf(data, "15m")?.bias || getTf(data, "15m")?.trend);
  applyDirectionalCardState("mtf1hBias", getTf(data, "1h")?.bias || getTf(data, "1h")?.trend);
  applyDirectionalCardState("mtf4hBias", getTf(data, "4h")?.bias || getTf(data, "4h")?.trend);
  applyDirectionalCardState("mtf1dBias", getTf(data, "1d")?.bias || getTf(data, "1d")?.trend);
  applyDirectionalCardState("orderflowState", data.orderflow?.state);
  applyDirectionalCardState("premiumBias15m", getTf(data, "15m")?.bias || getTf(data, "15m")?.trend);
  applyDirectionalCardState("premiumBias1h", getTf(data, "1h")?.bias || getTf(data, "1h")?.trend);
  applyDirectionalCardState("premiumBias4h", getTf(data, "4h")?.bias || getTf(data, "4h")?.trend);
  applyDirectionalCardState("premiumBias1d", getTf(data, "1d")?.bias || getTf(data, "1d")?.trend);

  lastAnalysisData = data;
  renderBigChartByTab(data, currentTab);
}

function setLoadingState(loading) {
  isLoading = loading;
  if (!runAnalysisBtn) return;

  runAnalysisBtn.disabled = loading;
  runAnalysisBtn.textContent = loading ? "Chargement..." : "Lancer l'analyse";
}

async function fetchAnalysis(force = false) {
  const now = Date.now();

  if (!force && now - lastFetchAt < FETCH_COOLDOWN_MS) {
    showToast("Attends quelques secondes avant une nouvelle analyse.", false);
    return;
  }

  if (isLoading) return;

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
      headers: { Accept: "application/json" },
      signal: currentController.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    renderAnalysis(data);
    showToast("Analyse chargée avec succès.");
  } catch (error) {
    if (error.name === "AbortError") return;

    console.error("Technical analysis fetch error:", error);
    setText("summaryText", "Erreur pendant le chargement des données.");
    setText("aiExecutionNote", "La lecture avancée n’a pas pu être chargée.");
    setText("aiInvalidation", "Aucune invalidation disponible.");
    showToast("Erreur de chargement de l'analyse.", false);
  } finally {
    setLoadingState(false);
  }
}

if (runAnalysisBtn) {
  runAnalysisBtn.addEventListener("click", () => fetchAnalysis(false));
}

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    setActiveTab(btn.dataset.tab);
  });
});

interactiveCards.forEach((card) => {
  card.addEventListener("click", () => {
    const type = card.dataset.insight;
    const content = buildInsightContent(type, lastAnalysisData || {});
    openInsightModal(content);
  });
});

insightClose?.addEventListener("click", closeInsightModal);

insightModal?.addEventListener("click", (e) => {
  if (e.target.dataset.close === "true") {
    closeInsightModal();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeInsightModal();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  applyMembershipLocks();
  setActiveTab(currentTab);

  // Chargement automatique de l'analyse au démarrage
  setTimeout(() => {
    fetchAnalysis(true);
  }, 600);
});