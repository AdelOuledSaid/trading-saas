document.addEventListener("DOMContentLoaded", function () {
    const navbar = document.querySelector(".navbar");
    const burger = document.querySelector(".burger, .nav-toggle");
    const dropdownButtons = document.querySelectorAll(".nav-drop-btn");

    if (!navbar) return;

    function closeAllDropdowns() {
        document.querySelectorAll(".nav-dropdown").forEach((item) => {
            item.classList.remove("active");
        });
    }

    function closeLangDropdown() {
        const langDropdown = document.getElementById("langDropdown");
        if (langDropdown) {
            langDropdown.classList.remove("open");
        }
    }

    function closeMobileMenu() {
        navbar.classList.remove("mobile-open");
        if (burger) burger.classList.remove("active");
        document.body.classList.remove("menu-open");
        closeAllDropdowns();
        closeLangDropdown();
    }

    if (burger) {
        burger.addEventListener("click", function (e) {
            e.stopPropagation();
            navbar.classList.toggle("mobile-open");
            burger.classList.toggle("active");
            document.body.classList.toggle("menu-open");
        });
    }

    dropdownButtons.forEach((btn) => {
        btn.addEventListener("click", function (e) {
            if (window.innerWidth <= 980) {
                e.preventDefault();
                e.stopPropagation();

                const parent = this.closest(".nav-dropdown");
                if (!parent) return;

                const isActive = parent.classList.contains("active");

                closeAllDropdowns();
                closeLangDropdown();

                if (!isActive) {
                    parent.classList.add("active");
                }
            }
        });
    });

    // LANGUAGE DROPDOWN
    const langToggle = document.getElementById("langToggle");
    const langDropdown = document.getElementById("langDropdown");

    if (langToggle && langDropdown) {
        langToggle.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();

            closeAllDropdowns();
            langDropdown.classList.toggle("open");
        });
    }

    document.addEventListener("click", function (e) {
        if (!navbar.contains(e.target)) {
            closeMobileMenu();
        } else if (langDropdown && !langDropdown.contains(e.target)) {
            closeLangDropdown();
        }
    });

    window.addEventListener("resize", function () {
        if (window.innerWidth > 980) {
            closeMobileMenu();
        }
    });
});