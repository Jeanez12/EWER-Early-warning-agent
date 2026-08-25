# EWER-Agent — Agent Autonome d'Alerte Précoce

Projet soumis au hackathon **All Things Agentic** (Google / Devpost) — catégorie **Taskmaster**.

## Le problème

Dans les systèmes d'alerte précoce communautaires (méthodologie WANEP-WARN /
ECOWARN / CEWARN), des moniteurs de terrain envoient des rapports bruts
(texte libre, formulaires Kobo, messages WhatsApp). Aujourd'hui, un humain
doit *manuellement* : lire chaque rapport, en évaluer la gravité, décider
s'il justifie une alerte, rédiger le rapport formaté, et le transmettre à la
bonne structure. Ce processus est lent, dépend de la disponibilité humaine,
et rate souvent les tendances d'escalade progressive qui ne sont visibles
qu'en croisant plusieurs signaux dans le temps.

## Ce que fait l'agent, en autonomie complète

1. **Ingestion** — reçoit un rapport de terrain (via Pub/Sub, en
   arrière-plan, en continu — pas de session de chat).
2. **Analyse** — Gemini extrait les indicateurs de risque selon 7
   catégories standards (sécurité, relations intercommunautaires,
   mouvements de population, gouvernance, économie, société civile/médias,
   sécurité des femmes/enfants) et calcule un score composite.
3. **Mémorisation** — chaque analyse est enregistrée dans Firestore, par
   zone géographique.
4. **Détection de tendance (le twist)** — l'agent vérifie si plusieurs
   signaux modérés se sont accumulés dans la même zone sur une fenêtre de
   14 jours. Si oui, il **escalade automatiquement** le niveau d'alerte,
   même si chaque rapport pris isolément n'aurait pas déclenché d'alerte.
5. **Action autonome** — si le seuil est atteint (directement ou par
   escalade), l'agent rédige un rapport d'alerte formaté, l'enregistre, et
   envoie une notification — **sans validation humaine**.

## Fonctionnalité additionnelle — Rapport mensuel et cartographie

En plus du traitement en temps réel, l'agent génère automatiquement, le
1er de chaque mois (via **Cloud Scheduler**), un rapport de synthèse :
- Gemini analyse l'ensemble des signaux du mois et identifie les zones à
  tendance croissante et les catégories d'indicateurs dominantes.
- Une **carte interactive** des incidents (géolocalisés par commune,
  colorés par niveau de risque) est générée et stockée sur **Cloud
  Storage**, accessible via une URL publique incluse dans le rapport.
- Le rapport est archivé dans Firestore (`ewer_monthly_reports`) pour
  historique institutionnel.

## Intégration avec les systèmes d'alerte existants

L'agent n'est pas conçu pour remplacer les dispositifs d'alerte précoce
déjà en place (ECOWARN, WANEP-NEWS, ou tout système national équivalent),
mais pour s'y connecter. Le module `integration_adapter.py` convertit
chaque alerte dans un schéma neutre et interopérable, et peut la transmettre
automatiquement à un système tiers via un simple webhook/API REST
(configurable via `EXTERNAL_EWS_ENDPOINT`), sans modification du système
existant.

## Architecture

Voir `docs/architecture.png` (ou le diagramme ci-dessous).

```
[Rapport terrain brut]
        │
        ▼
  Pub/Sub topic (ewer-incoming-reports)
        │  (push asynchrone)
        ▼
  Cloud Run service (EWER-Agent, Flask + Google ADK)
        │
        ├──► Gemini API ─── extraction indicateurs + scoring
        │
        ├──► Firestore ──── mémoire persistante par zone
        │         │
        │         └──► détection d'escalade cumulative
        │
        └──► Notification (webhook) ── si seuil atteint
```

## Stack technique (conforme aux exigences du hackathon)

