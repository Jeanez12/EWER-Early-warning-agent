"""
EWER-Agent — Module de notification
Formate et envoie le rapport d'alerte à la structure désignée (email
via SendGrid/SMTP, ou webhook — configurable). Pour la démo du hackathon,
un webhook générique (ex. requêtes vers un endpoint Slack/n8n/Zapier) est
utilisé par défaut ; il peut être remplacé par un vrai envoi email.
"""
import json
import logging
import os

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.notifier")


def format_alert_message(analysis: dict, escalation: dict | None = None) -> str:
    lines = [
        "🚨 ALERTE EWER — Système d'Alerte Précoce",
        f"Zone : {analysis.get('zone', 'non précisé')}",
        f"Niveau de risque : {analysis.get('risk_level', 'inconnu').upper()}",
        f"Score composite : {analysis.get('composite_score', 'N/A')}/10",
        f"Résumé : {analysis.get('summary_fr', '')}",
        f"Action recommandée : {analysis.get('recommended_action', '')}",
    ]
    if escalation:
        lines.append(
            f"⚠️ ESCALADE AUTOMATIQUE : {escalation['trigger_count']} signaux "
            f"cumulés en {escalation['window_days']} jours → niveau élevé à "
            f"{escalation['escalated_to'].upper()}"
        )
    indicators = analysis.get("indicators_detected", [])
    if indicators:
        lines.append("Indicateurs détectés :")
        for ind in indicators:
            lines.append(f"  - {ind['category']} (intensité {ind['intensity']}/10): {ind['evidence']}")
    return "\n".join(lines)


def send_notification(analysis: dict, escalation: dict | None = None) -> bool:
    """
    Envoie la notification vers le webhook configuré. Retourne True si
    l'envoi a réussi (ou si aucun webhook n'est configuré, en mode démo local).
    """
    message = format_alert_message(analysis, escalation)
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL")

    if not webhook_url:
        logger.warning("ALERT_WEBHOOK_URL non configuré — mode démo local.")
        logger.info("Message d'alerte (non envoyé) :\n%s", message)
        return True

    try:
        resp = requests.post(
            webhook_url,
            json={"text": message, "raw_analysis": analysis, "escalation": escalation},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Notification envoyée avec succès vers %s", webhook_url)
        return True
    except requests.RequestException as exc:
        logger.error("Échec de l'envoi de notification: %s", exc)
        return False
