console.log("LIGHTWEIGHT ELITE MODE LOADED");

/*
  ELITE MODE
  - Lightweight Charts
  - Replay fluide style TradingView
  - Zoom/scroll/crosshair natifs
  - Multi-trades si API renvoie data.trades, sinon trade unique
  - EMA20 / EMA50 / VWAP / MTF / HH-HL / Volume / RSI avec cases
  - MFE / MAE live
  - Feedback décision intelligent simple côté frontend
*/

let chart = null;
let candleSeries = null;
let markerApi = null;

let ema20Series = null;
let ema50Series = null;
let vwapSeries = null;
let htfSeries = null;
let structureSeries = null;
let volumeSeries = null;
let rsiSeries = null;

let rawData = {};
let trades = [];
let activeTradeIndex = 0;
let trade = {};

let candles = [];
let htfCandles = [];
let replayCandles = [];

let entryIndex = 0;
let decisionIndex = 0;
let exitIndex = 0;
let startIndex = 0;
let endIndex = 0;
let currentPos = 1;

let timer = null;
let speed = 420;
let decisionDone = false;
let decisionShown = false;

let indicatorState = {
  ema20: true,
  ema50: true,
  vwap: true,
  htf: true,
  structure: true,
  volume: true,
  rsi: true
};

window.addEventListener("load", initReplay);

