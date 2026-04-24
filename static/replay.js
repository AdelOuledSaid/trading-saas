console.log("REPLAY JS FINAL TIMELINE-ALIGNED LOADED");

let chart = null;
let replayTimer = null;
let speed = 900;

let rawData = null;
let candles = [];
let htfCandles = [];
let events = [];
let trade = null;

let currentIndex = 0;
let entryIndex = 0;
let decisionIndex = 0;
let exitIndex = 0;

let decisionMade = false;
let replayFinished = false;
let replayStoppedByOutcome = false;
let revealedEvents = new Set();
let activeHintTimeout = null;

// =========================
// INIT
// =========================
async function initReplay() {
    try {
        const res = await fetch(replayApiBase);
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || "Erreur de chargement du replay");
        }

        rawData = data;
        candles = sanitizeCandles(Array.isArray(data.candles) ? data.candles : []);
        htfCandles = sanitizeCandles(Array.isArray(data.higher_timeframe_candles) ? data.higher_timeframe_candles : []);
        events = Array.isArray(data.events) ? data.events : [];
        trade = data.trade || {};

        normalizeReplayFlow();
        hydrateStaticUI();
        ensureAdvancedPanels();
        initChart();

        if (!candles.length) {
            throw new Error(buildEmptyReplayMessage(data.debug || {}));
        }

        

        currentIndex = entryIndex || 1;

        renderChart(currentIndex);
        renderEvents(events);
        renderLessons(Array.isArray(trade.lessons) ? trade.lessons : []);
        renderTimeline();
        updateMeta(currentIndex);
        updateScoreWaiting();
        updateLiveStats(currentIndex);
        updateMarketState(currentIndex);
        updateHTFDesk();
        updateDecisionAssistant(currentIndex);
        highlightTimeline(currentIndex - 1);
        revealEventsUpTo(currentIndex - 1);
    } catch (error) {
        console.error(error);
        const chartEl = document.getElementById("chart");
        if (chartEl) {
            chartEl.innerHTML = `<div class="chart-error">${escapeHtml(error.message)}</div>`;
        }
    }
}

// =========================
// DATA SANITIZE
// =========================
function sanitizeCandles(input) {
    const list = (input || [])
        .map((c) => ({
            time: normalizeIsoTime(c.time),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
            volume: c.volume == null ? null : Number(c.volume),
        }))
        .filter((c) => c.time && [c.open, c.high, c.low, c.close].every(Number.isFinite))
        .sort((a, b) => safeTimestamp(a.time) - safeTimestamp(b.time));

    const unique = [];
    const seen = new Set();

    list.forEach((candle) => {
        if (seen.has(candle.time)) return;
        seen.add(candle.time);

        unique.push({
            ...candle,
            high: Math.max(candle.high, candle.open, candle.close, candle.low),
            low: Math.min(candle.low, candle.open, candle.close, candle.high),
            index: unique.length,
        });
    });

    return unique;
}

function clampIndex(value, fallback = 0) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
        return Math.max(0, Math.min(fallback, Math.max(0, candles.length - 1)));
    }
    return Math.max(0, Math.min(Math.round(num), Math.max(0, candles.length - 1)));
}

// =========================
// FLOW NORMALIZATION
// =========================
function normalizeReplayFlow() {
    entryIndex = clampIndex(trade?.entry_index, 0);
    decisionIndex = clampIndex(trade?.decision_index, entryIndex + 1);
    exitIndex = clampIndex(trade?.exit_index, Math.min(candles.length - 1, entryIndex + 2));

    if (decisionIndex < entryIndex) {
        decisionIndex = entryIndex;
    }

    if (exitIndex < decisionIndex) {
        exitIndex = decisionIndex;
    }

    events = (events || []).map((evt, idx) => ({
        ...evt,
        id: evt.id || `${evt.type || "event"}-${idx}`,
        index: clampIndex(evt.index, inferEventIndex(evt.type)),
    }));

    replayStoppedByOutcome = false;
}

function inferEventIndex(type) {
    const t = String(type || "").toLowerCase();
    if (t === "entry") return entryIndex;
    if (t === "decision") return decisionIndex;
    if (["tp_hit", "sl_hit", "breakeven", "open"].includes(t)) return exitIndex;
    return entryIndex;
}

function computeInitialIndex() {
    if (!candles.length) return 0;
    return Math.max(1, entryIndex - Math.min(20, entryIndex));
}

