(function () {
  "use strict";

  var LS_CAPITAL = "vw_calc_capital";
  var LS_RISK = "vw_calc_risk";

  function t(key, fallback) {
    var dict = window.VW_CALC_I18N || {};
    return dict[key] || fallback;
  }

  function fmt(n, digits) {
    if (!isFinite(n)) return "—";
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    }).format(n);
  }

  function money(n) {
    if (!isFinite(n)) return "—";
    return "$" + fmt(n, 2);
  }

  var modal = null;

  function buildModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.className = "vwpc-overlay";
    modal.innerHTML =
      '<div class="vwpc-modal" role="dialog" aria-modal="true" aria-label="' +
      t("calc_title", "Calculateur de position") + '">' +
        '<div class="vwpc-head">' +
          '<h3>' + t("calc_title", "Calculateur de position") + '</h3>' +
          '<button type="button" class="vwpc-close" aria-label="' + t("close", "Fermer") + '">&times;</button>' +
        '</div>' +
        '<div class="vwpc-signal">' +
          '<span class="vwpc-asset" id="vwpc-asset">—</span>' +
          '<span class="vwpc-dir" id="vwpc-dir">—</span>' +
          '<div class="vwpc-levels">' +
            '<div><span>' + t("entry", "Entrée") + '</span><strong id="vwpc-entry">—</strong></div>' +
            '<div><span>SL</span><strong id="vwpc-sl">—</strong></div>' +
            '<div><span>TP</span><strong id="vwpc-tp">—</strong></div>' +
          '</div>' +
        '</div>' +
        '<div class="vwpc-inputs">' +
          '<label>' + t("calc_capital", "Votre capital") +
            '<div class="vwpc-field"><span>$</span><input type="number" id="vwpc-capital" min="1" step="1" value="1000"></div>' +
          '</label>' +
          '<label>' + t("calc_risk", "Risque par trade") +
            '<div class="vwpc-field"><input type="number" id="vwpc-risk" min="0.1" max="100" step="0.1" value="2"><span>%</span></div>' +
          '</label>' +
        '</div>' +
        '<div class="vwpc-error" id="vwpc-error"></div>' +
        '<div class="vwpc-results" id="vwpc-results">' +
          '<div class="vwpc-res"><span>' + t("calc_position_size", "Taille de position") + '</span><strong id="vwpc-size">—</strong></div>' +
          '<div class="vwpc-res"><span>' + t("calc_position_value", "Valeur de position") + '</span><strong id="vwpc-value">—</strong></div>' +
          '<div class="vwpc-res vwpc-loss"><span>' + t("calc_potential_loss", "Perte potentielle") + '</span><strong id="vwpc-loss">—</strong></div>' +
          '<div class="vwpc-res vwpc-gain"><span>' + t("calc_potential_gain", "Gain potentiel") + '</span><strong id="vwpc-gain">—</strong></div>' +
          '<div class="vwpc-res vwpc-rr"><span>' + t("calc_rr", "Ratio risque / rendement") + '</span><strong id="vwpc-rr">—</strong></div>' +
        '</div>' +
        '<p class="vwpc-note">' + t("calc_note", "Estimation à titre indicatif. Ne constitue pas un conseil en investissement.") + '</p>' +
      '</div>';
    document.body.appendChild(modal);

    modal.addEventListener("click", function (e) {
      if (e.target === modal || e.target.classList.contains("vwpc-close")) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    modal.querySelector("#vwpc-capital").addEventListener("input", recompute);
    modal.querySelector("#vwpc-risk").addEventListener("input", recompute);
    return modal;
  }

  var current = {};

  function open(data) {
    buildModal();
    current = data;
    modal.querySelector("#vwpc-asset").textContent = data.asset || "—";
    var dir = (data.dir || "").toUpperCase();
    var dirEl = modal.querySelector("#vwpc-dir");
    dirEl.textContent = dir || "—";
    dirEl.className = "vwpc-dir " + (dir === "SELL" ? "sell" : "buy");
    modal.querySelector("#vwpc-entry").textContent = isFinite(data.entry) ? fmt(data.entry, guessDigits(data.entry)) : "—";
    modal.querySelector("#vwpc-sl").textContent = isFinite(data.sl) ? fmt(data.sl, guessDigits(data.sl)) : "—";
    modal.querySelector("#vwpc-tp").textContent = isFinite(data.tp) ? fmt(data.tp, guessDigits(data.tp)) : "—";

    var cap = parseFloat(localStorage.getItem(LS_CAPITAL));
    var risk = parseFloat(localStorage.getItem(LS_RISK));
    if (isFinite(cap) && cap > 0) modal.querySelector("#vwpc-capital").value = cap;
    if (isFinite(risk) && risk > 0) modal.querySelector("#vwpc-risk").value = risk;

    modal.classList.add("open");
    document.body.style.overflow = "hidden";
    recompute();
  }

  function close() {
    if (modal) {
      modal.classList.remove("open");
      document.body.style.overflow = "";
    }
  }

  function guessDigits(v) {
    v = Math.abs(v);
    if (v >= 100) return 2;
    if (v >= 1) return 2;
    return 5;
  }

  function recompute() {
    var capital = parseFloat(modal.querySelector("#vwpc-capital").value);
    var risk = parseFloat(modal.querySelector("#vwpc-risk").value);
    var entry = current.entry, sl = current.sl, tp = current.tp;
    var err = modal.querySelector("#vwpc-error");
    var results = modal.querySelector("#vwpc-results");

    try {
      localStorage.setItem(LS_CAPITAL, capital);
      localStorage.setItem(LS_RISK, risk);
    } catch (e) {}

    function bad(msg) {
      err.textContent = msg;
      err.style.display = "block";
      results.style.opacity = "0.35";
    }
    err.style.display = "none";
    results.style.opacity = "1";

    if (!isFinite(capital) || capital <= 0) return bad(t("calc_err_capital", "Entrez un capital valide."));
    if (!isFinite(risk) || risk <= 0) return bad(t("calc_err_risk", "Entrez un risque valide."));
    if (!isFinite(entry) || !isFinite(sl) || !isFinite(tp))
      return bad(t("calc_err_levels", "Ce signal n'a pas d'entrée / SL / TP complets."));

    var stopDist = Math.abs(entry - sl);
    if (stopDist <= 0) return bad(t("calc_err_sl", "Le stop-loss doit différer de l'entrée."));

    var riskAmount = capital * risk / 100;
    var size = riskAmount / stopDist;
    var positionValue = size * entry;
    var rewardDist = Math.abs(tp - entry);
    var potentialGain = size * rewardDist;
    var rr = rewardDist / stopDist;

    modal.querySelector("#vwpc-size").textContent = fmt(size, size < 1 ? 4 : 3) + " " + t("units", "unités");
    modal.querySelector("#vwpc-value").textContent = money(positionValue);
    modal.querySelector("#vwpc-loss").textContent = "-" + money(riskAmount);
    modal.querySelector("#vwpc-gain").textContent = "+" + money(potentialGain);
    modal.querySelector("#vwpc-rr").textContent = "1 : " + fmt(rr, 2);
  }

  function attach() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".js-position-calc");
      if (!btn) return;
      e.preventDefault();
      open({
        asset: btn.getAttribute("data-asset"),
        dir: btn.getAttribute("data-dir"),
        entry: parseFloat(btn.getAttribute("data-entry")),
        sl: parseFloat(btn.getAttribute("data-sl")),
        tp: parseFloat(btn.getAttribute("data-tp")),
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    attach();
  }
})();
