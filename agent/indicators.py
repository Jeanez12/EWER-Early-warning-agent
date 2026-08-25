"""
EWER-Agent — Indicateurs de risque de conflit
Basés sur les méthodologies CEWARN (IGAD), ECOWARN (ECOWAS) et WANEP-WARN.
Ces catégories structurent l'extraction d'indicateurs par Gemini à partir
de rapports de terrain bruts (texte libre, formulaires Kobo, etc.)
"""

INDICATOR_CATEGORIES = {
    "security_incidents": {
        "label_fr": "Sécurité et incidents violents",
        "description": "Affrontements armés, raids, manifestations violentes, "
                        "crimes graves, présence d'armes, attaques ciblées.",
        "weight": 1.0,
    },
    "intercommunity_relations": {
        "label_fr": "Relations intercommunautaires",
        "description": "Tensions entre groupes (ethniques, religieux, "
                        "agriculteurs-éleveurs), discours de haine, rupture "
                        "de dialogue, rumeurs incendiaires.",
        "weight": 0.9,
    },
    "population_movement": {
        "label_fr": "Mouvements de population",
        "description": "Déplacements massifs, afflux de réfugiés ou de "
                        "personnes déplacées internes, exode soudain.",
        "weight": 0.8,
    },
    "governance_political": {
        "label_fr": "Gouvernance et espace politique",
        "description": "Contestation électorale, répression de l'opposition, "
                        "restriction des libertés civiques, défaillance des "
                        "institutions locales.",
        "weight": 0.7,
    },
    "economic_resource": {
        "label_fr": "Économie et ressources",
        "description": "Chocs de prix, pénuries alimentaires, compétition "
                        "accrue pour la terre ou l'eau, blocage de routes "
                        "commerciales.",
        "weight": 0.6,
    },
    "civil_society_media": {
        "label_fr": "Société civile et médias",
        "description": "Désinformation, fermeture de l'espace civique, "
                        "intimidation de journalistes ou d'organisations "
                        "locales.",
        "weight": 0.6,
    },
    "human_security_women_children": {
        "label_fr": "Sécurité des femmes et des enfants",
        "description": "Violences basées sur le genre, recrutement ou "
                        "exploitation d'enfants, indicateurs spécifiques "
                        "ajoutés par WANEP au-delà d'ECOWARN.",
        "weight": 0.9,
    },
}

# Niveaux de risque et seuils de score composite (0-10)
RISK_LEVELS = {
    "low": {"label_fr": "Faible", "min_score": 0, "max_score": 2.9},
    "moderate": {"label_fr": "Modéré", "min_score": 3, "max_score": 5.4},
    "high": {"label_fr": "Élevé", "min_score": 5.5, "max_score": 7.9},
    "critical": {"label_fr": "Critique", "min_score": 8, "max_score": 10},
}

# Seuil à partir duquel une alerte formelle est déclenchée automatiquement
ALERT_TRIGGER_THRESHOLD = "moderate"  # "moderate", "high" ou "critical"

# Règle d'escalade par tendance cumulative (le "twist" différenciant du projet)
# Si N signaux au niveau >= ESCALATION_MIN_LEVEL sont enregistrés pour la même
# zone dans la fenêtre de temps ESCALATION_WINDOW_DAYS, l'agent escalade
# automatiquement le niveau d'alerte même si chaque signal pris isolément
# n'aurait pas déclenché d'alerte.
ESCALATION_RULES = {
    "min_level": "moderate",
    "window_days": 14,
    "signal_count_trigger": 3,
    "escalate_to": "high",
}