// =========================
// UI BUILDERS
// =========================
function ensureAdvancedPanels() {
    const mainColumn = document.querySelector(".replay-main-column");
    const sideColumn = document.querySelector(".replay-side-column");

    if (mainColumn && !document.getElementById("replay-intelligence-card")) {
        const intelligenceCard = document.createElement("section");
        intelligenceCard.className = "intel-card";
        intelligenceCard.id = "replay-intelligence-card";
        intelligenceCard.innerHTML = `
            <div class="panel-head">
                <div>
                    <span class="panel-kicker">Desk intelligence</span>
                    <h3>Lecture tactique du replay</h3>
                </div>
                <div class="panel-badge" id="market-phase-badge">Phase -</div>
            </div>

            <div class="intel-grid">
                <div class="intel-box">
                    <span>État du marché</span>
                    <strong id="market-state-text">Observation</strong>
                    <small id="market-state-subtext">Chargement...</small>
                </div>

                <div class="intel-box">
                    <span>Pression du prix</span>
                    <strong id="pressure-text">Neutre</strong>
                    <small id="pressure-subtext">Structure en lecture</small>
                </div>

                <div class="intel-box">
                    <span>Momentum local</span>
                    <strong id="momentum-text">N/A</strong>
                    <small id="momentum-subtext">Analyse glissante</small>
                </div>

                <div class="intel-box">
                    <span>Statut du plan</span>
                    <strong id="plan-status-text">En préparation</strong>
                    <small id="plan-status-subtext">Aucune invalidation détectée</small>
                </div>
            </div>

            <div class="hint-stream" id="hint-stream">
                <div class="hint-item neutral">Le replay analysera la structure au fil des bougies.</div>
            </div>
        `;
        mainColumn.insertBefore(intelligenceCard, document.querySelector(".training-card"));
    }

    if (mainColumn && !document.getElementById("replay-htf-card")) {
        const htfCard = document.createElement("section");
        htfCard.className = "intel-card";
        htfCard.id = "replay-htf-card";
        htfCard.innerHTML = `
            <div class="panel-head">
                <div>
                    <span class="panel-kicker">Multi-timeframe</span>
                    <h3>Overlay supérieur</h3>
                </div>
                <div class="panel-badge" id="htf-bias-badge">HTF -</div>
            </div>

            <div class="intel-grid">
                <div class="intel-box">
                    <span>Timeframe principal</span>
                    <strong id="htf-primary-tf">-</strong>
                    <small>Lecture d’exécution</small>
                </div>

                <div class="intel-box">
                    <span>Timeframe supérieur</span>
                    <strong id="htf-higher-tf">-</strong>
                    <small>Lecture structurelle</small>
                </div>

                <div class="intel-box">
                    <span>Biais HTF</span>
                    <strong id="htf-bias-text">-</strong>
                    <small id="htf-bias-subtext">Contexte supérieur</small>
                </div>

                <div class="intel-box">
                    <span>Zones HTF</span>
                    <strong id="htf-zone-count">0</strong>
                    <small id="htf-zone-subtext">Aucune zone</small>
                </div>
            </div>
        `;
        mainColumn.insertBefore(htfCard, document.querySelector(".training-card"));
    }

    if (mainColumn && !document.getElementById("decision-assistant-card")) {
        const decisionCard = document.createElement("section");
        decisionCard.className = "analysis-card";
        decisionCard.id = "decision-assistant-card";
        decisionCard.innerHTML = `
            <div class="panel-head">
                <div>
                    <span class="panel-kicker">Decision assistant</span>
                    <h3>Aide à la décision</h3>
                </div>
            </div>

            <div class="analysis-split">
                <div class="analysis-box">
                    <h4>Contexte de décision</h4>
                    <p id="decision-context-text">Chargement...</p>
                </div>

                <div class="analysis-box">
                    <h4>Lecture de risque</h4>
                    <p id="decision-risk-text">Chargement...</p>
                </div>
            </div>
        `;
        mainColumn.insertBefore(decisionCard, document.querySelector(".lessons-card"));
    }

    if (sideColumn && !document.getElementById("trader-benchmark-card")) {
        const benchCard = document.createElement("section");
        benchCard.className = "benchmark-card";
        benchCard.id = "trader-benchmark-card";
        benchCard.innerHTML = `
            <div class="panel-head">
                <div>
                    <span class="panel-kicker">Benchmark</span>
                    <h3>Comparatif trader</h3>
                </div>
            </div>

            <div class="benchmark-grid">
                <div class="benchmark-box">
                    <span>Ton score</span>
                    <strong id="bench-user-score">0/10</strong>
                </div>

                <div class="benchmark-box">
                    <span>Moyenne desk</span>
                    <strong id="bench-desk-score">6.4/10</strong>
                </div>

                <div class="benchmark-box">
                    <span>Position</span>
                    <strong id="bench-ranking">Top 50%</strong>
                </div>

                <div class="benchmark-box">
                    <span>Niveau</span>
                    <strong id="bench-level">Observer</strong>
                </div>
            </div>

            <div class="benchmark-progress-wrap">
                <div class="benchmark-progress-label">
                    <span>Progression trader</span>
                    <strong id="bench-progress-text">0%</strong>
                </div>
                <div class="benchmark-progress">
                    <div class="benchmark-progress-fill" id="bench-progress-fill"></div>
                </div>
            </div>
        `;
        sideColumn.insertBefore(benchCard, document.querySelector(".side-note-card"));
    }
}

function hydrateStaticUI() {
    setText("hero-symbol", trade.symbol || "-");
    setText("hero-direction", trade.direction || "-");
    setText("hero-confidence", `${trade.confidence || 0}%`);
    setText("hero-rr", trade.risk_reward || trade.computed_rr || "-");

    setText("side-symbol", trade.symbol || "-");
    setText("side-direction", trade.direction || "-");
    setText("side-entry", formatPrice(trade.entry_price));
    setText("side-sl", formatPrice(trade.stop_loss));
    setText("side-tp", formatPrice(trade.take_profit));
    setText("side-confidence", `${trade.confidence || 0}%`);
    setText("side-trend", formatTrendText(trade.trend || inferTrendFromData()));
    setText("side-rr", trade.risk_reward || trade.computed_rr || "-");
    setText("side-timeframe", trade.timeframe || "-");
    setText("side-result", formatResultLabel(trade.result || trade.derived_result));

    setText("entry-price-box", formatPrice(trade.entry_price));
    setText("stop-loss-box", formatPrice(trade.stop_loss));
    setText("take-profit-box", formatPrice(trade.take_profit));
    setText("result-box", formatResultLabel(trade.result || trade.derived_result));

    setText("market-context", trade.market_context || "Aucune analyse de contexte disponible.");
    setText("post-analysis", trade.post_analysis || "Aucune analyse post-trade disponible.");

    setText("setup-grade-badge", `Setup ${trade.setup_grade || "-"}`);
    setText("difficulty-badge", trade.difficulty || "Difficulty -");
    setText("chart-badge", `${trade.symbol || "-"} • ${trade.timeframe || "-"}`);

    const resultBadge = document.getElementById("result-badge");
    if (resultBadge) {
        const resultUpper = String(trade.result || trade.derived_result || "OPEN").toUpperCase();
        resultBadge.textContent = formatResultLabel(resultUpper);
        resultBadge.classList.remove("status-open", "status-win", "status-loss");
        if (resultUpper === "WIN") {
            resultBadge.classList.add("status-win");
        } else if (resultUpper === "LOSS") {
            resultBadge.classList.add("status-loss");
        } else {
            resultBadge.classList.add("status-open");
        }
    }

    const directionEls = [
        document.getElementById("hero-direction"),
        document.getElementById("side-direction")
    ];

    directionEls.forEach((el) => {
        if (!el) return;
        el.classList.remove("BUY", "SELL", "buy", "sell");
        const dir = String(trade.direction || "").toUpperCase();
        if (dir === "BUY") {
            el.classList.add("buy");
        } else if (dir === "SELL") {
            el.classList.add("sell");
        }
    });
}

