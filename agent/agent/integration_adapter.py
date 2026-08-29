"""
EWER-Agent — Adaptateur d'intégration avec les systèmes existants

L'agent n'est pas pensé pour remplacer les systèmes d'alerte précoce déjà
en place (ECOWARN, WANEP-NEWS, ou tout système national/local équivalent),
mais pour s'y connecter en amont ou en aval. Ce module fournit un schéma
de sortie standardisé et un mécanisme d'envoi générique (webhook/API REST)
afin que l'agent puisse être branché sur l'infrastructure existante d'une
organisation sans modification de son côté.
"""
import logging
import os

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.integration_adapter")


def to_standard_schema(analysis: dict, escalation: dict | None = None) -> dict:
    """
    Convertit une analyse EWER-Agent dans un schéma neutre inspiré des
    champs communs aux systèmes CEWARN/ECOWARN (catégorie d'indicateur,
    zone, sévérité, horodatage, source), afin de rester interopérable avec
    des systèmes tiers qui n'utilisent pas le même format interne.
    """
    raw_indicators = analysis.get("indicators_detected") or []
    categories = [
        i.get("category")
        for i in raw_indicators
        if isinstance(i, dict) and i.get("category")
    ]

    return {
        "schema_version": "ewer-agent-1.0",
        "event_type": "conflict_early_warning_signal",
        "location": {
            "name": analysis.get("zone") or "non précisé",
        },
        "severity": analysis.get("risk_level") or "unknown",
        "severity_score": analysis.get("composite_score"),
        "indicator_categories": categories,
        "narrative": analysis.get("summary_fr") or "",
        "recommended_action": analysis.get("recommended_action") or "",
        "escalation": escalation,
        "source_id": analysis.get("source_id") or "",
    }



def push_to_external_system(analysis: dict, escalation: dict | None = None) -> bool:
    """
    Envoie l'alerte au format standardisé vers un système externe configuré
    via EXTERNAL_EWS_ENDPOINT (ex. l'API d'un système NEWS national, ou un
    connecteur ECOWARN). Si aucun endpoint n'est configuré, ne fait rien
    (l'agent reste utilisable de façon autonome sans intégration externe).
    """
    endpoint = os.environ.get("EXTERNAL_EWS_ENDPOINT")
    if not endpoint:
        logger.info("Aucun EXTERNAL_EWS_ENDPOINT configuré — envoi externe ignoré.")
        return False

    payload = to_standard_schema(analysis, escalation)
    api_key = os.environ.get("EXTERNAL_EWS_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logger.info("Alerte transmise au système externe: %s", endpoint)
        return True
    except requests.RequestException as exc:
        logger.error("Échec de la transmission au système externe: %s", exc)
        return False
