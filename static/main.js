document.addEventListener("DOMContentLoaded", function () {
    const navbar = document.querySelector(".navbar");
    const burger = document.querySelector(".burger, .nav-toggle");
    const dropdownButtons = document.querySelectorAll(".nav-drop-btn");

    if (!navbar || !burger) return;

    function closeAllDropdowns() {
        document.querySelectorAll(".nav-dropdown").forEach((item) => {
            item.classList.remove("active");
        });
    }

    function closeMobileMenu() {
        navbar.classList.remove("mobile-open");
        burger.classList.remove("active");
        document.body.classList.remove("menu-open");
        closeAllDropdowns();
    }

    burger.addEventListener("click", function (e) {
        e.stopPropagation();
        navbar.classList.toggle("mobile-open");
        burger.classList.toggle("active");
        document.body.classList.toggle("menu-open");
    });

    dropdownButtons.forEach((btn) => {
        btn.addEventListener("click", function (e) {
            if (window.innerWidth <= 980) {
                e.preventDefault();
                e.stopPropagation();

                const parent = this.closest(".nav-dropdown");
                if (!parent) return;

                const isActive = parent.classList.contains("active");
                closeAllDropdowns();

                if (!isActive) {
                    parent.classList.add("active");
                }
            }
        });
    });

    document.addEventListener("click", function (e) {
        if (!navbar.contains(e.target)) {
            closeMobileMenu();
        }
    });

    window.addEventListener("resize", function () {
        if (window.innerWidth > 980) {
            closeMobileMenu();
        }
    });
});