async function initReplay() {
  const chartEl = document.getElementById("chart");

  try {
    if (typeof LightweightCharts === "undefined") {
      throw new Error("LightweightCharts non chargé dans replay.html");
    }

    if (typeof replayApiBase === "undefined" || !replayApiBase) {
      throw new Error("replayApiBase manquant");
    }

    const res = await fetch(replayApiBase, { credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Erreur API replay");

    rawData = data || {};
    candles = normalizeCandles(data.candles || []);
    htfCandles = normalizeCandles(data.higher_timeframe_candles || []);

    trades = Array.isArray(data.trades) && data.trades.length
      ? data.trades
      : [data.trade || data || {}];

    if (!candles.length) {
      chartEl.innerHTML = "<div class='chart-error'>Aucune bougie disponible.</div>";
      return;
    }

    trade = trades[activeTradeIndex] || {};
    computeReplayWindow();
    hydrateUI();
    initIndicatorPanel();
    initElitePanels();
    initDecisionOverlay();
    initChart();
    resetReplay();

  } catch (e) {
    console.error(e);
    if (chartEl) chartEl.innerHTML = "<div class='chart-error'>" + escapeHtml(e.message) + "</div>";
  }
}

/* ================= DATA ================= */

function normalizeCandles(raw) {
  return (raw || [])
    .map(c => ({
      time: toUnixTime(c.time),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
      volume: c.volume == null ? 0 : Number(c.volume)
    }))
    .filter(c => c.time && [c.open, c.high, c.low, c.close].every(Number.isFinite))
    .sort((a, b) => a.time - b.time)
    .map((c, i) => ({
      ...c,
      index: i,
      high: Math.max(c.high, c.open, c.close, c.low),
      low: Math.min(c.low, c.open, c.close, c.high)
    }));
}

function computeReplayWindow() {
  entryIndex = clampIndex(trade.entry_index, nearestIndexByTime(trade.entry_time, 0));
  exitIndex = detectExitIndex();
  decisionIndex = computeProDecisionIndex();

  if (decisionIndex <= entryIndex && exitIndex > entryIndex) {
    decisionIndex = Math.min(exitIndex, entryIndex + 2);
  }

  if (decisionIndex >= exitIndex && exitIndex > entryIndex) {
    decisionIndex = Math.max(entryIndex + 1, exitIndex - 1);
  }

  // Affichage large : 100 bougies avant entrée
startIndex = Math.max(0, entryIndex - 100);

// Fin du replay après sortie
endIndex = Math.min(
  candles.length - 1,
  Math.max(exitIndex + 10, entryIndex + 24)
);

// Toutes les bougies visibles dans le chart
replayCandles = candles.slice(startIndex, endIndex + 1);

// Mais le PLAY commence seulement 10 bougies avant entrée
const playStartIndex = Math.max(0, entryIndex - 10);
currentPos = Math.max(1, playStartIndex - startIndex + 1);
  decisionDone = false;
  decisionShown = false;
}

function detectExitIndex() {
  const direction = String(trade.direction || "").toUpperCase();
  const tp = Number(trade.take_profit);
  const sl = Number(trade.stop_loss);

  for (let i = entryIndex + 1; i < candles.length; i++) {
    const c = candles[i];
    const tpTouched = Number.isFinite(tp) && c.low <= tp && c.high >= tp;
    const slTouched = Number.isFinite(sl) && c.low <= sl && c.high >= sl;

    if (direction === "BUY") {
      if (tpTouched) return i;
      if (slTouched) return i;
    } else if (direction === "SELL") {
      if (tpTouched) return i;
      if (slTouched) return i;
    } else if (tpTouched || slTouched) {
      return i;
    }
  }

  return clampIndex(trade.exit_index, candles.length - 1);
}

function computeProDecisionIndex() {
  if (!Number.isFinite(entryIndex) || !Number.isFinite(exitIndex) || exitIndex <= entryIndex) {
    return Math.min(candles.length - 1, entryIndex + 2);
  }

  const distance = exitIndex - entryIndex;
  if (distance < 6) return Math.min(exitIndex, entryIndex + Math.max(1, Math.floor(distance / 2)));
  return Math.round(entryIndex + distance * 0.5);
}

/* ================= CHART ================= */

function initChart() {
  const el = document.getElementById("chart");
  el.innerHTML = "";

  chart = LightweightCharts.createChart(el, {
    width: el.clientWidth,
    height: el.clientHeight || 540,
    layout: {
      background: { color: "#07111f" },
      textColor: "#94a3b8",
      fontSize: 12
    },
    grid: {
      vertLines: { color: "rgba(148,163,184,0.07)" },
      horzLines: { color: "rgba(148,163,184,0.07)" }
    },
    rightPriceScale: {
      borderColor: "rgba(148,163,184,0.16)",
      scaleMargins: { top: 0.08, bottom: 0.12 }
    },
    timeScale: {
      borderColor: "rgba(148,163,184,0.16)",
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 10,
      barSpacing: 12,
      fixLeftEdge: false,
      fixRightEdge: false,
      lockVisibleTimeRangeOnResize: false
    },
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: true
    },
    handleScale: {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: {
        color: "rgba(148,163,184,0.35)",
        style: LightweightCharts.LineStyle.Dashed,
        labelBackgroundColor: "#334155"
      },
      horzLine: {
        color: "rgba(148,163,184,0.35)",
        style: LightweightCharts.LineStyle.Dashed,
        labelBackgroundColor: "#334155"
      }
    }
  });

  candleSeries = addCandlestickSeriesCompat({
    upColor: "#22c55e",
    downColor: "#ef4444",
    borderUpColor: "#22c55e",
    borderDownColor: "#ef4444",
    wickUpColor: "#22c55e",
    wickDownColor: "#ef4444",
    priceLineVisible: true
  });

  ema20Series = addLineSeriesCompat({ color: "#f59e0b", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "EMA 20" });
  ema50Series = addLineSeriesCompat({ color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "EMA 50" });
  vwapSeries = addLineSeriesCompat({ color: "#38bdf8", lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dotted, priceLineVisible: false, lastValueVisible: true, title: "VWAP" });
  htfSeries = addLineSeriesCompat({ color: "#8b5cf6", lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true, title: "HTF" });
  structureSeries = addLineSeriesCompat({ color: "#e5e7eb", lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, title: "HH/HL" });

  volumeSeries = addHistogramSeriesCompat({
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    priceLineVisible: false,
    lastValueVisible: false
  });

  try {
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, borderVisible: false });
  } catch (e) {}

  rsiSeries = addLineSeriesCompat({
    color: "#eab308",
    lineWidth: 1,
    priceScaleId: "rsi",
    priceLineVisible: false,
    lastValueVisible: false,
    title: "RSI 14"
  });

  try {
    chart.priceScale("rsi").applyOptions({ scaleMargins: { top: 0.68, bottom: 0.12 }, borderVisible: false });
  } catch (e) {}

  addPriceLines();

  window.addEventListener("resize", () => {
    chart.applyOptions({ width: el.clientWidth, height: el.clientHeight || 540 });
  });
}

function addCandlestickSeriesCompat(options) {
  if (chart && typeof chart.addCandlestickSeries === "function") return chart.addCandlestickSeries(options);
  if (LightweightCharts.CandlestickSeries && typeof chart.addSeries === "function") return chart.addSeries(LightweightCharts.CandlestickSeries, options);
  throw new Error("CandlestickSeries introuvable");
}

