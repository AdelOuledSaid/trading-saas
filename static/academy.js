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

function getAcademyLevelKey() {
    return document.body.dataset.academyLevel || "level1";
}

function getAcademyStorageKey(levelKey) {
    return `academy_progress_${levelKey}`;
}

function getAcademyBadgeStorageKey(levelKey) {
    return `academy_badge_shown_${levelKey}`;
}

function getLevelTotalLessons() {
    const bodyValue = parseInt(document.body.dataset.academyTotalLessons || "0", 10);
    if (!Number.isNaN(bodyValue) && bodyValue > 0) {
        return bodyValue;
    }

    const lessonNodes = document.querySelectorAll("[data-complete-lesson]");
    return lessonNodes.length || 10;
}

function getAcademyProgress(levelKey = getAcademyLevelKey()) {
    try {
        return JSON.parse(localStorage.getItem(getAcademyStorageKey(levelKey)) || "{}");
    } catch (error) {
        return {};
    }
}

function setAcademyProgress(progress, levelKey = getAcademyLevelKey()) {
    localStorage.setItem(getAcademyStorageKey(levelKey), JSON.stringify(progress));
}

function getCompletedLessonsCount(levelKey = getAcademyLevelKey()) {
    const progress = getAcademyProgress(levelKey);
    return Object.keys(progress).filter((key) => progress[key] === true).length;
}

function markLessonComplete(lessonId, levelKey = getAcademyLevelKey()) {
    if (!lessonId) return;

    const progress = getAcademyProgress(levelKey);
    progress[lessonId] = true;
    setAcademyProgress(progress, levelKey);

    updateProgressUI(levelKey);
}

function unmarkLessonComplete(lessonId, levelKey = getAcademyLevelKey()) {
    if (!lessonId) return;

    const progress = getAcademyProgress(levelKey);
    delete progress[lessonId];
    setAcademyProgress(progress, levelKey);

    updateProgressUI(levelKey);
}

function toggleLessonComplete(lessonId, levelKey = getAcademyLevelKey()) {
    if (!lessonId) return;

    const progress = getAcademyProgress(levelKey);

    if (progress[lessonId]) {
        delete progress[lessonId];
    } else {
        progress[lessonId] = true;
    }

    setAcademyProgress(progress, levelKey);
    updateProgressUI(levelKey);
}

function getLessonElementsForCurrentLevel() {
    return document.querySelectorAll("[data-complete-lesson]");
}

function getBadgeElementsForCurrentLevel() {
    return document.querySelectorAll("[data-lesson-badge]");
}

function updateProgressBars(percent) {
    document.querySelectorAll(".academy-progress-fill").forEach((el) => {
        el.style.width = `${percent}%`;
    });
}

function updateProgressHeadNumbers(percent) {
    document.querySelectorAll(".academy-progress-head strong").forEach((el) => {
        const label = el.closest(".academy-progress-head")?.querySelector("span")?.textContent?.toLowerCase() || "";
        if (label.includes("progression")) {
            el.textContent = `${percent}%`;
        }
    });
}

function updateScoreRings(percent) {
    document.querySelectorAll(".academy-score-ring").forEach((el) => {
        el.style.setProperty("--score", percent);
    });

    document.querySelectorAll(".academy-score-ring-inner strong").forEach((el) => {
        el.textContent = `${percent}%`;
    });
}

function updateLessonButtons(progress) {
    getLessonElementsForCurrentLevel().forEach((button) => {
        const lessonId = button.dataset.completeLesson;
        const isDone = !!progress[lessonId];

        if (isDone) {
            button.textContent = "✓ Module validé";
            button.classList.add("is-completed");
        } else {
            button.textContent = "✔ Marquer comme terminé";
            button.classList.remove("is-completed");
        }
    });
}

function updateLessonBadges(progress) {
    getBadgeElementsForCurrentLevel().forEach((badge) => {
        const lessonId = badge.dataset.lessonBadge;
        const isDone = !!progress[lessonId];

        if (isDone) {
            badge.textContent = "✓ Module validé";
            badge.classList.add("validated");
            badge.classList.remove("current");
        }
    });
}

function updateCompletionMessage(percent, completedLessons, totalLessons) {
    const targets = document.querySelectorAll("[data-academy-completion-text]");
    targets.forEach((el) => {
        el.textContent = `${completedLessons}/${totalLessons} modules validés • ${percent}% complété`;
    });
}

function getLevelDisplayName(levelKey) {
    const customName = document.body.dataset.academyLevelName;
    if (customName) return customName;

    const map = {
        level1: "Niveau 1",
        level2: "Niveau 2",
        level3: "Niveau 3",
        level4: "Niveau 4 Pro"
    };

    return map[levelKey] || levelKey;
}

function checkCompletionBadge(completedLessons, totalLessons, levelKey = getAcademyLevelKey()) {
    const badge = document.getElementById("academyCompletionBadge");
    const alreadyShown = localStorage.getItem(getAcademyBadgeStorageKey(levelKey));
    const levelName = getLevelDisplayName(levelKey);

    if (completedLessons >= totalLessons && alreadyShown !== "true") {
        localStorage.setItem(getAcademyBadgeStorageKey(levelKey), "true");

        const message = `🎓 ${levelName} terminé. Badge débloqué.`;

        if (badge) {
            badge.innerHTML = `
                <div class="academy-result academy-result-success">
                    ${message}
                </div>
            `;
        } else {
            alert(message);
        }
    }
}

function updateProgressUI(levelKey = getAcademyLevelKey()) {
    const progress = getAcademyProgress(levelKey);
    const totalLessons = getLevelTotalLessons();
    const completedLessons = Object.keys(progress).filter((key) => progress[key] === true).length;
    const percent = totalLessons > 0
        ? Math.min(100, Math.round((completedLessons / totalLessons) * 100))
        : 0;

    updateProgressBars(percent);
    updateProgressHeadNumbers(percent);
    updateScoreRings(percent);
    updateLessonButtons(progress);
    updateLessonBadges(progress);
    updateCompletionMessage(percent, completedLessons, totalLessons);
    checkCompletionBadge(completedLessons, totalLessons, levelKey);
}

function bindLessonCompletionButtons(levelKey = getAcademyLevelKey()) {
    getLessonElementsForCurrentLevel().forEach((button) => {
        button.addEventListener("click", function () {
            const lessonId = this.dataset.completeLesson;
            toggleLessonComplete(lessonId, levelKey);
        });
    });
}

function bindAccordionAutoOpen() {
    document.querySelectorAll(".academy-outline-link").forEach((link) => {
        link.addEventListener("click", function () {
            const href = this.getAttribute("href");
            if (!href || !href.startsWith("#")) return;

            const target = document.querySelector(href);
            if (!target) return;

            if (target.tagName.toLowerCase() === "details") {
                target.open = true;
            }
        });
    });
}

function resetCurrentLevelProgress() {
    const levelKey = getAcademyLevelKey();
    localStorage.removeItem(getAcademyStorageKey(levelKey));
    localStorage.removeItem(getAcademyBadgeStorageKey(levelKey));
    updateProgressUI(levelKey);
}

document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
        closeUpgradePopup();
    }
});

document.addEventListener("DOMContentLoaded", function () {
    const levelKey = getAcademyLevelKey();

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

    bindLessonCompletionButtons(levelKey);
    bindAccordionAutoOpen();
    updateProgressUI(levelKey);

    document.querySelectorAll("[data-reset-academy-progress='true']").forEach((button) => {
        button.addEventListener("click", function () {
            resetCurrentLevelProgress();
        });
    });
});