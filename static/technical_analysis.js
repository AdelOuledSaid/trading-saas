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

const FETCH_COOLDOWN_MS = 4000;

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

  if (Math.abs(num) >= 1000) {
    return `$${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
  if (Math.abs(num) >= 1) {
    return `$${num.toFixed(4)}`;
  }
  return `$${num.toFixed(6)}`;
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
  setTimeout(() => toast.remove(), 3000);
}

function setText(id, value, fallback = "--") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ?? fallback;
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
  const [label, cls] = map[key] || map.mixed;

  el.textContent = label;
  el.className = `ta-bias-pill ${cls}`;
}

function buildSummaryTags(data) {
  const tags = [];
  const confluenceScore = data?.multi_timeframe?.confluence?.score;
  const orderflowState = data?.orderflow?.state;
  const replayCount = data?.setup_replay?.count;

  if (data.signal) tags.push(String(data.signal).toUpperCase());
  if (data.indicator) tags.push(String(data.indicator).toUpperCase());
  if (data.summary_context?.trend) tags.push(String(data.summary_context.trend).toUpperCase());
  if (data.summary_context?.volume_trend) tags.push(`VOL ${String(data.summary_context.volume_trend).toUpperCase()}`);
  if (confluenceScore !== undefined) tags.push(`CONF ${confluenceScore}`);
  if (orderflowState) tags.push(capitalize(orderflowState));
  if (replayCount !== undefined && replayCount !== null) tags.push(`REPLAY ${replayCount}`);

  return tags.slice(0, 6);
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

function buildSvgPathFromSeries(series, width = 900) {
  if (!series || series.length < 2) return "";

  const normalized = normalizeSeries(series);
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

  const series = data.chart_series || {};
  let selectedSeries = [];

  if (tabName === "rsi") {
    selectedSeries = series.rsi || [];
  } else if (tabName === "mfi") {
    selectedSeries = series.mfi || [];
  } else {
    selectedSeries = series.price || [];
  }

  const path = buildSvgPathFromSeries(selectedSeries, 900);
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
  if (!insightModal || !insightContent) return;

  insightBadge.textContent = tier.toUpperCase();
  insightBadge.className = `ta-insight-badge ${tier === "vip" ? "ta-membership-badge-vip" : "ta-membership-badge-premium"}`;
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
      <strong>${capitalize(tfData.bias || tfData.trend || "unknown")}</strong>
      <small>RSI ${tfData.rsi ?? "--"} · Conf ${tfData.confidence ?? "--"}</small>
    </div>
  `;
}

