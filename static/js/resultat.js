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
    const chartWrap = svg ? svg.closest(".rs-equity-chart") : null;

    if (svg && chartWrap && window.RESULTS_EQUITY_POINTS && window.RESULTS_EQUITY_POINTS.length) {
        const points = window.RESULTS_EQUITY_POINTS;

        const width = 1000, height = 280, padX = 24, padY = 22;
        const min = Math.min(...points);
        const max = Math.max(...points);
        const range = (max - min) || 1;
        const xStep = points.length > 1 ? (width - padX * 2) / (points.length - 1) : 0;

        const mapX = (i) => padX + i * xStep;
        const mapY = (v) => height - padY - ((v - min) / range) * (height - padY * 2);

        let lineD = "";
        points.forEach((value, i) => {
            const x = mapX(i), y = mapY(value);
            lineD += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
        });

        const firstX = mapX(0), lastX = mapX(points.length - 1);
        const areaD = `${lineD} L ${lastX} ${height - padY} L ${firstX} ${height - padY} Z`;
        const zeroY = mapY(0);
        const lastVal = points[points.length - 1];
        const endColor = lastVal >= 0 ? "#22c55e" : "#ef4444";

        const defs = `
            <defs>
                <linearGradient id="eqLine" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="#3b82f6"/>
                    <stop offset="100%" stop-color="${lastVal >= 0 ? '#22c55e' : '#ef4444'}"/>
                </linearGradient>
                <linearGradient id="eqArea" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="rgba(59,130,246,0.32)"/>
                    <stop offset="100%" stop-color="rgba(34,197,94,0.01)"/>
                </linearGradient>
                <filter id="eqGlow"><feGaussianBlur stdDeviation="6" result="b"/>
                    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            </defs>`;

        const grid = `
            <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
            <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
            <line x1="${padX}" y1="${zeroY}" x2="${width - padX}" y2="${zeroY}" stroke="rgba(255,255,255,0.10)" stroke-dasharray="5 5" stroke-width="1"/>`;

        const area = `<path d="${areaD}" fill="url(#eqArea)" opacity="0.9"></path>`;
        const line = `<path d="${lineD}" fill="none" stroke="url(#eqLine)" stroke-width="4" filter="url(#eqGlow)" stroke-linecap="round" stroke-linejoin="round"></path>`;
        const endDot = `<circle cx="${lastX}" cy="${mapY(lastVal)}" r="5" fill="#fff" stroke="${endColor}" stroke-width="3"></circle>`;

        svg.innerHTML = defs + grid + area + line + endDot;

        /* ---- interactive HTML overlay (crisp despite SVG stretch) ---- */
        chartWrap.style.position = "relative";
        const mk = (cls) => {
            let el = chartWrap.querySelector("." + cls.split(" ").join("."));
            if (!el) { el = document.createElement("div"); el.className = cls; chartWrap.appendChild(el); }
            return el;
        };
        const tip = mk("rs-eq-tip");
        const cross = mk("rs-eq-cross");
        const hoverDot = mk("rs-eq-hoverdot");

        const pxX = (idx) => { const W = chartWrap.clientWidth, px = (padX / width) * W;
            return px + idx * ((W - 2 * px) / Math.max(points.length - 1, 1)); };
        const pxY = (v) => { const H = chartWrap.clientHeight, py = (padY / height) * H;
            return H - py - ((v - min) / range) * (H - 2 * py); };

        const hiIdx = points.indexOf(max), loIdx = points.indexOf(min);
        function badge(cls, idx, val, color) {
            const b = mk("rs-eq-badge " + cls);
            b.style.left = pxX(idx) + "px";
            b.style.top = pxY(val) + "px";
            b.style.setProperty("--c", color);
            b.textContent = (val >= 0 ? "+" : "") + val + "%";
        }
        function refreshBadges() {
            if (points.length > 1 && max !== min) {
                badge("rs-eq-hi", hiIdx, max, "#22c55e");
                badge("rs-eq-lo", loIdx, min, "#ef4444");
            }
        }
        refreshBadges();
        window.addEventListener("resize", refreshBadges);

        function onMove(e) {
            const rect = chartWrap.getBoundingClientRect();
            const W = rect.width, px = (padX / width) * W, inner = W - 2 * px;
            let frac = inner > 0 ? (e.clientX - rect.left - px) / inner : 0;
            frac = Math.max(0, Math.min(1, frac));
            const idx = Math.round(frac * (points.length - 1));
            const val = points[idx], x = pxX(idx), y = pxY(val);
            const c = val >= 0 ? "#22c55e" : "#ef4444";
            cross.style.display = "block"; cross.style.left = x + "px";
            hoverDot.style.display = "block"; hoverDot.style.left = x + "px"; hoverDot.style.top = y + "px";
            hoverDot.style.setProperty("--c", c);
            tip.style.display = "block";
            tip.innerHTML = `<span class="rs-eq-tip-idx">Trade #${idx + 1}</span>` +
                `<span class="rs-eq-tip-val" style="color:${val >= 0 ? '#4ade80' : '#f87171'}">${val >= 0 ? '+' : ''}${val}%</span>`;
            let tipX = x + 14; if (tipX + 130 > W) tipX = x - 130;
            tip.style.left = Math.max(4, tipX) + "px";
            tip.style.top = Math.max(4, y - 46) + "px";
        }
        function onLeave() { tip.style.display = "none"; cross.style.display = "none"; hoverDot.style.display = "none"; }
        chartWrap.addEventListener("mousemove", onMove);
        chartWrap.addEventListener("mouseleave", onLeave);
        chartWrap.addEventListener("touchmove", (ev) => { if (ev.touches[0]) onMove(ev.touches[0]); }, { passive: true });
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