function submitQuiz(formId, answers, resultId) {
    const form = document.getElementById(formId);
    const resultBox = document.getElementById(resultId);

    if (!form || !resultBox) return;

    let score = 0;

    answers.forEach((answer, index) => {
        const selected = form.querySelector(`input[name="q${index + 1}"]:checked`);
        if (selected && selected.value === answer) {
            score++;
        }
    });

    const total = answers.length;
    const percent = Math.round((score / total) * 100);

    if (percent >= 70) {
        resultBox.innerHTML = `
            <div class="academy-result academy-result-success">
                Bravo. Score : ${score}/${total} (${percent}%). Validation réussie.
            </div>
        `;
    } else {
        resultBox.innerHTML = `
            <div class="academy-result academy-result-fail">
                Score : ${score}/${total} (${percent}%). Reprenez le module puis réessayez.
            </div>
        `;
    }
}

function showUpgradePopup() {
    const popup = document.getElementById("upgradePopup");
    if (!popup) return;
    popup.classList.add("active");
    popup.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
}

function closeUpgradePopup() {
    const popup = document.getElementById("upgradePopup");
    if (!popup) return;
    popup.classList.remove("active");
    popup.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
}

document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
        closeUpgradePopup();
    }
});

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-upgrade-trigger='true']").forEach((el) => {
        el.addEventListener("click", function (event) {
            event.preventDefault();
            showUpgradePopup();
        });
    });

    const autoPopup = document.body.dataset.autoUpgradePopup;
    if (autoPopup === "true") {
        setTimeout(() => {
            showUpgradePopup();
        }, 1800);
    }
});