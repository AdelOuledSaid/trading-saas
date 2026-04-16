let replayData = null;
let chart = null;
let candleSeries = null;
let index = 0;
let interval = null;
let speed = 700;
let eventElements = [];
let decisionShown = false;
let traderScore = 0;

async function loadReplay() {
    try {
        const res = await fetch(`/api/replay/${replayId}`);
        replayData = await res.json();

        if (!res.ok || !replayData || replayData.error) {
            console.error("Erreur replay:", replayData?.error || "Données invalides");
            renderChartMessage("Aucun replay disponible pour ce trade.");
            return;
        }

        if (!replayData.candles || replayData.candles.length === 0) {
            renderChartMessage("Ce replay ne contient pas encore de bougies.");
            return;
        }

        initChart();
        renderEvents();
        drawLines();
        updateScoreUI(
            0,
            "En attente de décision",
            "Le score apparaîtra après ton choix.",
            ""
        );

        // Démarrage automatique pour éviter une zone vide
        setTimeout(() => {
            startReplay();
        }, 300);

    } catch (error) {
        console.error("Erreur chargement replay:", error);
        renderChartMessage("Impossible de charger le replay.");
    }
}

function renderChartMessage(message) {
    const container = document.getElementById("chart");
    if (!container) return;

    container.innerHTML = `
        <div class="replay-empty-state">
            ${message}
        </div>
    `;
}

function initChart() {
    const container = document.getElementById("chart");
    if (!container) {
        console.error("Container #chart introuvable");
        return;
    }

    // Nettoyage si reset / reload
    container.innerHTML = "";

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 430,
        layout: {
            background: { color: "#031124" },
            textColor: "#cbd5e1",
        },
        grid: {
            vertLines: { color: "rgba(148,163,184,0.08)" },
            horzLines: { color: "rgba(148,163,184,0.08)" },
        },
        rightPriceScale: {
            borderColor: "rgba(148,163,184,0.15)",
        },
        timeScale: {
            borderColor: "rgba(148,163,184,0.15)",
            timeVisible: true,
            secondsVisible: false,
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
    });

    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
    });

    window.addEventListener("resize", () => {
        if (chart) {
            chart.applyOptions({
                width: container.clientWidth
            });
        }
    });
}

function normalizeTime(value) {
    return Math.floor(new Date(value).getTime() / 1000);
}

function drawLines() {
    if (!candleSeries || !replayData || !replayData.trade) return;

    const trade = replayData.trade;

    candleSeries.createPriceLine({
        price: Number(trade.entry_price),
        color: "#38bdf8",
        lineWidth: 2,
        axisLabelVisible: true,
        title: "Entrée",
    });

    if (trade.stop_loss) {
        candleSeries.createPriceLine({
            price: Number(trade.stop_loss),
            color: "#ef4444",
            lineWidth: 2,
            axisLabelVisible: true,
            title: "SL",
            lineStyle: LightweightCharts.LineStyle.Dashed,
        });
    }

    if (trade.take_profit) {
        candleSeries.createPriceLine({
            price: Number(trade.take_profit),
            color: "#22c55e",
            lineWidth: 2,
            axisLabelVisible: true,
            title: "TP",
            lineStyle: LightweightCharts.LineStyle.Dashed,
        });
    }
}

function startReplay() {
    if (!replayData || !replayData.candles || !candleSeries) {
        console.error("Replay non prêt");
        return;
    }

    clearInterval(interval);

    interval = setInterval(() => {
        if (index >= replayData.candles.length) {
            clearInterval(interval);
            return;
        }

        checkDecisionPoint(index);

        const c = replayData.candles[index];

        candleSeries.update({
            time: normalizeTime(c.time),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
        });

        highlightEvents(index);

        if (chart) {
            chart.timeScale().scrollToRealTime();
        }

        index++;
    }, speed);
}

function pauseReplay() {
    clearInterval(interval);
}

