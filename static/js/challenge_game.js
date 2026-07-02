(function () {
  "use strict";

  var CFG = window.CHALLENGE || {};
  var i18n = CFG.i18n || {};
  function t(k, f) { return i18n[k] || f; }

  var el = function (id) { return document.getElementById(id); };
  var chart = null, series = null, data = null, revealTimer = null;

  function fmtPct(v) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return (v >= 0 ? "+" : "") + Number(v).toFixed(2) + "%";
  }

  function setStatus(txt) { var s = el("cg-phase"); if (s) s.textContent = txt; }

  function drawPriceLines() {
    if (!series) return;
    var LW = window.LightweightCharts;
    var dashed = LW && LW.LineStyle ? LW.LineStyle.Dashed : 2;
    series.createPriceLine({ price: data.entry_price, color: "#93c5fd", lineWidth: 1, lineStyle: dashed, axisLabelVisible: true, title: t("entry", "Entrée") });
    if (data.stop_loss) series.createPriceLine({ price: data.stop_loss, color: "#ef4444", lineWidth: 1, lineStyle: dashed, axisLabelVisible: true, title: "SL" });
    if (data.take_profit) series.createPriceLine({ price: data.take_profit, color: "#22c55e", lineWidth: 1, lineStyle: dashed, axisLabelVisible: true, title: "TP" });
  }

  function buildChart() {
    var LW = window.LightweightCharts;
    if (!LW) { el("cg-chart").innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center;">Chart library unavailable.</p>'; return false; }
    chart = LW.createChart(el("cg-chart"), {
      layout: { background: { color: "transparent" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "rgba(148,163,184,0.06)" }, horzLines: { color: "rgba(148,163,184,0.06)" } },
      rightPriceScale: { borderColor: "rgba(148,163,184,0.15)" },
      timeScale: { borderColor: "rgba(148,163,184,0.15)", timeVisible: true, barSpacing: 8, minBarSpacing: 4, rightOffset: 3 },
      crosshair: { mode: 0 },
      handleScroll: false, handleScale: false,
    });
    var candleOpts = {
      upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    };
    try {
      if (typeof chart.addCandlestickSeries === "function") {
        series = chart.addCandlestickSeries(candleOpts);          // lightweight-charts v3/v4
      } else if (LW.CandlestickSeries && typeof chart.addSeries === "function") {
        series = chart.addSeries(LW.CandlestickSeries, candleOpts); // v5+
      } else {
        throw new Error("CandlestickSeries unavailable");
      }
    } catch (e) {
      setStatus(t("error", "Données indisponibles"));
      return false;
    }
    window.addEventListener("resize", function () {
      if (chart) chart.applyOptions({ width: el("cg-chart").clientWidth, height: el("cg-chart").clientHeight });
    });
    return true;
  }

  function revealUpTo(idx) {
    var slice = data.candles.slice(0, Math.min(idx + 1, data.candles.length));
    series.setData(slice);
  }

  function start() {
    var n = data.candles.length;
    var di = data.decision_index;
    // Client-side pause point is for UX only (scoring is 100% server-side),
    // so pick a point that always leaves a readable amount of context.
    if (typeof di !== "number" || di < 8 || di > n - 2) {
      di = Math.floor(n * 0.62);
    }
    data._decisionIdx = Math.max(3, Math.min(di, n - 2));
    revealUpTo(data._decisionIdx);
    var shown = data._decisionIdx + 1;
    if (shown >= 25) {
      chart.timeScale().fitContent();
    } else {
      chart.timeScale().applyOptions({ barSpacing: 12 });
      try { chart.timeScale().scrollToPosition(3, false); } catch (e) {}
    }
    drawPriceLines();
    el("cg-asset").textContent = data.asset || "—";
    var dir = el("cg-dir");
    dir.textContent = data.direction || "—";
    dir.className = "cg-dir " + (data.direction === "SELL" ? "sell" : "buy");
    setStatus(t("decision_moment", "Moment de décision"));
    el("cg-decision").style.display = "flex";
  }

  function decide(choice) {
    el("cg-decision").style.display = "none";
    setStatus(t("revealing", "Révélation…"));
    fetch(CFG.apiBase + "/decision", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: choice }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) { animateReveal(choice, res); })
      .catch(function () { setStatus(t("error", "Erreur")); });
  }

  function animateReveal(choice, res) {
    var end = (typeof res.exit_index === "number" && res.exit_index > data._decisionIdx)
      ? res.exit_index : data.candles.length - 1;
    end = Math.min(end, data.candles.length - 1);
    var i = data._decisionIdx;
    clearInterval(revealTimer);
    revealTimer = setInterval(function () {
      i++;
      revealUpTo(i);
      try { chart.timeScale().fitContent(); } catch (e) {}
      if (i >= end) { clearInterval(revealTimer); showResult(choice, res); }
    }, 110);
  }

  function showResult(choice, res) {
    setStatus(t("result", "Résultat"));
    var win = (res.status === "good");
    var box = el("cg-result");
    var choiceLabel = { close: t("d_close", "Fermer"), hold: t("d_hold", "Conserver"), partial: t("d_partial", "Alléger") };
    var idealLabel = choiceLabel[res.ideal_decision] || res.ideal_decision;
    el("cg-score-val").textContent = res.score;
    el("cg-score-ring").style.background =
      "conic-gradient(" + (win ? "#22c55e" : res.status === "medium" ? "#f59e0b" : "#ef4444") +
      " " + (res.score * 3.6) + "deg, rgba(148,163,184,.15) 0deg)";
    el("cg-verdict").textContent = win ? t("verdict_good", "Bien joué !") : res.status === "medium" ? t("verdict_medium", "Pas mal") : t("verdict_bad", "Raté");
    el("cg-verdict").className = "cg-verdict " + res.status;
    el("cg-detail").innerHTML =
      t("your_choice", "Ton choix") + " : <strong>" + (choiceLabel[choice] || choice) + "</strong> · " +
      t("ideal_choice", "Idéal") + " : <strong>" + idealLabel + "</strong><br>" +
      t("trade_result", "Résultat du trade") + " : <strong style=\"color:" + ((res.result_percent || 0) >= 0 ? "#4ade80" : "#f87171") + "\">" + fmtPct(res.result_percent) + "</strong>";
    box.style.display = "block";
    window._cgFinalScore = res.score;
  }

  function submitScore() {
    var pseudo = (el("cg-pseudo").value || "").trim();
    if (pseudo.length < 2) { el("cg-pseudo").focus(); return; }
    fetch(CFG.leaderboardBase, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pseudo: pseudo, score: window._cgFinalScore || 0, rounds: 1 }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res && res.leaderboard) renderLeaderboard(res.leaderboard);
        el("cg-submit-row").innerHTML = "<span style=\"color:#4ade80;font-weight:700;\">✓ " + t("score_saved", "Score enregistré !") + "</span>";
      })
      .catch(function () {});
  }

  function renderLeaderboard(list) {
    var wrap = el("cg-leaderboard");
    if (!wrap || !list) return;
    wrap.innerHTML = list.map(function (s, i) {
      return '<div class="cg-lb-row"><span class="cg-lb-rank">' + (i + 1) + '</span><span class="cg-lb-name">' +
        escapeHtml(s.pseudo) + '</span><span class="cg-lb-score">' + s.score + '</span></div>';
    }).join("");
  }

  function escapeHtml(x) { var d = document.createElement("div"); d.textContent = x; return d.innerHTML; }

  function share() {
    var score = window._cgFinalScore || 0;
    var text = t("share_text", "J'ai scoré {s}/100 au Défi Trading VelWolef. Tu fais mieux ?").replace("{s}", score);
    var url = window.location.origin + "/defi";
    if (navigator.share) { navigator.share({ title: "Défi VelWolef", text: text, url: url }).catch(function () {}); }
    else {
      var tw = "https://twitter.com/intent/tweet?text=" + encodeURIComponent(text + " " + url);
      window.open(tw, "_blank");
    }
  }

  function init() {
    if (!buildChart()) return;
    fetch(CFG.apiBase, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("no data"); return r.json(); })
      .then(function (d) { data = d; if (!d.candles || !d.candles.length) throw new Error("empty"); start(); })
      .catch(function () { setStatus(t("error", "Données indisponibles")); });

    document.querySelectorAll("[data-choice]").forEach(function (b) {
      b.addEventListener("click", function () { decide(b.getAttribute("data-choice")); });
    });
    var sb = el("cg-submit-btn"); if (sb) sb.addEventListener("click", submitScore);
    var shb = el("cg-share-btn"); if (shb) shb.addEventListener("click", share);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
