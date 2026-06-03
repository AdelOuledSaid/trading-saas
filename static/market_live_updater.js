/**
 * market_live_updater.js
 * Rafraichit les prix BTC, ETH, Fear & Greed sur la homepage toutes les 60s.
 * A inclure dans home.html via <script src="{{ url_for('static', filename='market_live_updater.js') }}"></script>
 */

(function () {
  const REFRESH_MS = 60_000;

  function fmt_price(price, symbol) {
    if (price === null || price === undefined) return "--";
    if (["BTC", "ETH"].includes(symbol)) {
      return "$" + Number(price).toLocaleString("en-US", { maximumFractionDigits: 0 });
    }
    return "$" + Number(price).toLocaleString("en-US", { maximumFractionDigits: 2 });
  }

  function fmt_change(change) {
    if (change === null || change === undefined) return "";
    const sign = change >= 0 ? "+" : "";
    return sign + Number(change).toFixed(2) + "%";
  }

  function set_change_class(el, change) {
    if (!el) return;
    el.classList.remove("up", "down");
    if (change > 0) el.classList.add("up");
    else if (change < 0) el.classList.add("down");
  }

  function update_asset_card(symbol, price, change) {
    // Trouve la carte asset par le symbol dans .asset-mini-card
    document.querySelectorAll(".asset-mini-card").forEach(function (card) {
      const sym_el = card.querySelector(".symbol");
      if (!sym_el || sym_el.textContent.trim() !== symbol) return;

      const price_el = card.querySelector(".price");
      const change_el = card.querySelector(".change");

      if (price_el) price_el.textContent = fmt_price(price, symbol);
      if (change_el) {
        change_el.textContent = fmt_change(change);
        set_change_class(change_el, change);
      }
    });
  }

  function update_fear_greed(value, label) {
    // Badge Fear & Greed dans .hub-badge
    document.querySelectorAll(".hub-badge").forEach(function (badge) {
      const span = badge.querySelector("span");
      if (!span) return;
      const txt = span.textContent.trim().toLowerCase();
      if (txt.includes("fear") || txt.includes("greed") || txt.includes("greed") || txt.includes("greed")) {
        const strong = badge.querySelector("strong");
        const small = badge.querySelector("small");
        if (strong && value !== null) strong.textContent = value;
        if (small && label) small.textContent = label;
      }
    });
  }

  function update_btc_dominance_badge(dom_value) {
    document.querySelectorAll(".hub-badge").forEach(function (badge) {
      const span = badge.querySelector("span");
      if (!span) return;
      const txt = span.textContent.trim().toLowerCase();
      if (txt.includes("dominance") || txt.includes("domina")) {
        const strong = badge.querySelector("strong");
        if (strong && dom_value !== null && dom_value !== undefined) {
          strong.textContent = Number(dom_value).toFixed(1) + "%";
        }
      }
    });
  }

  function fetch_and_update() {
    // Mise a jour ticker (BTC, ETH, BTC.D, F&G)
    fetch("/api/market-live")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;

        var btc = data.btc || {};
        var eth = data.eth || {};
        var fg = data.fear_greed || {};

        update_asset_card("BTC", btc.price, btc.change);
        update_asset_card("ETH", eth.price, eth.change);
        update_fear_greed(fg.value, fg.label);
      })
      .catch(function () { /* silencieux — pas de console.error visible */ });

    // Mise a jour ticker barre en haut
    fetch("/api/market-ticker")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.items) return;
        data.items.forEach(function (item) {
          update_ticker_item(item.symbol, item.price, item.change);
        });
      })
      .catch(function () {});
  }

  function update_ticker_item(symbol, price, change) {
    // Mise a jour du ticker en haut (#tickerTrack)
    var track = document.getElementById("tickerTrack");
    if (!track) return;

    var items = track.querySelectorAll(".ticker-item");
    items.forEach(function (item) {
      var sym_el = item.querySelector(".ticker-symbol");
      if (!sym_el || sym_el.textContent.trim() !== symbol) return;

      var price_el = item.querySelector(".ticker-price");
      var change_el = item.querySelector(".ticker-change");

      if (price_el) price_el.textContent = fmt_price(price, symbol);
      if (change_el) {
        change_el.textContent = fmt_change(change);
        set_change_class(change_el, change);
      }
    });
  }

  // Lancement
  document.addEventListener("DOMContentLoaded", function () {
    fetch_and_update();
    setInterval(fetch_and_update, REFRESH_MS);
  });
})();
