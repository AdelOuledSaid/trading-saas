document.addEventListener("DOMContentLoaded", function () {

    if (!window.unlockData || unlockData.length === 0) return;

    const ctx = document.getElementById("unlockChart").getContext("2d");

    const labels = unlockData.map(x => x.day);
    const values = unlockData.map(x => x.value);

    const maxValue = Math.max(...values, 1);

    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, "rgba(59,130,246,0.9)");
    gradient.addColorStop(1, "rgba(59,130,246,0.05)");

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: "Unlock Volume",
                data: values,
                backgroundColor: gradient,
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,

            plugins: {
                legend: { display: false },

                tooltip: {
                    backgroundColor: "#0b1220",
                    borderColor: "#334155",
                    borderWidth: 1,
                    titleColor: "#fff",
                    bodyColor: "#94a3b8",
                    callbacks: {
                        label: function(ctx) {
                            return "$" + ctx.raw.toLocaleString();
                        }
                    }
                }
            },

            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: "#64748b",
                        font: { size: 10 }
                    }
                },
                y: {
                    grid: {
                        color: "rgba(148,163,184,0.1)"
                    },
                    ticks: {
                        color: "#64748b",
                        callback: val => "$" + val.toLocaleString()
                    }
                }
            }
        }
    });

});