function resetReplay() {
    clearInterval(interval);
    index = 0;
    decisionShown = false;
    traderScore = 0;

    if (candleSeries) {
        candleSeries.setData([]);
    }

    eventElements.forEach((el) => el.classList.remove("active"));

    const decisionBox = document.getElementById("decision-box");
    if (decisionBox) {
        decisionBox.classList.add("hidden");
    }

    updateScoreUI(
        0,
        "En attente de décision",
        "Le score apparaîtra après ton choix.",
        ""
    );

    setTimeout(() => {
        startReplay();
    }, 150);
}

function setSpeed(multiplier) {
    speed = 700 / multiplier;

    if (interval) {
        startReplay();
    }
}

function renderEvents() {
    const container = document.getElementById("events");
    if (!container || !replayData || !replayData.events) return;

    container.innerHTML = "";
    eventElements = [];

    replayData.events.forEach((e) => {
        const div = document.createElement("div");
        div.className = "replay-event";
        div.dataset.index = e.index;

        div.innerHTML = `
            <strong>${e.title}</strong>
            <span>${e.description || ""}</span>
        `;

        container.appendChild(div);
        eventElements.push(div);
    });
}

function highlightEvents(currentIndex) {
    eventElements.forEach((el) => {
        const idx = parseInt(el.dataset.index, 10);

        if (idx === currentIndex) {
            el.classList.add("active");
            el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } else {
            el.classList.remove("active");
        }
    });
}

function checkDecisionPoint(currentIndex) {
    if (decisionShown) return;

    if (currentIndex === 20) {
        decisionShown = true;
        pauseReplay();

        const decisionBox = document.getElementById("decision-box");
        if (decisionBox) {
            decisionBox.classList.remove("hidden");
        }
    }
}

async function saveDecisionToServer(decision, score, status, feedback) {
    try {
        const res = await fetch(`/api/replay/${replayId}/decision`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                decision: decision,
                score: score,
                status: status,
                feedback: feedback
            })
        });

        const data = await res.json();
        console.log("Sauvegarde décision :", data);
    } catch (error) {
        console.error("Erreur sauvegarde décision :", error);
    }
}

function makeDecision(choice) {
    const decisionBox = document.getElementById("decision-box");
    if (decisionBox) {
        decisionBox.classList.add("hidden");
    }

    let score = 0;
    let status = "";
    let feedback = "";
    let statusText = "";

    if (choice === "hold") {
        score = 10;
        status = "good";
        statusText = "Discipline excellente";
        feedback = "✅ Bonne décision. Il fallait conserver la position et respecter le plan.";
    } else if (choice === "partial") {
        score = 5;
        status = "medium";
        statusText = "Gestion prudente";
        feedback = "⚠️ Décision correcte mais incomplète. Tu sécurises, mais tu réduis le potentiel du trade.";
    } else if (choice === "close") {
        score = 0;
        status = "bad";
        statusText = "Sortie émotionnelle";
        feedback = "❌ Mauvaise décision. Tu coupes trop tôt par manque de discipline.";
    }

    traderScore = score;
    updateScoreUI(score, statusText, feedback, status);
    saveDecisionToServer(choice, score, status, feedback);

    startReplay();
}

function updateScoreUI(score, statusText, messageText, level) {
    const scoreEl = document.getElementById("trader-score");
    const statusEl = document.getElementById("trader-status");
    const feedbackEl = document.getElementById("decision-feedback");

    if (scoreEl) {
        scoreEl.textContent = String(score);
    }

    if (feedbackEl) {
        feedbackEl.textContent = messageText;
    }

    if (statusEl) {
        statusEl.textContent = statusText;
        statusEl.className = "score-status";

        if (level === "good") {
            statusEl.classList.add("good");
        } else if (level === "medium") {
            statusEl.classList.add("medium");
        } else if (level === "bad") {
            statusEl.classList.add("bad");
        }
    }
}

loadReplay();