"""
EWER-Agent — Orchestration via Google Agent Development Kit (ADK)

Définit l'agent autonome EWER : il ingère un rapport de terrain brut, décide
lui-même (via ses outils et son raisonnement) s'il faut déclencher une
alerte, en tenant compte à la fois de l'analyse Gemini du rapport et de la
mémoire cumulative des signaux passés dans la même zone (Firestore).

Aucune validation humaine n'est requise dans la boucle : l'agent exécute
la chaîne complète ingestion → analyse → décision → action.
"""
import logging

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

import gemini_analysis
import integration_adapter
import memory_store
import notifier
from indicators import RISK_LEVELS, ALERT_TRIGGER_THRESHOLD

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.adk_agent")

_LEVEL_ORDER = ["low", "moderate", "high", "critical"]


def _meets_threshold(level: str) -> bool:
    try:
        return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(ALERT_TRIGGER_THRESHOLD)
    except ValueError:
        return False


def analyze_field_report(report_text: str, source_id: str = "") -> dict:
    """Outil ADK : analyse un rapport de terrain brut via Gemini et retourne
    les indicateurs de risque structurés."""
    return gemini_analysis.analyze_report(report_text, source_id=source_id)


def process_and_act(report_text: str, source_id: str = "") -> dict:
    """
    Outil ADK principal : exécute le pipeline complet de bout en bout de
    façon autonome — analyse, mémorisation, détection d'escalade, et
    déclenchement d'alerte si le seuil est atteint. C'est cette fonction
    qui incarne l'action réelle de l'agent (pas seulement une réponse texte).
    """
    analysis = gemini_analysis.analyze_report(report_text, source_id=source_id)

    db = memory_store.get_client()
    memory_store.store_report_analysis(db, analysis)

    zone = analysis.get("zone")
    escalation = memory_store.check_escalation(db, zone)

    should_alert = _meets_threshold(analysis.get("risk_level", "low")) or escalation is not None

    result = {
        "analysis": analysis,
        "escalation": escalation,
        "alert_triggered": should_alert,
    }

    if should_alert:
        alert_record = {
            "zone": zone,
            "risk_level": analysis.get("risk_level"),
            "composite_score": analysis.get("composite_score"),
            "source_id": source_id,
            "escalation": escalation,
        }
        alert_id = memory_store.store_alert(db, alert_record)
        sent = notifier.send_notification(analysis, escalation)
        pushed_external = integration_adapter.push_to_external_system(analysis, escalation)
        result["alert_id"] = alert_id
        result["notification_sent"] = sent
        result["pushed_to_external_system"] = pushed_external
        logger.info("Alerte déclenchée et notifiée pour zone=%s (alert_id=%s)", zone, alert_id)
    else:
        logger.info("Aucune alerte déclenchée pour zone=%s (niveau=%s)",
                     zone, analysis.get("risk_level"))

    return result


# Déclaration de l'agent ADK. Le LLM (Gemini) orchestre l'appel de l'outil
# process_and_act de façon autonome pour chaque rapport reçu.
ewer_agent = Agent(
    name="ewer_agent",
    model="gemini-3.5-flash",
    description=(
        "Agent autonome d'alerte précoce (EWER) inspiré de la méthodologie "
        "WANEP/ECOWARN. Traite les rapports de terrain en arrière-plan, "
        "sans intervention humaine, et déclenche des alertes formatées "
        "lorsque les indicateurs de risque ou les tendances cumulatives "
        "le justifient."
    ),
    instruction=(
        "Pour chaque rapport de terrain reçu, appelle immédiatement l'outil "
        "process_and_act avec le texte du rapport. Ne demande jamais de "
        "confirmation humaine : agis de façon autonome selon le résultat "
        "de l'analyse et de la détection d'escalade."
    ),
    tools=[FunctionTool(process_and_act)],
)