function updateHTFDesk() {
    setText("htf-primary-tf", String(trade.timeframe || "-").toUpperCase());
    setText("htf-higher-tf", String(trade.higher_timeframe || "-").toUpperCase());

    const bias = String(trade.htf_bias || "NEUTRAL").toUpperCase();
    setText("htf-bias-badge", `HTF ${bias}`);
    setText("htf-bias-text", bias);
    setText(
        "htf-bias-subtext",
        bias === "BULLISH"
            ? "Structure supérieure favorable à la hausse"
            : bias === "BEARISH"
                ? "Structure supérieure orientée vendeuse"
                : "Structure supérieure neutre"
    );

    const zones = Array.isArray(trade?.htf_zones) ? trade.htf_zones : [];
    setText("htf-zone-count", String(zones.length));
    setText("htf-zone-subtext", zones.length ? zones.map((z) => z.label).join(" • ") : "Aucune zone détectée");
}

function updateDecisionAssistant(index) {
    setText("decision-context-text", trade?.decision_context || "Aucun contexte de décision disponible.");

    const health = String(trade?.trade_health || "unknown").toLowerCase();
    const structure = String(trade?.market_structure || "neutral").toLowerCase();

    const parts = [
        `Santé du trade : ${formatHealthLabel(health)}.`,
        `Structure : ${structure}.`,
        trade?.distance_to_sl_percent != null ? `Distance SL : ${trade.distance_to_sl_percent}%.` : null,
        trade?.distance_to_tp_percent != null ? `Distance TP : ${trade.distance_to_tp_percent}%.` : null,
        trade?.max_favorable_excursion_percent != null ? `MFE : ${trade.max_favorable_excursion_percent}%.` : null,
        trade?.max_adverse_excursion_percent != null ? `MAE : ${trade.max_adverse_excursion_percent}%.` : null,
        index < decisionIndex ? "Le moment critique n’est pas encore atteint." : "Le moment critique est atteint ou dépassé."
    ].filter(Boolean);

    setText("decision-risk-text", parts.join(" "));
}

// =========================
// CHART
// =========================
function initChart() {
    const chartDom = document.getElementById("chart");
    if (!chartDom) return;

    chartDom.style.width = "100%";
    chartDom.style.height = "540px";
    chartDom.style.minHeight = "540px";

    chart = echarts.init(chartDom, null, { renderer: "canvas" });

    setTimeout(() => {
        if (chart) chart.resize();
    }, 100);

    window.addEventListener("resize", () => {
        if (chart) chart.resize();
    });
}