- **Gemini 3.5 Flash** (via API Gemini, `gemini-3.5-flash` — modèle en
  disponibilité générale) — analyse, scoring et synthèse mensuelle. Avant
  la soumission finale, vérifie sur https://aistudio.google.com si Gemini
  3.5 Pro est devenu disponible publiquement et mets à jour `GEMINI_MODEL`
  si tu préfères l'utiliser.
- **Google ADK** (Agent Development Kit) — orchestration autonome de
  l'agent (`agent/ewer_adk_agent.py`)
- **Cloud Run** — hébergement du service
- **Firestore** — mémoire persistante (rapports + alertes + rapports mensuels)
- **Pub/Sub** — ingestion asynchrone en arrière-plan
- **Cloud Storage** — stockage des cartes interactives mensuelles
- **Cloud Scheduler** — déclenchement automatique du rapport mensuel

## Structure du dépôt

```
ewer-agent/
├── agent/
│   ├── main.py                  # Point d'entrée Flask (Cloud Run)
│   ├── ewer_adk_agent.py        # Agent ADK + logique de décision autonome
│   ├── gemini_analysis.py       # Extraction d'indicateurs via Gemini
│   ├── memory_store.py          # Firestore : stockage + détection d'escalade
│   ├── notifier.py              # Formatage et envoi des alertes
│   ├── integration_adapter.py   # Connexion aux systèmes d'alerte existants
│   ├── monthly_report.py        # Synthèse mensuelle + cartographie
│   ├── geo_lookup.py            # Coordonnées des communes (cartographie)
│   ├── indicators.py            # Config des indicateurs EWER standards
│   ├── requirements.txt
│   └── Dockerfile
├── deploy/
│   └── deploy.sh             # Script de déploiement Google Cloud complet
├── tests/
│   └── sample_reports.py     # Rapports fictifs pour tester le pipeline
└── README.md
```

## Instructions de déploiement (reproductibles)

### Prérequis
- Un projet Google Cloud avec facturation activée
- Une clé API Gemini (https://aistudio.google.com/apikey)
- Google Cloud Shell (recommandé, rien à installer) ou `gcloud` CLI en local

### Étapes

1. **Cloner le dépôt** (dans Cloud Shell ou en local) :
   ```bash
   git clone <URL_DU_REPO>
   cd ewer-agent
   ```

2. **Configurer les variables d'environnement** :
   ```bash
   export PROJECT_ID="ton-project-id"
   export GEMINI_API_KEY="ta-cle-api-gemini"
   ```

3. **Lancer le déploiement complet** (active les APIs, crée Firestore,
   déploie sur Cloud Run, crée le topic et la souscription Pub/Sub) :
   ```bash
   bash deploy/deploy.sh
   ```

4. **Tester le pipeline** (le script affiche les commandes exactes à la
   fin de son exécution) :
   ```bash
   curl -X POST <SERVICE_URL>/ingest \
     -H 'Content-Type: application/json' \
     -d '{"report_text": "Tensions signalées entre deux communautés...", "source_id": "test-1"}'
   ```

5. **Tester le flux asynchrone réel via Pub/Sub** :
   ```bash
   gcloud pubsub topics publish ewer-incoming-reports \
     --message='{"report_text": "...", "source_id": "test-2"}'
   ```

### Exécution locale (sans déploiement, pour développement)

```bash
cd agent
pip install -r requirements.txt
export GEMINI_API_KEY="ta-cle"
export GOOGLE_CLOUD_PROJECT="ton-project-id"
python main.py
# Le service tourne sur http://localhost:8080
```

## Note sur la démo

Le script `deploy/deploy.sh` exécute des actions Google Cloud réelles et
observables (Cloud Run, Firestore, Pub/Sub) — la vidéo de démonstration
montre les logs Cloud Run en direct, une mise à jour Firestore visible dans
la console, et l'alerte déclenchée automatiquement suite à l'escalade
cumulative simulée avec `tests/sample_reports.py`.