function buildReplayRows(replay) {
  const rows = replay?.last_setups || [];
  if (!rows.length) {
    return "<p>No replay history available yet.</p>";
  }

  return `
    <div class="ta-insight-replay">
      ${rows.map((row) => `
        <div class="ta-insight-box">
          <span>${formatText(row.interval).toUpperCase()} • ${formatText(row.signal).toUpperCase()}</span>
          <strong>${capitalize(row.bias)}</strong>
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
  const volumeTrend = data?.summary_context?.volume_trend ?? "--";
  const pivot = data?.levels?.pivot ?? "--";
  const r1 = data?.levels?.resistance_1 ?? "--";
  const s1 = data?.levels?.support_1 ?? "--";
  const orderflow = data?.orderflow || {};
  const confluence = data?.multi_timeframe?.confluence || {};
  const premium = data?.premium || {};
  const vip = data?.vip || {};
  const replay = data?.setup_replay || {};

  const tf15m = getTf(data, "15m");
  const tf1h = getTf(data, "1h");
  const tf4h = getTf(data, "4h");
  const tf1d = getTf(data, "1d");

  const map = {
    "premium-alignment": {
      tier: "premium",
      title: "Multi-Timeframe Alignment",
      subtitle: "Premium directional framework",
      html: `
        <p>Confluence score: <strong>${confluence.score ?? "--"}</strong> · Dominant bias: <strong>${capitalize(confluence.dominant_bias)}</strong></p>
        <div class="ta-insight-grid">
          ${buildTfBox("15M", tf15m)}
          ${buildTfBox("1H", tf1h)}
          ${buildTfBox("4H", tf4h)}
          ${buildTfBox("1D", tf1d)}
        </div>
        <ul class="ta-insight-list">
          <li>Alignment: ${capitalize(confluence.alignment)}</li>
          <li>Entry quality: ${capitalize(confluence.entry_quality)}</li>
          <li>Orderflow: ${capitalize(orderflow.state)}</li>
        </ul>
      `
    },
    "premium-breakdown": {
      tier: "premium",
      title: "Indicator Breakdown",
      subtitle: "Momentum and structure detail",
      html: `
        <div class="ta-insight-grid">
          <div class="ta-insight-box"><span>RSI</span><strong>${rsi}</strong></div>
          <div class="ta-insight-box"><span>MFI</span><strong>${mfi}</strong></div>
          <div class="ta-insight-box"><span>MACD</span><strong>${macd}</strong></div>
          <div class="ta-insight-box"><span>Confidence</span><strong>${confidence}%</strong></div>
          <div class="ta-insight-box"><span>RSI State</span><strong>${capitalize(premium?.indicator_breakdown?.rsi_state)}</strong></div>
          <div class="ta-insight-box"><span>MFI State</span><strong>${capitalize(premium?.indicator_breakdown?.mfi_state)}</strong></div>
          <div class="ta-insight-box"><span>MACD Regime</span><strong>${capitalize(premium?.indicator_breakdown?.macd_regime)}</strong></div>
          <div class="ta-insight-box"><span>Volume Quality</span><strong>${capitalize(premium?.indicator_breakdown?.volume_quality)}</strong></div>
        </div>
      `
    },
    "premium-ai": {
      tier: "premium",
      title: "Premium AI Context",
      subtitle: "Extended AI interpretation",
      html: `
        <p>${data?.ai_summary || "No AI context available."}</p>
        <p><strong>Premium Context:</strong> ${premium?.premium_ai_context || "No premium context available."}</p>
        <ul class="ta-insight-list">
          <li>Trend regime: ${capitalize(trend)}</li>
          <li>Bias: ${capitalize(data?.bias)}</li>
          <li>Execution confidence: ${confidence}%</li>
          <li>Orderflow strength: ${orderflow?.strength ?? "--"}</li>
        </ul>
      `
    },
    "premium-read": {
      tier: "premium",
      title: "Advanced Market Read",
      subtitle: "Contextual market interpretation",
      html: `
        <p>The market remains <strong>${capitalize(data?.bias)}</strong> with a <strong>${capitalize(trend)}</strong> structure and <strong>${capitalize(volumeTrend)}</strong> participation.</p>
        <div class="ta-insight-grid">
          <div class="ta-insight-box"><span>Pivot</span><strong>${pivot}</strong></div>
          <div class="ta-insight-box"><span>R1</span><strong>${r1}</strong></div>
          <div class="ta-insight-box"><span>S1</span><strong>${s1}</strong></div>
          <div class="ta-insight-box"><span>Orderflow</span><strong>${capitalize(orderflow.state)}</strong></div>
          <div class="ta-insight-box"><span>Absorption</span><strong>${capitalize(orderflow.absorption)}</strong></div>
          <div class="ta-insight-box"><span>Confluence</span><strong>${confluence.score ?? "--"}</strong></div>
        </div>
        <h4>Replay</h4>
        ${buildReplayRows(replay)}
      `
    },
    "vip-score": {
      tier: "vip",
      title: "VIP Confluence Score",
      subtitle: "Institutional quality filter",
      html: `
        <div class="ta-insight-grid">
          <div class="ta-insight-box"><span>VIP Score</span><strong>${vip?.score ?? "--"} / 100</strong></div>
          <div class="ta-insight-box"><span>Trend</span><strong>${capitalize(trend)}</strong></div>
          <div class="ta-insight-box"><span>Momentum</span><strong>${Number(rsi) >= 50 ? "Supportive" : "Weak"}</strong></div>
          <div class="ta-insight-box"><span>Flow</span><strong>${capitalize(orderflow.imbalance)}</strong></div>
          <div class="ta-insight-box"><span>Execution</span><strong>${capitalize(vip?.execution_mode)}</strong></div>
          <div class="ta-insight-box"><span>Risk</span><strong>${capitalize(vip?.risk_profile)}</strong></div>
        </div>
      `
    },
    "vip-scenarios": {
      tier: "vip",
      title: "VIP Scenarios",
      subtitle: "Bull / Bear / Neutral framework",
      html: `
        <ul class="ta-insight-list">
          <li><strong>Bullish:</strong> ${vip?.bullish_scenario || "No bullish scenario available."}</li>
          <li><strong>Bearish:</strong> ${vip?.bearish_scenario || "No bearish scenario available."}</li>
          <li><strong>Neutral:</strong> ${vip?.neutral_scenario || "No neutral scenario available."}</li>
        </ul>
      `
    },
    "vip-notes": {
      tier: "vip",
      title: "VIP Desk Notes",
      subtitle: "Institutional interpretation",
      html: `
        <p>${vip?.desk_notes || "No desk notes available."}</p>
        <ul class="ta-insight-list">
          <li>Telegram candidate: ${vip?.telegram_alert_candidate ? "YES" : "NO"}</li>
          <li>Confluence score: ${confluence?.score ?? "--"}</li>
          <li>Orderflow strength: ${orderflow?.strength ?? "--"}</li>
          <li>Replay winrate: ${replay?.winrate ?? "--"}%</li>
        </ul>
      `
    },
    "vip-execution": {
      tier: "vip",
      title: "Institutional Execution Layer",
      subtitle: "Scenario-based tactical framework",
      html: `
        <div class="ta-insight-grid">
          <div class="ta-insight-box"><span>Pivot</span><strong>${pivot}</strong></div>
          <div class="ta-insight-box"><span>Resistance</span><strong>${r1}</strong></div>
          <div class="ta-insight-box"><span>Support</span><strong>${s1}</strong></div>
          <div class="ta-insight-box"><span>Mode</span><strong>${capitalize(vip?.execution_mode)}</strong></div>
          <div class="ta-insight-box"><span>Alert Ready</span><strong>${vip?.telegram_alert_candidate ? "YES" : "NO"}</strong></div>
          <div class="ta-insight-box"><span>Flow</span><strong>${capitalize(orderflow.state)}</strong></div>
        </div>
      `
    }
  };

  return map[type] || {
    tier: "premium",
    title: "Advanced Insight",
    subtitle: "Desk interpretation",
    html: "<p>No insight available.</p>"
  };
}

