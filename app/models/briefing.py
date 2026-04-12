<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VelWolf — Market Briefing</title>

    <link rel="stylesheet" href="{{ url_for('static', filename='layout.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='dashboard.css') }}">
</head>
<body class="dashboard-body premium-dashboard-body ultra-dashboard-body">

{% include "partials/navbar.html" %}

<div class="dashboard-shell ultra-dashboard-shell">
    <main class="dashboard-content ultra-dashboard-content">

        <section class="dashboard-hero ultra-hero">
            <div class="dashboard-hero-content">
                <div class="hero-badge-line">
                    <span class="hero-badge">{{ current_user.plan | upper }}</span>
                    <span class="hero-live-dot">● Daily Market Briefing</span>
                </div>

                <div class="hero-title-row">
                    <h1 class="ultra-title">VelWolf Market Briefing</h1>
                    <span class="ai-badge">AI POWERED</span>
                </div>

                <p class="hero-subtitle">
                    Une lecture structurée du marché adaptée à votre niveau d’abonnement :
                    Basic simple, Premium complet, VIP détaillé.
                </p>

                <div class="hero-actions">
                    <a href="{{ url_for('dashboard.dashboard') }}" class="hero-secondary-btn">Retour dashboard</a>
                    <a href="{{ url_for('billing.pricing') }}" class="hero-utility-btn">Voir les offres</a>
                </div>
            </div>
        </section>

        <section class="premium-panel briefing-panel">
            <div class="panel-heading">
                <div>
                    <span class="panel-mini-title">Briefing daily</span>
                    <h2>Lecture marché du jour</h2>
                </div>
                <span class="stat-chip">{{ briefing_plan_label if briefing_plan_label else "Briefing" }}</span>
            </div>

            {% if briefing %}
                <div class="briefing-preview-box">
                    <div class="briefing-content-preview" style="white-space: pre-line;">{{ briefing.content }}</div>
                </div>
            {% else %}
                <div class="empty-state-box">
                    <h3>Aucun briefing disponible</h3>
                    <p>Le briefing du jour n’a pas encore été généré.</p>
                </div>
            {% endif %}
        </section>

    </main>
</div>

</body>
</html>