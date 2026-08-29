"""
Rapports de terrain fictifs pour tester le pipeline EWER-Agent.
Usage (depuis la racine du projet ewer-agent/ avec GEMINI_API_KEY et GOOGLE_CLOUD_PROJECT
définis dans l'environnement) :

    python -c "
    import sys, os; sys.path.insert(0, 'agent')
    from tests.sample_reports import REPORTS
    from ewer_adk_agent import process_and_act
    for r in REPORTS:
        print(process_and_act(r['text'], source_id=r['id']))
    "
"""


REPORTS = [
    {
        "id": "demo-001-faible",
        "text": (
            "Rapport hebdomadaire de routine, commune de Kandi. Marché "
            "hebdomadaire s'est tenu normalement. Aucune tension signalée "
            "entre les groupes présents. Activités agricoles en cours "
            "normalement."
        ),
    },
    {
        "id": "demo-002-modere-1",
        "text": (
            "Commune de Banikoara, zone frontalière. Des tensions ont été "
            "observées entre éleveurs peuls et agriculteurs locaux suite à "
            "des dégâts sur des champs de coton. Une réunion de médiation "
            "communautaire est prévue mais aucun accord n'a encore été trouvé. "
            "Rumeurs de représailles circulant sur les réseaux sociaux locaux."
        ),
    },
    {
        "id": "demo-003-modere-2",
        "text": (
            "Banikoara, deuxième signalement en 10 jours. Nouvelle altercation "
            "verbale entre jeunes des deux communautés lors du marché. Le "
            "chef traditionnel a appelé au calme mais la méfiance persiste. "
            "Quelques familles ont commencé à limiter leurs déplacements."
        ),
    },
    {
        "id": "demo-004-modere-3-escalade",
        "text": (
            "Banikoara, troisième signalement du mois. Un affrontement limité "
            "impliquant des jets de pierres a eu lieu hier soir entre groupes "
            "de jeunes des deux communautés. Aucun blessé grave rapporté mais "
            "la tension est palpable. Les autorités locales n'ont pas encore "
            "réagi officiellement."
        ),
    },
    {
        "id": "demo-005-critique",
        "text": (
            "URGENT — Commune de Malanville. Affrontement armé signalé cette "
            "nuit entre deux groupes, plusieurs blessés rapportés selon des "
            "témoins locaux. Déplacement de population en cours vers les "
            "localités voisines. Coupures de communication partielles dans "
            "la zone. Présence de discours de haine circulant sur WhatsApp "
            "appelant à la mobilisation."
        ),
    },
]