function renderConfluencePanel(data) {
  const confluence = data?.multi_timeframe?.confluence || {};

  setText("confluenceScore", confluence.score ?? "--");
  setText("confluenceBias", capitalize(confluence.dominant_bias));
  setText("confluenceAlignment", capitalize(confluence.alignment));
  setText("confluenceEntryQuality", capitalize(confluence.entry_quality));

  setText("sideConfluenceScore", confluence.score ?? "--");
  setText("sideConfluenceLabel", capitalize(confluence.entry_quality || "No data"));
}

function renderTimeframeCard(tfName, biasId, metaId, data) {
  const tf = getTf(data, tfName);
  setText(biasId, capitalize(tf.bias || tf.trend || "unknown"));
  setText(metaId, `RSI ${tf.rsi ?? "--"} · Conf ${tf.confidence ?? "--"}`);
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

  setText("premiumBias15m", capitalize(tf15m.bias || tf15m.trend || "unknown"));
  setText("premiumBias1h", capitalize(tf1h.bias || tf1h.trend || "unknown"));
  setText("premiumBias4h", capitalize(tf4h.bias || tf4h.trend || "unknown"));
  setText("premiumBias1d", capitalize(tf1d.bias || tf1d.trend || "unknown"));
}

function renderOrderflowPanel(data) {
  const orderflow = data?.orderflow || {};

  setText("orderflowState", capitalize(orderflow.state));
  setText("orderflowStrength", orderflow.strength ?? "--");
  setText("orderflowImbalance", capitalize(orderflow.imbalance));
  setText("orderflowAbsorption", capitalize(orderflow.absorption));
  setText("buyPressureValue", formatNumber(orderflow.buy_pressure, 2));
  setText("sellPressureValue", formatNumber(orderflow.sell_pressure, 2));

  setText("sideOrderflowState", capitalize(orderflow.state));
  setText("sideOrderflowStrength", `Strength ${orderflow.strength ?? "--"}`);
}