function renderChart(lastIndex) {
    if (!chart || !candles.length) return;

    const safeEnd = Math.max(1, Math.min(lastIndex, candles.length));
    const visibleCandles = candles.slice(0, safeEnd);

    if (!visibleCandles.length) return;

    const categoryData = visibleCandles.map((_, i) => i);
    const klineData = visibleCandles.map((c) => [c.open, c.close, c.low, c.high]);
    const eventPoints = buildEventPoints(visibleCandles);
    const priceLines = buildPriceLines();
    const zones = computeZones(visibleCandles).concat(buildHTFZoneAreas(visibleCandles));
    const htfOverlayLine = buildHTFOverlayLine(visibleCandles);
    const latestClose = visibleCandles[visibleCandles.length - 1]?.close ?? null;

    const lows = visibleCandles.map((c) => c.low).filter(Number.isFinite);
    const highs = visibleCandles.map((c) => c.high).filter(Number.isFinite);
    const minPrice = lows.length ? Math.min(...lows) : 0;
    const maxPrice = highs.length ? Math.max(...highs) : 1;
    const padding = (maxPrice - minPrice) * 0.08 || 1;

    chart.setOption(
        {
            backgroundColor: "#07111f",
            animation: false,
            grid: {
                left: 16,
                right: 16,
                top: 20,
                bottom: 45,
                containLabel: true
            },
            tooltip: {
                trigger: "axis",
                axisPointer: {
                    type: "cross",
                    lineStyle: {
                        color: "rgba(148,163,184,0.25)",
                        width: 1,
                        type: "dashed"
                    }
                },
                backgroundColor: "rgba(8,18,33,0.96)",
                borderColor: "rgba(59,130,246,0.18)",
                borderWidth: 1,
                textStyle: {
                    color: "#e5edf7",
                    fontSize: 12
                },
                extraCssText: "box-shadow: 0 16px 40px rgba(0,0,0,0.35); border-radius: 12px;",
                formatter(params) {
                    const candleParam = params.find((p) => p.seriesName === "Price") || params[0];
                    const row = visibleCandles[candleParam?.dataIndex];
                    if (!row) return "";

                    return `
                        <div style="min-width:220px;">
                            <div style="font-weight:700;margin-bottom:10px;color:#dbe8ff;">${formatTime(row.time)}</div>
                            <div style="display:flex;justify-content:space-between;gap:16px;"><span>Open</span><strong>${formatPrice(row.open)}</strong></div>
                            <div style="display:flex;justify-content:space-between;gap:16px;"><span>High</span><strong>${formatPrice(row.high)}</strong></div>
                            <div style="display:flex;justify-content:space-between;gap:16px;"><span>Low</span><strong>${formatPrice(row.low)}</strong></div>
                            <div style="display:flex;justify-content:space-between;gap:16px;"><span>Close</span><strong>${formatPrice(row.close)}</strong></div>
                            ${latestClose !== null ? `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08);"><span>Last</span><strong>${formatPrice(latestClose)}</strong></div>` : ""}
                        </div>
                    `;
                }
            },
            xAxis: {
                type: "category",
                data: categoryData,
                boundaryGap: true,
                axisLine: {
                    lineStyle: { color: "rgba(148,163,184,0.14)" }
                },
                axisTick: { show: false },
                axisLabel: {
                    color: "#94a3b8",
                    fontSize: 11,
                    margin: 12,
                    formatter: (value) => formatTimeCompact(visibleCandles[value]?.time)
                },
                splitLine: { show: false }
            },
            yAxis: {
                scale: true,
                min: minPrice - padding,
                max: maxPrice + padding,
                position: "right",
                axisLine: {
                    lineStyle: { color: "rgba(148,163,184,0.14)" }
                },
                axisTick: { show: false },
                axisLabel: {
                    color: "#94a3b8",
                    fontSize: 11,
                    formatter: (value) => formatAxisPrice(value)
                },
                splitLine: {
                    lineStyle: {
                        color: "rgba(148,163,184,0.06)",
                        type: "solid"
                    }
                }
            },
            dataZoom: [
                {
                    type: "inside",
                    start: 0,
                    end: 100
                }
            ],
            series: [
                {
                    name: "HTF Overlay",
                    type: "line",
                    data: htfOverlayLine,
                    smooth: true,
                    symbol: "none",
                    lineStyle: {
                        width: 1,
                        opacity: 0.18,
                        color: "#8b5cf6"
                    },
                    z: 1
                },
                {
                    name: "Price",
                    type: "candlestick",
                    data: klineData,
                    barWidth: 6,
                    itemStyle: {
                        color: "#22c55e",
                        color0: "#ef4444",
                        borderColor: "#22c55e",
                        borderColor0: "#ef4444",
                        borderWidth: 1
                    },
                    markLine: {
                        symbol: ["none", "none"],
                        silent: true,
                        data: priceLines,
                        label: {
                            color: "#dbe4f1",
                            backgroundColor: "rgba(8,18,33,0.84)",
                            padding: [4, 8],
                            borderRadius: 6,
                            formatter(param) {
                                if (!param || !param.name) return "";
                                if (param.name === "Entry") return `Entry ${formatPrice(trade.entry_price)}`;
                                if (param.name === "SL") return `SL ${formatPrice(trade.stop_loss)}`;
                                if (param.name === "TP") return `TP ${formatPrice(trade.take_profit)}`;
                                return param.name;
                            }
                        }
                    },
                    markPoint: {
                        symbol: "circle",
                        symbolSize: 10,
                        data: eventPoints
                    },
                    markArea: {
                        silent: true,
                        itemStyle: {
                            color: "rgba(59,130,246,0.03)"
                        },
                        data: zones
                    },
                    z: 3
                }
            ]
        },
        true
    );

    setTimeout(() => {
        if (chart) chart.resize();
    }, 50);
}

function buildPriceLines() {
    const lines = [];

    if (trade.entry_price != null) {
        lines.push({
            name: "Entry",
            yAxis: trade.entry_price,
            lineStyle: {
                width: 1.2,
                type: "solid",
                opacity: 0.75,
                color: "#22c55e"
            },
            label: { position: "end" }
        });
    }

    if (trade.stop_loss != null) {
        lines.push({
            name: "SL",
            yAxis: trade.stop_loss,
            lineStyle: {
                width: 1,
                type: "dashed",
                opacity: 0.58,
                color: "#ef4444"
            },
            label: { position: "end" }
        });
    }

    if (trade.take_profit != null) {
        lines.push({
            name: "TP",
            yAxis: trade.take_profit,
            lineStyle: {
                width: 1,
                type: "dashed",
                opacity: 0.58,
                color: "#3b82f6"
            },
            label: { position: "end" }
        });
    }

    return lines;
}

function buildEventPoints(visibleCandles) {
    return (events || [])
        .filter((e) => typeof e.index === "number" && e.index >= 0 && e.index < visibleCandles.length)
        .map((e) => ({
            coord: [e.index, e.price_level ?? visibleCandles[e.index]?.close ?? null],
            value: e.title,
            itemStyle: {
                color: eventColor(e.type),
                borderColor: "#07111f",
                borderWidth: 2
            },
            label: { show: false }
        }))
        .filter((p) => Array.isArray(p.coord) && p.coord[1] != null && Number.isFinite(Number(p.coord[1])));
}

function buildHTFOverlayLine(visibleCandles) {
    if (!htfCandles.length || !visibleCandles.length) {
        return visibleCandles.map(() => null);
    }

    return visibleCandles.map((current) => {
        const currentTs = safeTimestamp(current.time);
        let nearest = null;
        let bestDiff = null;

        htfCandles.forEach((htf) => {
            const diff = Math.abs(safeTimestamp(htf.time) - currentTs);
            if (bestDiff === null || diff < bestDiff) {
                bestDiff = diff;
                nearest = htf;
            }
        });

        return nearest ? nearest.close : null;
    });
}

function computeZones(visibleCandles) {
    if (visibleCandles.length < 8) return [];

    const highs = visibleCandles.map((c) => c.high).filter(Number.isFinite);
    const lows = visibleCandles.map((c) => c.low).filter(Number.isFinite);

    if (!highs.length || !lows.length) return [];

    const high = Math.max(...highs);
    const low = Math.min(...lows);
    const range = high - low;

    if (range <= 0) return [];

    const premiumBottom = high - range * 0.12;
    const discountTop = low + range * 0.12;
    const start = 0;
    const end = visibleCandles.length - 1;

    return [
        [{ xAxis: start, yAxis: premiumBottom }, { xAxis: end, yAxis: high }],
        [{ xAxis: start, yAxis: low }, { xAxis: end, yAxis: discountTop }]
    ];
}

function buildHTFZoneAreas(visibleCandles) {
    const zones = Array.isArray(trade?.htf_zones) ? trade.htf_zones : [];
    if (!zones.length || !visibleCandles.length) return [];

    const start = 0;
    const end = visibleCandles.length - 1;

    return zones
        .filter((z) => z.low != null && z.high != null)
        .map((z) => [
            { xAxis: start, yAxis: z.low },
            { xAxis: end, yAxis: z.high }
        ]);
}

// =========================
// REPLAY CONTROL
// =========================
function replayStep() {
    if (currentIndex >= candles.length) {
        pauseReplay();
        replayFinished = true;
        updateMeta(candles.length);
        finalizeReplay();
        return;
    }

    currentIndex += 1;

    if (
        Number.isFinite(exitIndex) &&
        trade?.should_stop_replay_at_exit &&
        currentIndex >= exitIndex &&
        currentIndex > decisionIndex
    ) {
        currentIndex = exitIndex;
        replayStoppedByOutcome = true;
    }

    renderChart(currentIndex);
    updateMeta(currentIndex);
    updateLiveStats(currentIndex);
    updateMarketState(currentIndex);
    updateDecisionAssistant(currentIndex);
    highlightTimeline(currentIndex - 1);
    revealEventsUpTo(currentIndex - 1);
    maybeEmitAdaptiveHints(currentIndex - 1);
    checkDecisionMoment(currentIndex - 1);

    if (replayStoppedByOutcome) {
        pauseReplay();
        replayFinished = true;
        finalizeReplay();
    }
}

function startReplay() {
    if (!candles.length) return;
    if (replayTimer) return;

    replayTimer = setInterval(() => {

        if (currentIndex >= candles.length) {
            pauseReplay();
            return;
        }

        currentIndex++;

        renderChart(currentIndex);
        updateMeta(currentIndex);

    }, 400); // vitesse
}

function pauseReplay() {
    if (replayTimer) {
        clearInterval(replayTimer);
        replayTimer = null;
    }
}

function stepReplay() {
    pauseReplay();
    replayStep();
}

function resetReplay() {
    pauseReplay();
    decisionMade = false;
    replayFinished = false;
    replayStoppedByOutcome = false;
    revealedEvents = new Set();

    currentIndex = computeInitialIndex();

    const decisionBox = document.getElementById("decision-box");
    if (decisionBox) decisionBox.classList.add("hidden");

    setText("decision-mode-text", "En attente");
    updateScoreWaiting();
    renderChart(currentIndex);
    updateMeta(currentIndex);
    updateLiveStats(currentIndex);
    updateMarketState(currentIndex);
    updateDecisionAssistant(currentIndex);
    renderTimeline();
    highlightTimeline(currentIndex - 1);
    revealEventsUpTo(currentIndex - 1);

    const hintStream = document.getElementById("hint-stream");
    if (hintStream) {
        hintStream.innerHTML = `<div class="hint-item neutral">Le replay analysera la structure au fil des bougies.</div>`;
    }
}

function setSpeed(multiplier) {
    speed = 900 / multiplier;
    if (replayTimer) {
        pauseReplay();
        startReplay();
    }
}

// =========================
// META / LIVE UI
// =========================
function updateMeta(index) {
    const total = candles.length || 1;
    const safeIndex = Math.max(1, Math.min(index, total));
    const progress = Math.round((safeIndex / total) * 100);

    setText("progress-text", `${progress}%`);
    setText("candle-counter", `${safeIndex} / ${candles.length}`);

    const progressBar = document.getElementById("progress-bar");
    if (progressBar) progressBar.style.width = `${progress}%`;
}

function updateLiveStats(index) {
    const current = candles[Math.max(0, index - 1)];
    const prev = candles[Math.max(0, index - 2)] || current;

    if (!current || !prev) return;

    const delta = current.close - prev.close;
    const deltaPct = prev.close ? ((delta / prev.close) * 100) : 0;

    const pressure = delta > 0 ? "Acheteurs" : delta < 0 ? "Vendeurs" : "Neutre";
    const momentum = Math.abs(deltaPct);

    setText("pressure-text", pressure);
    setText("pressure-subtext", `${delta >= 0 ? "+" : ""}${deltaPct.toFixed(2)}% sur la bougie active`);
    setText("momentum-text", momentum >= 0.25 ? "Fort" : momentum >= 0.1 ? "Modéré" : "Faible");
    setText("momentum-subtext", `Variation ${Math.abs(delta).toFixed(2)} pts`);
}

function updateMarketState(index) {
    const state = inferReplayState(index);
    setText("market-state-text", state.title);
    setText("market-state-subtext", state.subtitle);
    setText("market-phase-badge", state.phase);
    setText("plan-status-text", state.planTitle);
    setText("plan-status-subtext", state.planSubtitle);
}

// =========================
// DECISION
// =========================
function checkDecisionMoment(index) {
    if (decisionMade || decisionIndex == null) return;

    if (index === Math.max(0, decisionIndex - 2)) {
        showHint("Zone de décision à venir. Prépare ton jugement avant que le prix ne te force à réagir.", "warning");
    }

    if (index === decisionIndex) {
        pauseReplay();
        showDecisionBox();
        setText("decision-mode-text", "Décision requise");
        showHint("Moment critique atteint. Maintenant, on évalue ta gestion du trade.", "warning");
    }
}

function showDecisionBox() {
    const el = document.getElementById("decision-box");
    if (el) el.classList.remove("hidden");
}

async function makeDecision(choice) {
    try {
        const res = await fetch(`${replayApiBase}/decision`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ decision: choice })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || "Erreur pendant la sauvegarde");
        }

        decisionMade = true;
        displayScore(data);

        const el = document.getElementById("decision-box");
        if (el) el.classList.add("hidden");

        setText("decision-mode-text", `Choix: ${labelDecision(choice)}`);
        showHint(`Décision enregistrée: ${labelDecision(choice)}. Le replay reprend pour révéler l’issue du scénario.`, "good");
        startReplay();
    } catch (error) {
        console.error(error);
        alert(error.message);
    }
}

// =========================
// SCORE / BENCHMARK
// =========================
function displayScore(data) {
    const score = Number(data.score ?? 0);

    setText("trader-score", score);
    setText("trader-status", data.status_text || "Résultat");
    setText("decision-feedback", data.feedback || "");

    const statusEl = document.getElementById("trader-status");
    if (statusEl) {
        statusEl.classList.remove("score-good", "score-medium", "score-bad");
        if (data.status === "good") {
            statusEl.classList.add("score-good");
        } else if (data.status === "medium") {
            statusEl.classList.add("score-medium");
        } else {
            statusEl.classList.add("score-bad");
        }
    }

    setText("discipline-score", `${score}/10`);
    setText("timing-score", `${Number(data.timing_score ?? Math.max(0, score - 2))}/10`);

    updateBenchmark(score);
}

function updateScoreWaiting() {
    setText("trader-score", "0");
    setText("trader-status", "En attente de décision");
    setText(
        "decision-feedback",
        String(trade?.result || "").toUpperCase() === "OPEN"
            ? "Trade actif : la décision porte sur la gestion d’un scénario encore ouvert."
            : "Le score apparaîtra après ton choix."
    );
    setText("discipline-score", "0/10");
    setText("timing-score", "0/10");
    updateBenchmark(0);

    const statusEl = document.getElementById("trader-status");
    if (statusEl) {
        statusEl.classList.remove("score-good", "score-medium", "score-bad");
    }
}

function updateBenchmark(score) {
    setText("bench-user-score", `${score}/10`);

    let ranking = "Top 50%";
    let level = "Observer";
    let progress = 18;

    if (score >= 9) {
        ranking = "Top 8%";
        level = "Execution Pro";
        progress = 92;
    } else if (score >= 7) {
        ranking = "Top 22%";
        level = "Disciplined";
        progress = 74;
    } else if (score >= 5) {
        ranking = "Top 40%";
        level = "Developing";
        progress = 52;
    } else if (score >= 3) {
        ranking = "Top 58%";
        level = "Reactive";
        progress = 34;
    }

    setText("bench-ranking", ranking);
    setText("bench-level", level);
    setText("bench-progress-text", `${progress}%`);

    const fill = document.getElementById("bench-progress-fill");
    if (fill) fill.style.width = `${progress}%`;
}

// =========================
// TIMELINE / EVENTS
// =========================
function renderTimeline() {
    let timelineWrap = document.getElementById("replay-timeline");
    const progressBar = document.querySelector(".replay-progress");

    if (!progressBar) return;

    if (!timelineWrap) {
        timelineWrap = document.createElement("div");
        timelineWrap.id = "replay-timeline";
        timelineWrap.className = "replay-timeline";
        progressBar.insertAdjacentElement("afterend", timelineWrap);
    }

    const timelinePoints = buildOrderedTimelinePoints();

    let lastLeft = -999;

    timelineWrap.innerHTML = timelinePoints.map((point, idx) => {
        let pct = candles.length > 1 ? (point.index / (candles.length - 1)) * 100 : 0;

        if (pct - lastLeft < 8) {
            pct = lastLeft + 8;
        }

        if (pct > 100) pct = 100;
        lastLeft = pct;

        const extraClass = idx % 2 === 0 ? "label-top" : "label-bottom";

        return `
            <div class="timeline-node ${point.type} ${extraClass}" data-index="${point.index}" style="left:${pct}%;">
                <span class="timeline-dot"></span>
                <small>${escapeHtml(point.label)}</small>
            </div>
        `;
    }).join("");
}

function buildOrderedTimelinePoints() {
    return [
        {
            type: "entry",
            label: "Entrée",
            index: entryIndex
        },
        {
            type: "decision",
            label: "Décision",
            index: decisionIndex
        },
        {
            type: "outcome",
            label: formatOutcomeTimelineLabel(),
            index: exitIndex
        }
    ].sort((a, b) => a.index - b.index);
}

function formatOutcomeTimelineLabel() {
    const result = String(trade?.result || trade?.derived_result || "OPEN").toUpperCase();
    if (result === "WIN") return "TP atteint";
    if (result === "LOSS") return "SL atteint";
    if (result === "BREAKEVEN") return "Break-even";
    return "OPEN";
}

function renderEvents(eventsList) {
    const container = document.getElementById("events");
    if (!container) return;

    if (!eventsList.length) {
        container.innerHTML = `<div class="event-card"><strong>Aucun événement</strong><p>Ce replay ne contient pas encore de timeline enrichie.</p></div>`;
        return;
    }

    container.innerHTML = eventsList.map((e) => `
        <div class="event-card" data-index="${e.index ?? ""}">
            <div class="event-top">
                <span class="event-type ${eventClass(e.type)}">${formatEventType(e.type)}</span>
                <span class="event-index">#${e.index ?? "-"}</span>
            </div>
            <strong>${escapeHtml(e.title || "Événement")}</strong>
            <p>${escapeHtml(e.description || "")}</p>
        </div>
    `).join("");
}

function revealEventsUpTo(index) {
    (events || []).forEach((e) => {
        if (typeof e.index !== "number") return;

        const key = e.id || `${e.type}-${e.index}`;
        if (e.index <= index && !revealedEvents.has(key)) {
            revealedEvents.add(key);
            showHint(`${formatEventType(e.type)} : ${e.title}`, eventHintTone(e.type));
        }
    });
}

function highlightTimeline(index) {
    document.querySelectorAll(".event-card").forEach((card) => {
        card.classList.remove("active");
        const eventIndex = Number(card.dataset.index);
        if (!Number.isNaN(eventIndex) && eventIndex <= index) {
            card.classList.add("active");
        }
    });

    document.querySelectorAll(".timeline-node").forEach((node) => {
        node.classList.remove("active");
        const nodeIndex = Number(node.dataset.index);
        if (!Number.isNaN(nodeIndex) && nodeIndex <= index) {
            node.classList.add("active");
        }
    });
}

// =========================
// LESSONS
// =========================
function renderLessons(lessons) {
    const container = document.getElementById("lessons-list");
    if (!container) return;

    if (!lessons.length) {
        container.innerHTML = `<div class="lesson-item">Aucune leçon disponible.</div>`;
        return;
    }

    container.innerHTML = lessons.map((lesson) => `
        <div class="lesson-item">${escapeHtml(lesson)}</div>
    `).join("");
}

// =========================
// ADAPTIVE HINTS
// =========================
function maybeEmitAdaptiveHints(index) {
    const current = candles[index];
    const previous = candles[index - 1];

    if (!current || !previous) return;

    const body = Math.abs(current.close - current.open);
    const fullRange = current.high - current.low || 1;
    const bodyRatio = body / fullRange;

    if (bodyRatio > 0.68) {
        showHint("Impulsion nette détectée. Le marché choisit une direction à court terme.", "good");
    }

    if (trade.stop_loss != null && touchesLevel(current, trade.stop_loss, 0.0008)) {
        showHint("Le prix teste dangereusement la zone du stop. La discipline devient prioritaire.", "bad");
    }

    if (trade.entry_price != null && touchesLevel(current, trade.entry_price, 0.0005)) {
        showHint("Retour sur la zone d’entrée. C’est souvent ici que les traders émotionnels dévient du plan.", "warning");
    }

    if (trade.take_profit != null && touchesLevel(current, trade.take_profit, 0.0008)) {
        showHint("Le prix s’approche de l’objectif. Observe si l’impulsion garde sa qualité.", "good");
    }

    if (String(trade.result || "").toUpperCase() === "OPEN" && index >= candles.length - 3) {
        showHint("Le trade reste ouvert. Le replay est ici un exercice de gestion, pas une conclusion finale.", "neutral");
    }
}

function showHint(message, tone = "neutral") {
    const container = document.getElementById("hint-stream");
    if (!container) return;

    const item = document.createElement("div");
    item.className = `hint-item ${tone}`;
    item.textContent = message;

    container.prepend(item);

    const items = container.querySelectorAll(".hint-item");
    if (items.length > 5) {
        items[items.length - 1].remove();
    }

    if (activeHintTimeout) {
        clearTimeout(activeHintTimeout);
    }

    activeHintTimeout = setTimeout(() => {
        item.classList.add("hint-fade");
    }, 2800);
}

function finalizeReplay() {
    const result = String(trade.result || trade.derived_result || "").toUpperCase();

    if (result === "WIN") {
        showHint("Issue finale : scénario gagnant. Le replay confirme la qualité du plan et de la gestion.", "good");
    } else if (result === "LOSS") {
        showHint("Issue finale : invalidation du plan. L’intérêt du replay est de corriger la lecture, pas de cacher l’erreur.", "bad");
    } else if (result === "OPEN") {
        showHint("Replay terminé sur un trade encore actif. L’enjeu est la gestion en cours, pas un résultat fermé.", "neutral");
    } else {
        showHint("Replay clos. Évalue la structure, la gestion, puis compare avec le plan initial.", "neutral");
    }
}

// =========================
// MARKET STATE ENGINE
// =========================
function inferReplayState(index) {
    const slice = candles.slice(0, Math.max(1, index));
    if (!slice.length) {
        return {
            title: "Observation",
            subtitle: "Chargement de la structure",
            phase: "Warm-up",
            planTitle: "En préparation",
            planSubtitle: "Le replay n’a pas encore démarré"
        };
    }

    const first = slice[0].close;
    const last = slice[slice.length - 1].close;
    const deltaPct = first ? ((last - first) / first) * 100 : 0;
    const latest = slice[slice.length - 1];

    let title = "Compression";
    let subtitle = "Le marché prépare un déplacement plus clair";
    let phase = "Compression";
    let planTitle = "Plan intact";
    let planSubtitle = "Aucune invalidation claire";

    if (Math.abs(deltaPct) > 0.45) {
        title = deltaPct > 0 ? "Expansion haussière" : "Expansion baissière";
        subtitle = deltaPct > 0
            ? "Les acheteurs imposent la séquence"
            : "Les vendeurs prennent le contrôle";
        phase = "Expansion";
    }

    if (latest && trade.entry_price != null) {
        const isAboveEntry = latest.close >= trade.entry_price;
        if (String(trade.direction || "").toUpperCase() === "BUY") {
            planTitle = isAboveEntry ? "Plan défendable" : "Plan sous pression";
            planSubtitle = isAboveEntry
                ? "Le prix reste au-dessus ou proche de la zone d’exécution"
                : "Le prix travaille sous la zone d’entrée";
        } else {
            planTitle = !isAboveEntry ? "Plan défendable" : "Plan sous pression";
            planSubtitle = !isAboveEntry
                ? "Le prix respecte la logique vendeuse"
                : "Le prix remonte contre la logique initiale";
        }
    }

    if (trade.stop_loss != null && latest && touchesLevel(latest, trade.stop_loss, 0.0006)) {
        planTitle = "Invalidation proche";
        planSubtitle = "Le stop est directement menacé";
        phase = "Stress test";
    }

    if (trade.take_profit != null && latest && touchesLevel(latest, trade.take_profit, 0.0008)) {
        phase = "Target approach";
        subtitle = "L’objectif devient visible";
    }

    if (String(trade.result || "").toUpperCase() === "OPEN" && index >= candles.length - 3) {
        phase = "Live management";
    }

    return { title, subtitle, phase, planTitle, planSubtitle };
}

function inferTrendFromData() {
    if (!candles.length) return "-";
    const first = candles[0].close;
    const last = candles[candles.length - 1].close;
    if (last > first) return "Bullish";
    if (last < first) return "Bearish";
    return "Range";
}

// =========================
// HELPERS
// =========================
function touchesLevel(candle, level, toleranceRatio = 0.001) {
    if (level == null || !candle) return false;
    const tolerance = Math.max(Math.abs(level) * toleranceRatio, 0.0000001);
    return candle.low <= level + tolerance && candle.high >= level - tolerance;
}

function eventColor(type) {
    const t = String(type || "").toLowerCase();
    if (t.includes("tp")) return "#3b82f6";
    if (t.includes("sl")) return "#ef4444";
    if (t.includes("entry")) return "#22c55e";
    if (t.includes("decision")) return "#f59e0b";
    if (t.includes("open")) return "#60a5fa";
    return "#a78bfa";
}

function eventClass(type) {
    const t = String(type || "").toLowerCase();
    if (t.includes("tp")) return "event-tp";
    if (t.includes("sl")) return "event-sl";
    if (t.includes("entry")) return "event-entry";
    if (t.includes("decision")) return "event-decision";
    return "event-context";
}

function eventHintTone(type) {
    const t = String(type || "").toLowerCase();
    if (t.includes("tp")) return "good";
    if (t.includes("sl")) return "bad";
    if (t.includes("decision")) return "warning";
    return "neutral";
}

function formatEventType(type) {
    const t = String(type || "").toLowerCase();
    if (t === "entry") return "Entrée";
    if (t === "context") return "Contexte";
    if (t === "decision") return "Décision";
    if (t === "tp_hit") return "TP atteint";
    if (t === "sl_hit") return "SL atteint";
    if (t === "open") return "Trade actif";
    if (t === "breakeven") return "Break-even";
    return type || "Event";
}

function labelDecision(choice) {
    if (choice === "close") return "Fermer";
    if (choice === "hold") return "Conserver";
    if (choice === "partial") return "Alléger";
    return choice;
}

function formatResultLabel(value) {
    const result = String(value || "OPEN").toUpperCase();
    if (result === "BREAKEVEN") return "BE";
    return result;
}

function formatTrendText(value) {
    const v = String(value || "").toLowerCase();
    if (v === "bullish") return "Bullish";
    if (v === "bearish") return "Bearish";
    if (v === "range") return "Range";
    return value || "-";
}

function formatHealthLabel(value) {
    const v = String(value || "").toLowerCase();
    if (v === "healthy") return "Healthy";
    if (v === "under_pressure") return "Under pressure";
    if (v === "critical") return "Critical";
    if (v === "invalidated") return "Invalidated";
    return "Unknown";
}

function formatPrice(value) {
    if (value == null || value === "") return "-";
    const num = Number(value);
    if (!Number.isFinite(num)) return String(value);
    if (Math.abs(num) >= 1000) return num.toFixed(2);
    if (Math.abs(num) >= 1) return num.toFixed(4);
    return num.toFixed(6);
}

function formatAxisPrice(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return value;
    if (Math.abs(num) >= 1000) return num.toLocaleString("en-US", { maximumFractionDigits: 0 });
    if (Math.abs(num) >= 1) return num.toLocaleString("en-US", { maximumFractionDigits: 2 });
    return num.toLocaleString("en-US", { maximumFractionDigits: 5 });
}

function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    const day = String(date.getUTCDate()).padStart(2, "0");
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const hours = String(date.getUTCHours()).padStart(2, "0");
    const minutes = String(date.getUTCMinutes()).padStart(2, "0");
    return `${day}/${month} ${hours}:${minutes}`;
}

function formatTimeCompact(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";

    const day = String(date.getUTCDate()).padStart(2, "0");
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const hours = String(date.getUTCHours()).padStart(2, "0");
    const minutes = String(date.getUTCMinutes()).padStart(2, "0");
    return `${day}/${month} ${hours}:${minutes}`;
}

function normalizeIsoTime(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString();
}

function safeTimestamp(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function escapeHtml(text) {
    return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function buildEmptyReplayMessage(debug) {
    const source = debug.source ? `Source: ${debug.source}. ` : "";
    const stored = debug.stored_len != null ? `Stored candles: ${debug.stored_len}. ` : "";
    const market = debug.market_raw_len != null ? `Market candles: ${debug.market_raw_len}. ` : "";
    return `${source}${stored}${market}Aucune bougie exploitable pour ce replay.`.trim();
}

window.addEventListener("load", initReplay);