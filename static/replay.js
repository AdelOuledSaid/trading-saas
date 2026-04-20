let chart;
let candleSeries;
let candles = [];
let events = [];

let currentIndex = 0;
let interval = null;
let speed = 800;

let decisionIndex = null;
let decisionMade = false;

// =========================
// INIT
// =========================
async function initReplay() {
    const res = await fetch(replayApiBase);
    const data = await res.json();

    candles = data.candles;
    events = data.events;

    decisionIndex = data.trade.decision_index;

    initChart();
    renderEvents(events);
    renderLessons(data.trade.lessons);

    updateMeta(0);
}

// =========================
// CHART
// =========================
function initChart() {
    chart = LightweightCharts.createChart(document.getElementById('chart'), {
        layout: {
            background: { color: '#0b0f1a' },
            textColor: '#d1d5db'
        },
        grid: {
            vertLines: { color: '#1f2937' },
            horzLines: { color: '#1f2937' }
        },
        width: document.getElementById('chart').clientWidth,
        height: 400
    });

    candleSeries = chart.addCandlestickSeries();

    window.addEventListener('resize', () => {
        chart.resize(document.getElementById('chart').clientWidth, 400);
    });
}

// =========================
// REPLAY CONTROL
// =========================
function startReplay() {
    if (interval) return;

    interval = setInterval(() => {
        if (currentIndex >= candles.length) {
            pauseReplay();
            return;
        }

        const c = candles[currentIndex];

        candleSeries.update({
            time: new Date(c.time).getTime() / 1000,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close
        });

        updateMeta(currentIndex);
        checkDecisionMoment(currentIndex);

        currentIndex++;
    }, speed);
}

function pauseReplay() {
    clearInterval(interval);
    interval = null;
}

function resetReplay() {
    pauseReplay();
    currentIndex = 0;
    decisionMade = false;

    document.getElementById("decision-box").classList.add("hidden");

    chart.remove();
    initChart();
    updateMeta(0);
}

function setSpeed(multiplier) {
    speed = 800 / multiplier;
    if (interval) {
        pauseReplay();
        startReplay();
    }
}

// =========================
// META UI
// =========================
function updateMeta(index) {
    const progress = Math.round((index / candles.length) * 100);

    document.getElementById("progress-text").innerText = progress + "%";
    document.getElementById("candle-counter").innerText = `${index} / ${candles.length}`;

    document.getElementById("progress-bar").style.width = progress + "%";
}

// =========================
// DECISION SYSTEM
// =========================
function checkDecisionMoment(index) {
    if (!decisionMade && index >= decisionIndex) {
        pauseReplay();
        showDecisionBox();
    }
}

function showDecisionBox() {
    document.getElementById("decision-box").classList.remove("hidden");
}

async function makeDecision(choice) {
    decisionMade = true;

    const res = await fetch(`${replayApiBase}/decision`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ decision: choice })
    });

    const data = await res.json();

    displayScore(data);
    document.getElementById("decision-box").classList.add("hidden");

    startReplay();
}

// =========================
// SCORE DISPLAY
// =========================
function displayScore(data) {
    document.getElementById("trader-score").innerText = data.score;

    const statusEl = document.getElementById("trader-status");
    statusEl.innerText = data.status_text;

    const feedbackEl = document.getElementById("decision-feedback");
    feedbackEl.innerText = data.feedback;

    if (data.status === "good") {
        statusEl.style.color = "#22c55e";
    } else if (data.status === "medium") {
        statusEl.style.color = "#f59e0b";
    } else {
        statusEl.style.color = "#ef4444";
    }

    // mini scores (simple simulation)
    document.getElementById("discipline-score").innerText = `${data.score}/10`;
    document.getElementById("timing-score").innerText = `${Math.max(0, data.score - 2)}/10`;
}

// =========================
// EVENTS TIMELINE
// =========================
function renderEvents(events) {
    const container = document.getElementById("events");
    container.innerHTML = "";

    events.forEach(e => {
        const div = document.createElement("div");
        div.className = "event";

        div.innerHTML = `
            <strong>${e.title}</strong>
            <p>${e.description || ""}</p>
        `;

        container.appendChild(div);
    });
}

// =========================
// LESSONS
// =========================
function renderLessons(lessons) {
    const container = document.getElementById("lessons-list");
    container.innerHTML = "";

    lessons.forEach(l => {
        const div = document.createElement("div");
        div.className = "lesson-item";
        div.innerText = l;
        container.appendChild(div);
    });
}

// =========================
// START
// =========================
window.onload = initReplay;