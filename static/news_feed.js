document.addEventListener("DOMContentLoaded", function () {
    const sentimentFilter = document.getElementById("filterSentiment");
    const coinFilter = document.getElementById("filterCoin");
    const newsItems = Array.from(document.querySelectorAll(".oz-news-item"));
  
    function normalize(value) {
      return String(value || "").trim().toLowerCase();
    }
  
    function applyFilters() {
      const selectedSentiment = normalize(sentimentFilter ? sentimentFilter.value : "all");
      const selectedCoin = normalize(coinFilter ? coinFilter.value : "all");
  
      newsItems.forEach(function (item) {
        const itemSentiment = normalize(item.dataset.sentiment);
        const itemCoin = normalize(item.dataset.coin);
  
        const matchSentiment =
          selectedSentiment === "all" || selectedSentiment === itemSentiment;
  
        const matchCoin =
          selectedCoin === "all" || selectedCoin === itemCoin;
  
        if (matchSentiment && matchCoin) {
          item.classList.remove("hidden");
        } else {
          item.classList.add("hidden");
        }
      });
    }
  
    function animateCards() {
      newsItems.forEach(function (card, index) {
        card.style.opacity = "0";
        card.style.transform = "translateY(14px)";
  
        setTimeout(function () {
          card.style.transition = "opacity 0.35s ease, transform 0.35s ease";
          card.style.opacity = "1";
          card.style.transform = "translateY(0)";
        }, index * 45);
      });
    }
  
    function enableCardHover() {
      newsItems.forEach(function (card) {
        card.addEventListener("mouseenter", function () {
          card.style.transform = "translateY(-5px)";
        });
  
        card.addEventListener("mouseleave", function () {
          card.style.transform = "translateY(0)";
        });
      });
    }
  
    if (sentimentFilter) {
      sentimentFilter.addEventListener("change", applyFilters);
    }
  
    if (coinFilter) {
      coinFilter.addEventListener("change", applyFilters);
    }
  
    applyFilters();
    animateCards();
    enableCardHover();
  });