function addLineSeriesCompat(options) {
  if (chart && typeof chart.addLineSeries === "function") return chart.addLineSeries(options);
  if (LightweightCharts.LineSeries && typeof chart.addSeries === "function") return chart.addSeries(LightweightCharts.LineSeries, options);
  throw new Error("LineSeries introuvable");
}

function addHistogramSeriesCompat(options) {
  if (chart && typeof chart.addHistogramSeries === "function") return chart.addHistogramSeries(options);
  if (LightweightCharts.HistogramSeries && typeof chart.addSeries === "function") return chart.addSeries(LightweightCharts.HistogramSeries, options);
  throw new Error("HistogramSeries introuvable");
}

function addPriceLines() {
  if (trade.entry_price != null) {
    candleSeries.createPriceLine({ price: Number(trade.entry_price), color: "#22c55e", lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: "Entry" });
  }
  if (trade.stop_loss != null) {
    candleSeries.createPriceLine({ price: Number(trade.stop_loss), color: "#ef4444", lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: "SL" });
  }
  if (trade.take_profit != null) {
    candleSeries.createPriceLine({ price: Number(trade.take_profit), color: "#3b82f6", lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: "TP" });
  }
}

function renderChart() {
  const visible = replayCandles.slice(0, currentPos);

  candleSeries.setData(visible.map(toChartCandle));
  updateIndicatorSeries(visible);

  const structureMarkers = indicatorState.structure ? buildStructureMarkers(visible) : [];
  setSeriesMarkers(buildMarkers(visible).concat(structureMarkers));

  renderProgress();
  updateLiveStats(visible);
  updateAIFeedbackLive(visible);

  const last = visible[visible.length - 1];
  if (last) {
    setText("decision-mode-text", last.index >= exitIndex ? "Replay terminé" : "Lecture");
  }

  // TradingView feel: follow right edge smoothly while keeping zoom/scroll native.
  if (visible.length > 1) {
    chart.timeScale().setVisibleRange({
      from: visible[Math.max(0, visible.length - 40)].time,
      to: visible[visible.length - 1].time
    });
  } else {
    chart.timeScale().fitContent();
  }
}

/* ================= REPLAY ENGINE ================= */

function startReplay() {
  if (timer) return;
  if (currentPos >= replayCandles.length) resetReplay();
  timer = setInterval(stepReplay, speed);
}

function pauseReplay() {
  if (timer) clearInterval(timer);
  timer = null;
  setText("decision-mode-text", "Pause");
}

function stepReplay() {
  if (currentPos >= replayCandles.length) {
    pauseReplay();
    setText("decision-mode-text", "Replay terminé");
    return;
  }

  currentPos += 1;
  const current = replayCandles[currentPos - 1];

  if (current && current.index === decisionIndex && !decisionDone && !decisionShown) {
    renderChart();
    decisionShown = true;
    showDecisionOverlay();
    pauseReplay();
    return;
  }

  renderChart();
}

function resetReplay() {
  pauseReplay();
  const playStartIndex = Math.max(0, entryIndex - 10);
  currentPos = Math.max(1, playStartIndex - startIndex + 1);
  decisionDone = false;
  decisionShown = false;

  hideDecisionOverlay();
  const box = document.getElementById("decision-box");
  if (box) box.classList.add("hidden");

  setText("decision-mode-text", "En attente");
  renderChart();
}

function setSpeed(multiplier) {
  const m = Number(multiplier) || 1;
  speed = Math.max(45, 420 / m);
  if (timer) {
    pauseReplay();
    startReplay();
  }
}