function renderReplayPanel(data) {
  const replay = data?.setup_replay || {};
  const historyEl = document.getElementById("replayHistory");

  setText("replayCount", replay.count ?? "--");
  setText("replayWinrate", replay.winrate !== null && replay.winrate !== undefined ? `${replay.winrate}%` : "--");
  setText("replayAvgConfidence", replay.avg_confidence !== null && replay.avg_confidence !== undefined ? `${replay.avg_confidence}%` : "--");
  setText("replayBestBias", capitalize(replay.best_bias));

  setText("sideReplayWinrate", replay.winrate !== null && replay.winrate !== undefined ? `${replay.winrate}%` : "--");
  setText("sideReplayCount", `${replay.count ?? 0} setups`);

  if (!historyEl) return;

  const rows = replay?.last_setups || [];
  if (!rows.length) {
    historyEl.innerHTML = "<p>No replay history loaded.</p>";
    return;
  }

  historyEl.innerHTML = rows.map((row) => `
    <div class="ta-indicator-row">
      <div>
        <strong>${formatText(row.signal).toUpperCase()} • ${formatText(row.interval).toUpperCase()}</strong>
        <p>Bias: ${capitalize(row.bias)} · Conf: ${row.confidence ?? "--"} · Outcome: ${row.simulated_outcome_pct ?? "--"}%</p>
      </div>
      <span class="ta-status-chip ${Number(row.simulated_outcome_pct) >= 0 ? "green" : "gold"}">
        ${Number(row.simulated_outcome_pct) >= 0 ? "Positive" : "Watch"}
      </span>
    </div>
  `).join("");
}

function renderTelegramPanel(data) {
  const vip = data?.vip || {};

  setText("telegramReady", vip.telegram_alert_candidate ? "YES" : "NO");
  setText("telegramExecutionMode", capitalize(vip.execution_mode));
  setText("telegramRiskProfile", capitalize(vip.risk_profile));
  setText(
    "telegramNote",
    vip.telegram_alert_candidate
      ? "VIP alert conditions are met. Setup is eligible for Telegram automation."
      : "VIP alert conditions are not fully aligned yet."
  );
}

function renderPremiumVipBlocks(data) {
  const premium = data?.premium || {};
  const vip = data?.vip || {};
  const replay = data?.setup_replay || {};
  const orderflow = data?.orderflow || {};
  const confluence = data?.multi_timeframe?.confluence || {};

  setText("premiumRsiState", capitalize(premium?.indicator_breakdown?.rsi_state || "unknown"));
  setText("premiumMfiState", capitalize(premium?.indicator_breakdown?.mfi_state || "unknown"));
  setText("premiumMacdState", capitalize(premium?.indicator_breakdown?.macd_regime || "unknown"));
  setText("premiumVolumeState", capitalize(premium?.indicator_breakdown?.volume_quality || data?.summary_context?.volume_trend || "unknown"));
  setText("premiumAiSummary", premium?.premium_ai_context || data?.ai_summary || "No premium context available.");

  setText("vipConfluenceScore", `${vip?.score ?? confluence?.score ?? "--"} / 100`);
  setText("vipExecutionMode", capitalize(vip?.execution_mode || "selective"));
  setText("vipRiskProfile", capitalize(vip?.risk_profile || "balanced"));
  setText("vipBullScenario", vip?.bullish_scenario || `Bullish continuation above pivot ${data?.levels?.pivot ?? "--"} with improving orderflow.`);
  setText("vipBearScenario", vip?.bearish_scenario || `Bearish pressure remains valid below ${data?.levels?.resistance_1 ?? "--"} if support weakens.`);
  setText("vipNeutralScenario", vip?.neutral_scenario || "Neutral regime remains active while confluence stays mixed.");
  setText(
    "vipDeskNotes",
    vip?.desk_notes ||
      `Institutional note: bias ${data?.bias || "mixed"}, confluence ${confluence?.score ?? "--"}, replay winrate ${replay?.winrate ?? "--"}%, flow ${capitalize(orderflow.state)}.`
  );
}

