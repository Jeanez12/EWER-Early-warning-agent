"""
EWER-Agent — Mémoire persistante (Firestore)
Stocke chaque analyse par zone géographique et détecte les tendances
d'escalade cumulative : plusieurs signaux modérés dans une même zone sur
une fenêtre de temps donnée déclenchent une escalade automatique, même si
chaque signal pris isolément n'aurait pas suffi.
"""
import datetime
import logging
import os

from google.cloud import firestore

from indicators import ESCALATION_RULES, RISK_LEVELS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.memory_store")

COLLECTION_REPORTS = "ewer_reports"
COLLECTION_ALERTS = "ewer_alerts"

_LEVEL_ORDER = ["low", "moderate", "high", "critical"]


def _level_index(level: str) -> int:
    return _LEVEL_ORDER.index(level) if level in _LEVEL_ORDER else -1


def get_client() -> firestore.Client:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    return firestore.Client(project=project_id)


def store_report_analysis(db: firestore.Client, analysis: dict) -> str:
    """Enregistre l'analyse d'un rapport dans Firestore. Retourne l'ID du document."""
    doc = dict(analysis)
    doc["received_at"] = datetime.datetime.now(datetime.timezone.utc)
    ref = db.collection(COLLECTION_REPORTS).document()
    ref.set(doc)
    logger.info("Rapport enregistré: %s (zone=%s, niveau=%s)",
                ref.id, analysis.get("zone"), analysis.get("risk_level"))
    return ref.id


def check_escalation(db: firestore.Client, zone: str) -> dict | None:
    """
    Vérifie si l'accumulation de signaux récents dans une zone justifie une
    escalade automatique du niveau de risque, indépendamment du dernier
    rapport pris isolément. C'est le mécanisme de détection de tendance.
    """
    if not zone or zone == "non précisé":
        return None

    min_level_idx = _level_index(ESCALATION_RULES["min_level"])
    window_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=ESCALATION_RULES["window_days"]
    )

    query = (
        db.collection(COLLECTION_REPORTS)
        .where("zone", "==", zone)
        .where("received_at", ">=", window_start)
    )

    qualifying_reports = []
    for doc in query.stream():
        data = doc.to_dict()
        if _level_index(data.get("risk_level", "low")) >= min_level_idx:
            qualifying_reports.append(data)

    if len(qualifying_reports) >= ESCALATION_RULES["signal_count_trigger"]:
        logger.warning(
            "Escalade détectée pour zone=%s: %d signaux >= %s en %d jours",
            zone, len(qualifying_reports), ESCALATION_RULES["min_level"],
            ESCALATION_RULES["window_days"],
        )
        return {
            "zone": zone,
            "escalated_to": ESCALATION_RULES["escalate_to"],
            "trigger_count": len(qualifying_reports),
            "window_days": ESCALATION_RULES["window_days"],
            "reason": "escalation_cumulative_trend",
        }
    return None


def store_alert(db: firestore.Client, alert: dict) -> str:
    """Enregistre une alerte formelle déclenchée (directe ou par escalade)."""
    doc = dict(alert)
    doc["created_at"] = datetime.datetime.now(datetime.timezone.utc)
    ref = db.collection(COLLECTION_ALERTS).document()
    ref.set(doc)
    logger.info("Alerte enregistrée: %s (zone=%s)", ref.id, alert.get("zone"))
    return ref.id