async function makeDecision(choice) {
  try {
    const payload = { decision: choice, trade_index: activeTradeIndex };

    const res = await fetch(`${replayApiBase}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Erreur sauvegarde décision");

    decisionDone = true;
    hideDecisionOverlay();

    const box = document.getElementById("decision-box");
    if (box) box.classList.add("hidden");

    displayScore(data);
    updateAIFeedbackAfterDecision(choice, data);
    startReplay();

  } catch (e) {
    console.error(e);
    alert(e.message);
  }
}

/* ================= ELITE UI ================= */

function initIndicatorPanel() {
  const chartCard = document.querySelector(".chart-card");
  if (!chartCard || document.getElementById("indicator-panel")) return;

  const panel = document.createElement("div");
  panel.id = "indicator-panel";
  panel.className = "indicator-panel";
  panel.innerHTML = `
    <label><input type="checkbox" data-indicator="ema20" checked> EMA 20</label>
    <label><input type="checkbox" data-indicator="ema50" checked> EMA 50</label>
    <label><input type="checkbox" data-indicator="vwap" checked> VWAP</label>
    <label><input type="checkbox" data-indicator="htf" checked> MTF</label>
    <label><input type="checkbox" data-indicator="structure" checked> HH/HL</label>
    <label><input type="checkbox" data-indicator="volume" checked> Volume</label>
    <label><input type="checkbox" data-indicator="rsi" checked> RSI</label>
  `;

  const chartEl = document.getElementById("chart");
  chartCard.insertBefore(panel, chartEl);

  panel.querySelectorAll("input[type='checkbox']").forEach(input => {
    input.addEventListener("change", () => {
      indicatorState[input.dataset.indicator] = input.checked;
      renderChart();
    });
  });
}

function initElitePanels() {
  const side = document.querySelector(".replay-side-column");
  if (side && !document.getElementById("elite-live-card")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "elite-live-card";
    card.innerHTML = `
      <h3>Stats live</h3>
      <div class="metric-list">
        <div class="metric-row"><span>MFE</span><strong id="live-mfe">0%</strong></div>
        <div class="metric-row"><span>MAE</span><strong id="live-mae">0%</strong></div>
        <div class="metric-row"><span>R actuel</span><strong id="live-r">0R</strong></div>
        <div class="metric-row"><span>Phase</span><strong id="live-phase">Pré-entry</strong></div>
      </div>
    `;
    side.insertBefore(card, side.children[1] || null);
  }

  if (side && !document.getElementById("elite-ai-card")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "elite-ai-card";
    card.innerHTML = `
      <h3>IA feedback</h3>
      <p id="ai-feedback" style="color:#b8c4d8;line-height:1.55;">Le feedback apparaîtra pendant le replay.</p>
    `;
    side.insertBefore(card, side.children[2] || null);
  }

  if (trades.length > 1) initTradeSelector();

  const style = document.createElement("style");
  style.textContent = `
    .indicator-panel {
      display:flex; flex-wrap:wrap; gap:10px; align-items:center;
      margin:0 0 12px; padding:10px 12px; border-radius:14px;
      background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.07);
    }
    .indicator-panel label {
      display:inline-flex; align-items:center; gap:7px; color:#c8d4e8;
      font-size:13px; font-weight:800; cursor:pointer; user-select:none;
    }
    .indicator-panel input { accent-color:#3b82f6; cursor:pointer; }
    .trade-selector {
      display:flex; gap:8px; flex-wrap:wrap; margin:0 0 12px;
    }
    .trade-selector button {
      border:1px solid rgba(255,255,255,.09); background:#13233d; color:#e5edf7;
      padding:8px 12px; border-radius:999px; font-weight:800; cursor:pointer;
    }
    .trade-selector button.active { background:#2563eb; border-color:#60a5fa; }
  `;
  document.head.appendChild(style);
}

function initTradeSelector() {
  const chartCard = document.querySelector(".chart-card");
  if (!chartCard || document.getElementById("trade-selector")) return;

  const selector = document.createElement("div");
  selector.id = "trade-selector";
  selector.className = "trade-selector";
  selector.innerHTML = trades.map((t, i) => `
    <button data-trade-index="${i}" class="${i === activeTradeIndex ? "active" : ""}">
      Trade ${i + 1} ${t.symbol ? "• " + escapeHtml(t.symbol) : ""}
    </button>
  `).join("");

  const indicator = document.getElementById("indicator-panel");
  chartCard.insertBefore(selector, indicator || document.getElementById("chart"));

  selector.querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", () => {
      activeTradeIndex = Number(btn.dataset.tradeIndex);
      trade = trades[activeTradeIndex] || {};
      selector.querySelectorAll("button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      if (chart) chart.remove();
      markerApi = null;
      computeReplayWindow();
      hydrateUI();
      initChart();
      resetReplay();
    });
  });
}

function initDecisionOverlay() {
  if (document.getElementById("decision-overlay")) return;

  const overlay = document.createElement("div");
  overlay.id = "decision-overlay";
  overlay.className = "decision-overlay hidden";
  overlay.innerHTML = `
    <div class="decision-overlay-card">
      <div class="decision-overlay-kicker">Moment de décision</div>
      <h3>Le trade est au milieu de son scénario</h3>
      <p id="decision-overlay-text">Choisis ton action avant de révéler la suite.</p>
      <div class="decision-overlay-actions">
        <button class="btn-close" onclick="makeDecision('close')">Fermer</button>
        <button class="btn-hold" onclick="makeDecision('hold')">Conserver</button>
        <button class="btn-partial" onclick="makeDecision('partial')">Alléger</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const style = document.createElement("style");
  style.textContent = `
    .decision-overlay { position:fixed; inset:0; display:grid; place-items:center; z-index:9999;
      background:rgba(2,8,23,.56); backdrop-filter:blur(5px); }
    .decision-overlay.hidden { display:none; }
    .decision-overlay-card { width:min(520px,calc(100vw - 32px)); border-radius:24px; padding:26px;
      background:linear-gradient(135deg,#0b1728,#111f35); border:1px solid rgba(245,158,11,.45);
      box-shadow:0 28px 90px rgba(0,0,0,.55); color:#e5edf7; }
    .decision-overlay-kicker { display:inline-flex; padding:7px 12px; border-radius:999px;
      background:rgba(245,158,11,.13); color:#fbbf24; font-size:13px; font-weight:900; margin-bottom:14px; }
    .decision-overlay-card h3 { margin:0 0 10px; font-size:26px; line-height:1.2; }
    .decision-overlay-card p { margin:0 0 20px; color:#b8c4d8; line-height:1.55; }
    .decision-overlay-actions { display:flex; flex-wrap:wrap; gap:12px; }
    .decision-overlay-actions button { border:0; border-radius:14px; padding:12px 18px; font-weight:900; cursor:pointer; }
  `;
  document.head.appendChild(style);
}

function showDecisionOverlay() {
  setText("decision-mode-text", "Moment de décision");
  const overlay = document.getElementById("decision-overlay");
  const text = document.getElementById("decision-overlay-text");
  if (text) text.textContent = buildDecisionPrompt();
  if (overlay) overlay.classList.remove("hidden");

  const box = document.getElementById("decision-box");
  if (box) box.classList.remove("hidden");
}

function hideDecisionOverlay() {
  const overlay = document.getElementById("decision-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function buildDecisionPrompt() {
  const stats = computeLiveStats(replayCandles.slice(0, currentPos));
  if (stats.maePct > 0.5) return "Le trade est sous pression. Réduire ou fermer peut être plus discipliné.";
  if (stats.mfePct > 0.5) return "Le trade a déjà donné du potentiel. Protège le plan avant de révéler la suite.";
  return "Le trade est encore neutre. Choisis selon la structure, pas selon l’émotion.";
}

/* ================= INDICATORS ================= */

function updateIndicatorSeries(visible) {
  setDataSafe(ema20Series, indicatorState.ema20 ? calculateEMA(visible, 20) : []);
  setDataSafe(ema50Series, indicatorState.ema50 ? calculateEMA(visible, 50) : []);
  setDataSafe(vwapSeries, indicatorState.vwap ? calculateVWAP(visible) : []);
  setDataSafe(htfSeries, indicatorState.htf ? calculateHTFOverlay(visible) : []);
  setDataSafe(structureSeries, indicatorState.structure ? calculateStructureLine(visible) : []);
  setDataSafe(volumeSeries, indicatorState.volume ? calculateVolume(visible) : []);
  setDataSafe(rsiSeries, indicatorState.rsi ? calculateRSI(visible, 14) : []);
}

function setDataSafe(series, data) {
  if (series && typeof series.setData === "function") series.setData(data || []);
}

function calculateEMA(data, period) {
  if (!data.length) return [];
  const k = 2 / (period + 1);
  let ema = data[0].close;
  return data.map((c, index) => {
    ema = index === 0 ? c.close : c.close * k + ema * (1 - k);
    return { time: c.time, value: Number(ema.toFixed(6)) };
  });
}

function calculateVWAP(data) {
  let cumulativePV = 0;
  let cumulativeVolume = 0;
  return data.map(c => {
    const typical = (c.high + c.low + c.close) / 3;
    const volume = Number.isFinite(Number(c.volume)) && Number(c.volume) > 0 ? Number(c.volume) : 1;
    cumulativePV += typical * volume;
    cumulativeVolume += volume;
    return { time: c.time, value: Number((cumulativePV / cumulativeVolume).toFixed(6)) };
  });
}

function calculateVolume(data) {
  return data.map(c => ({
    time: c.time,
    value: Number(c.volume || 0),
    color: c.close >= c.open ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)"
  }));
}

function calculateRSI(data, period) {
  if (!data || data.length < period + 1) return [];
  const output = [];
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= period; i++) {
    const change = data[i].close - data[i - 1].close;
    avgGain += Math.max(change, 0);
    avgLoss += Math.max(-change, 0);
  }

  avgGain /= period;
  avgLoss /= period;

  let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  output.push({ time: data[period].time, value: Number((100 - 100 / (1 + rs)).toFixed(2)) });

  for (let i = period + 1; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close;
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    output.push({ time: data[i].time, value: Number((100 - 100 / (1 + rs)).toFixed(2)) });
  }

  return output;
}

function calculateHTFOverlay(visible) {
  if (!htfCandles.length || !visible.length) return [];
  return visible.map(c => {
    const h = nearestHTFCandle(c.time);
    return h ? { time: c.time, value: h.close } : null;
  }).filter(Boolean);
}

function nearestHTFCandle(time) {
  let best = null;
  let bestDiff = Infinity;
  htfCandles.forEach(h => {
    const diff = Math.abs(h.time - time);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = h;
    }
  });
  return best;
}

function detectSwings(data, left = 2, right = 2) {
  const swings = [];
  if (!data || data.length < left + right + 1) return swings;

  for (let i = left; i < data.length - right; i++) {
    const c = data[i];
    let isHigh = true;
    let isLow = true;

    for (let j = i - left; j <= i + right; j++) {
      if (j === i) continue;
      if (data[j].high >= c.high) isHigh = false;
      if (data[j].low <= c.low) isLow = false;
    }

    if (isHigh) swings.push({ type: "H", index: c.index, time: c.time, price: c.high });
    if (isLow) swings.push({ type: "L", index: c.index, time: c.time, price: c.low });
  }

  return labelMarketStructure(swings);
}

function labelMarketStructure(swings) {
  let lastHigh = null;
  let lastLow = null;

  return swings.map(s => {
    let label = s.type;
    if (s.type === "H") {
      label = lastHigh == null ? "H" : (s.price > lastHigh ? "HH" : "LH");
      lastHigh = s.price;
    }
    if (s.type === "L") {
      label = lastLow == null ? "L" : (s.price > lastLow ? "HL" : "LL");
      lastLow = s.price;
    }
    return { ...s, label };
  });
}

function calculateStructureLine(visible) {
  return detectSwings(visible)
    .filter(s => ["HH", "HL", "LH", "LL"].includes(s.label))
    .map(s => ({ time: s.time, value: s.price }));
}

function buildStructureMarkers(visible) {
  return detectSwings(visible)
    .filter(s => ["HH", "HL", "LH", "LL"].includes(s.label))
    .map(s => ({
      time: s.time,
      position: s.type === "H" ? "aboveBar" : "belowBar",
      color: structureColor(s.label),
      shape: s.type === "H" ? "arrowDown" : "arrowUp",
      text: s.label
    }));
}

function structureColor(label) {
  if (label === "HH" || label === "HL") return "#22c55e";
  if (label === "LH" || label === "LL") return "#ef4444";
  return "#94a3b8";
}

/* ================= MARKERS ================= */

function buildMarkers(visible) {
  const visibleIndexes = new Set(visible.map(c => c.index));
  const markers = [];

  if (visibleIndexes.has(entryIndex)) {
    markers.push({ time: candles[entryIndex].time, position: "belowBar", color: "#22c55e", shape: "arrowUp", text: "Entry" });
  }

  if (visibleIndexes.has(decisionIndex)) {
    markers.push({ time: candles[decisionIndex].time, position: "aboveBar", color: "#f59e0b", shape: "circle", text: "Decision" });
  }

  if (visibleIndexes.has(exitIndex)) {
    markers.push({
      time: candles[exitIndex].time,
      position: outcomeIsWin() ? "aboveBar" : "belowBar",
      color: outcomeIsWin() ? "#3b82f6" : "#ef4444",
      shape: outcomeIsWin() ? "arrowUp" : "arrowDown",
      text: outcomeIsWin() ? "TP" : "SL"
    });
  }

  const last = visible[visible.length - 1];
  if (last) markers.push({ time: last.time, position: "aboveBar", color: "#60a5fa", shape: "circle", text: "LIVE" });

  return markers;
}

function setSeriesMarkers(markers) {
  if (candleSeries && typeof candleSeries.setMarkers === "function") {
    candleSeries.setMarkers(markers);
    return;
  }

  if (typeof LightweightCharts.createSeriesMarkers === "function") {
    if (!markerApi) markerApi = LightweightCharts.createSeriesMarkers(candleSeries, markers);
    else if (typeof markerApi.setMarkers === "function") markerApi.setMarkers(markers);
  }
}

/* ================= LIVE STATS + AI ================= */

function computeLiveStats(visible) {
  const entry = Number(trade.entry_price);
  const sl = Number(trade.stop_loss);
  const direction = String(trade.direction || "").toUpperCase();

  if (!Number.isFinite(entry) || !visible.length) {
    return { mfePct: 0, maePct: 0, r: 0, phase: "Pré-entry" };
  }

  const afterEntry = visible.filter(c => c.index >= entryIndex);
  if (!afterEntry.length) return { mfePct: 0, maePct: 0, r: 0, phase: "Pré-entry" };

  const risk = Number.isFinite(sl) ? Math.abs(entry - sl) : Math.max(1, entry * 0.001);
  let best = 0;
  let worst = 0;

  afterEntry.forEach(c => {
    if (direction === "BUY") {
      best = Math.max(best, c.high - entry);
      worst = Math.min(worst, c.low - entry);
    } else {
      best = Math.max(best, entry - c.low);
      worst = Math.min(worst, entry - c.high);
    }
  });

  const last = afterEntry[afterEntry.length - 1];
  const currentProfit = direction === "BUY" ? last.close - entry : entry - last.close;

  const mfePct = entry ? (best / entry) * 100 : 0;
  const maePct = entry ? (Math.abs(worst) / entry) * 100 : 0;
  const r = risk ? currentProfit / risk : 0;

  let phase = "Pré-entry";
  if (last.index >= exitIndex) phase = "Sortie";
  else if (last.index >= decisionIndex) phase = "Décision";
  else if (last.index >= entryIndex) phase = "Trade actif";

  return { mfePct, maePct, r, phase };
}

function updateLiveStats(visible) {
  const stats = computeLiveStats(visible);
  setText("live-mfe", `${stats.mfePct.toFixed(2)}%`);
  setText("live-mae", `${stats.maePct.toFixed(2)}%`);
  setText("live-r", `${stats.r.toFixed(2)}R`);
  setText("live-phase", stats.phase);
}

function updateAIFeedbackLive(visible) {
  const el = document.getElementById("ai-feedback");
  if (!el) return;

  const stats = computeLiveStats(visible);
  if (stats.phase === "Pré-entry") {
    el.textContent = "Observe le contexte avant l’entrée. Le replay n’est pas encore dans le trade actif.";
  } else if (stats.phase === "Trade actif") {
    el.textContent = stats.r < -0.5
      ? "Le trade se dégrade avant la décision. Prépare un plan de réduction du risque."
      : "Trade actif. Surveille la structure et évite de réagir à une seule bougie.";
  } else if (stats.phase === "Décision") {
    el.textContent = stats.maePct > stats.mfePct
      ? "À la décision, le risque domine le potentiel. Fermer ou alléger est cohérent."
      : "À la décision, le trade garde du potentiel. Conserver reste défendable si le plan est respecté.";
  } else {
    el.textContent = "Replay terminé. Compare ton choix avec l’issue réelle du trade.";
  }
}

function updateAIFeedbackAfterDecision(choice, data) {
  const el = document.getElementById("ai-feedback");
  if (!el) return;

  const ideal = String(trade.ideal_decision || "").toLowerCase();
  const label = choice === "close" ? "fermer" : choice === "hold" ? "conserver" : "alléger";

  if (ideal && ideal === choice) {
    el.textContent = `Bonne décision : ${label}. Ton choix correspond au scénario idéal détecté.`;
  } else if (data && data.feedback) {
    el.textContent = data.feedback;
  } else {
    el.textContent = `Décision enregistrée : ${label}. Le replay continue pour révéler le résultat.`;
  }
}

/* ================= UI/HYDRATION ================= */

function hydrateUI() {
  setText("hero-symbol", trade.symbol || "-");
  setText("hero-direction", trade.direction || "-");
  setText("result-badge", resultLabel(trade.result || trade.derived_result || "OPEN"));
  setText("chart-badge", `${trade.symbol || "-"} • ${trade.timeframe || "-"}`);

  setText("entry-price-box", formatPrice(trade.entry_price));
  setText("stop-loss-box", formatPrice(trade.stop_loss));
  setText("take-profit-box", formatPrice(trade.take_profit));
  setText("result-box", resultLabel(trade.result || trade.derived_result));

  setText("market-context", (trade.market_context || "Replay Elite TradingView mode.") + (trades.length > 1 ? ` • ${trades.length} trades` : ""));
  setText("post-analysis", trade.post_analysis || "");

  setText("side-symbol", trade.symbol || "-");
  setText("side-direction", trade.direction || "-");
  setText("side-entry", formatPrice(trade.entry_price));
  setText("side-sl", formatPrice(trade.stop_loss));
  setText("side-tp", formatPrice(trade.take_profit));
  setText("side-confidence", `${trade.confidence || 0}%`);
  setText("side-trend", trade.trend || "-");
  setText("side-rr", trade.risk_reward || trade.computed_rr || "-");
  setText("side-timeframe", trade.timeframe || "-");
  setText("side-result", resultLabel(trade.result || trade.derived_result));

  renderLessons();
  renderScoreWaiting();
}

function renderProgress() {
  const total = replayCandles.length;
  const played = Math.min(currentPos, total);
  const percent = Math.round((played / Math.max(1, total)) * 100);
  setText("progress-text", `${percent}%`);
  setText("candle-counter", `${played} / ${total}`);
  const bar = document.getElementById("progress-bar");
  if (bar) bar.style.width = `${percent}%`;
}

function renderLessons() {
  const el = document.getElementById("lessons-list");
  if (!el) return;
  const lessons = Array.isArray(trade.lessons) ? trade.lessons : [];
  el.innerHTML = lessons.length
    ? lessons.map(l => `<div class="lesson-item">${escapeHtml(l)}</div>`).join("")
    : `<div class="lesson-item">Aucune leçon disponible.</div>`;
}

function renderScoreWaiting() {
  setText("trader-score", "0");
  setText("trader-status", "En attente de décision");
  setText("discipline-score", "0/10");
  setText("timing-score", "0/10");
  setText("decision-feedback", "Le score apparaîtra après ton choix.");
}

function displayScore(data) {
  const score = Number(data.score || 0);
  setText("trader-score", score);
  setText("trader-status", data.status_text || data.status_label || "Décision analysée");
  setText("decision-feedback", data.feedback || "");
  setText("discipline-score", `${score}/10`);
  setText("timing-score", `${Number(data.timing_score ?? Math.max(0, score - 2))}/10`);
}

/* ================= HELPERS ================= */

function toChartCandle(c) {
  return { time: c.time, open: c.open, high: c.high, low: c.low, close: c.close };
}

function toUnixTime(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor(d.getTime() / 1000);
}

function nearestIndexByTime(timeValue, fallback) {
  if (!timeValue) return fallback;
  const t = toUnixTime(timeValue);
  if (!t) return fallback;

  let best = fallback;
  let diff = Infinity;
  candles.forEach((c, i) => {
    const d = Math.abs(c.time - t);
    if (d < diff) {
      diff = d;
      best = i;
    }
  });
  return best;
}

function clampIndex(value, fallback = 0) {
  const max = Math.max(0, candles.length - 1);
  const n = Number(value);
  if (!Number.isFinite(n)) return Math.max(0, Math.min(Number(fallback) || 0, max));
  return Math.max(0, Math.min(Math.round(n), max));
}

function outcomeIsWin() {
  return String(trade.result || trade.derived_result || "").toUpperCase() === "WIN";
}

function resultLabel(value) {
  const v = String(value || "OPEN").toUpperCase();
  return v === "BREAKEVEN" ? "BE" : v;
}

function formatPrice(value) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (Math.abs(n) >= 1000) return n.toFixed(2);
  if (Math.abs(n) >= 1) return n.toFixed(4);
  return n.toFixed(6);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "-";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

window.startReplay = startReplay;
window.pauseReplay = pauseReplay;
window.stepReplay = stepReplay;
window.resetReplay = resetReplay;
window.setSpeed = setSpeed;
window.makeDecision = makeDecision;