function renderExecutionPlan(data) {
  const executionPlan = document.getElementById("executionPlan");
  if (!executionPlan) return;

  const confluence = data?.multi_timeframe?.confluence || {};
  const orderflow = data?.orderflow || {};
  const replay = data?.setup_replay || {};
  const vip = data?.vip || {};

  executionPlan.innerHTML = `
    <p><strong>Asset:</strong> ${data.token || "--"}</p>
    <p><strong>Timeframe:</strong> ${String(data.interval || "--").toUpperCase()}</p>
    <p><strong>Indicator:</strong> ${data.indicator || "--"}</p>
    <p><strong>Live Price:</strong> ${formatPrice(data.current_price)}</p>
    <p><strong>24H Change:</strong> ${formatPct(data.price_change_24h)}</p>
    <p><strong>Bias:</strong> ${capitalize(data.bias)}</p>
    <p><strong>Confluence Score:</strong> ${confluence.score ?? "--"}</p>
    <p><strong>Entry Quality:</strong> ${capitalize(confluence.entry_quality)}</p>
    <p><strong>Orderflow:</strong> ${capitalize(orderflow.state)} (${orderflow.strength ?? "--"})</p>
    <p><strong>Replay Winrate:</strong> ${replay.winrate ?? "--"}%</p>
    <p><strong>Execution Mode:</strong> ${capitalize(vip.execution_mode)}</p>
  `;
}

function renderAnalysis(data) {
  const heroSignal = document.getElementById("heroSignal");
  const biasBadge = document.getElementById("biasBadge");
  const summaryTags = document.getElementById("summaryTags");

  const vip = data?.vip || {};
  const orderflow = data?.orderflow || {};

  setText("heroAsset", data.token || "--");
  setSignalPill(heroSignal, data.signal);
  setBiasBadge(biasBadge, data.bias);

  setText("heroPrice", formatPrice(data.current_price));
  setText("heroMarketCap", formatMoney(data.market_cap));
  setText("heroVolume", formatMoney(data.volume_24h));
  setText("heroConfidence", `${vip?.score ?? data.confidence ?? "--"}${vip?.score || data.confidence ? " / 100" : ""}`);

  setText("heroTrend", capitalize(data.summary_context?.trend));
  setText("heroRsi", data.indicators?.rsi ?? "--");
  setText("heroMfi", data.indicators?.mfi ?? "--");
  setText("heroDeskMode", capitalize(vip.execution_mode || "neutral"));

  setText("signalValue", String(data.signal || "--").toUpperCase());
  setText("confidenceValue", `${data.confidence ?? "--"}%`);
  setText("emaValue", capitalize(data.summary_context?.trend));
  setText("volumeValue", capitalize(data.summary_context?.volume_trend));
  setText("summaryText", data.ai_summary || data?.premium?.premium_ai_context || "No summary.");

  setText("trendValue", capitalize(data.summary_context?.trend));
  setText("rsiValue", data.indicators?.rsi ?? "--");
  setText("stochValue", data.indicators?.stochastic_rsi_k ?? "--");
  setText("mfiValue", data.indicators?.mfi ?? "--");
  setText("macdValue", data.indicators?.macd ?? "--");
  setText("riskValue", capitalize(vip?.risk_profile || "medium"));

  setText("res1", data.levels?.resistance_1 ?? "--");
  setText("res2", data.levels?.resistance_2 ?? "--");
  setText("pivot", data.levels?.pivot ?? "--");
  setText("sup1", data.levels?.support_1 ?? "--");
  setText("sup2", data.levels?.support_2 ?? "--");

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
  renderPremiumVipBlocks(data);
  renderExecutionPlan(data);

  lastAnalysisData = data;
  renderBigChartByTab(data, currentTab);
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
    showToast("Please wait a few seconds before requesting another analysis.", false);
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
      signal: currentController.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    renderAnalysis(data);
    showToast("Analysis loaded successfully.");
  } catch (error) {
    if (error.name === "AbortError") return;

    console.error("Technical analysis fetch error:", error);
    setText("summaryText", "Erreur pendant le chargement des données réelles.");
    showToast("Error loading real analysis.", false);
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

// Pas d'auto-fetch sur change
// Pas d'auto-fetch au chargement