/* =========================================================
   RESULTS PAGE JS
   Filters dropdown + equity chart + learn toggle
   File: static/js/results.js
========================================================= */

function toggleLearn(btn) {
    const box = btn.nextElementSibling;
    if (!box) return;
    box.style.display = box.style.display === "block" ? "none" : "block";
}

document.addEventListener("DOMContentLoaded", function () {
    /* =============================
       EQUITY CHART
    ============================= */
    const svg = document.getElementById("equityChart");

    if (svg && window.RESULTS_EQUITY_POINTS && window.RESULTS_EQUITY_POINTS.length) {
        const points = window.RESULTS_EQUITY_POINTS;

        const width = 1000;
        const height = 280;
        const padX = 24;
        const padY = 22;

        const min = Math.min(...points);
        const max = Math.max(...points);
        const range = max - min || 1;

        const xStep = points.length > 1 ? (width - padX * 2) / (points.length - 1) : 0;

        const mapX = (i) => padX + i * xStep;
        const mapY = (v) => height - padY - ((v - min) / range) * (height - padY * 2);

        let lineD = "";

        points.forEach(function (value, i) {
            const x = mapX(i);
            const y = mapY(value);
            lineD += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
        });

        const firstX = mapX(0);
        const lastX = mapX(points.length - 1);
        const areaD = `${lineD} L ${lastX} ${height - padY} L ${firstX} ${height - padY} Z`;
        const zeroY = mapY(0);

        const defs = `
            <defs>
                <linearGradient id="eqLine" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="#3b82f6"/>
                    <stop offset="100%" stop-color="#22c55e"/>
                </linearGradient>
                <linearGradient id="eqArea" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="rgba(59,130,246,0.35)"/>
                    <stop offset="100%" stop-color="rgba(34,197,94,0.02)"/>
                </linearGradient>
                <filter id="eqGlow">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feMerge>
                        <feMergeNode in="blur"/>
                        <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                </filter>
            </defs>
        `;

        const grid = `
            <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
            <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
            <line x1="${padX}" y1="${zeroY}" x2="${width - padX}" y2="${zeroY}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="5 5" stroke-width="1"/>
        `;

        const area = `<path d="${areaD}" fill="url(#eqArea)" opacity="0.9"></path>`;
        const line = `<path d="${lineD}" fill="none" stroke="url(#eqLine)" stroke-width="4" filter="url(#eqGlow)" stroke-linecap="round" stroke-linejoin="round"></path>`;

        const dots = points.map(function (value, i) {
            const x = mapX(i);
            const y = mapY(value);
            return `<circle cx="${x}" cy="${y}" r="4" fill="#ffffff" stroke="#22c55e" stroke-width="2"></circle>`;
        }).join("");

        svg.innerHTML = defs + grid + area + line + dots;
    }

    /* =============================
       DROPDOWN FILTERS
    ============================= */
    const assetsByType = {
        ALL: ["ALL", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "EURUSD", "GBPUSD", "USDJPY", "US100", "US500", "GER40", "FRA40"],
        CRYPTO: ["ALL", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"],
        FOREX: ["ALL", "EURUSD", "GBPUSD", "USDJPY"],
        INDICES: ["ALL", "US100", "US500", "GER40", "FRA40"]
    };

    const assetToType = {
        BTCUSD: "CRYPTO",
        ETHUSD: "CRYPTO",
        SOLUSD: "CRYPTO",
        XRPUSD: "CRYPTO",
        EURUSD: "FOREX",
        GBPUSD: "FOREX",
        USDJPY: "FOREX",
        US100: "INDICES",
        US500: "INDICES",
        GER40: "INDICES",
        FRA40: "INDICES",
        ALL: "ALL"
    };

    const marketSelect = document.getElementById("market-type");
    const assetSelect = document.getElementById("asset-list");
    const timeframeSelect = document.getElementById("timeframe");

    if (!marketSelect || !assetSelect || !timeframeSelect) return;

    let selectedAsset = window.RESULTS_SELECTED_ASSET || "ALL";
    let selectedTime = window.RESULTS_SELECTED_TIME || "all";
    let selectedType = assetToType[selectedAsset] || "ALL";

    function renderAssets(type) {
        assetSelect.innerHTML = "";

        const list = assetsByType[type] || assetsByType.ALL;

        list.forEach(function (asset) {
            const option = document.createElement("option");
            option.value = asset;
            option.textContent = asset;

            if (asset === selectedAsset) {
                option.selected = true;
            }

            assetSelect.appendChild(option);
        });
    }

    function updateURL() {
        const url = new URL(window.location.href);
        url.searchParams.set("asset", selectedAsset);
        url.searchParams.set("time", selectedTime);
        window.location.href = url.toString();
    }

    marketSelect.value = selectedType;
    timeframeSelect.value = selectedTime;
    renderAssets(selectedType);

    marketSelect.addEventListener("change", function () {
        selectedType = this.value;
        selectedAsset = "ALL";
        marketSelect.value = selectedType;
        renderAssets(selectedType);
        updateURL();
    });

    assetSelect.addEventListener("change", function () {
        selectedAsset = this.value;
        updateURL();
    });

    timeframeSelect.addEventListener("change", function () {
        selectedTime = this.value;
        updateURL();
    });
});