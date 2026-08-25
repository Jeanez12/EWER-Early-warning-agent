"""
EWER-Agent — Point d'entrée Cloud Run

Expose:
- POST /pubsub-push : endpoint appelé par Pub/Sub à chaque nouveau rapport
  publié sur le topic (ingestion asynchrone en arrière-plan, sans que
  l'agent attende une requête utilisateur).
- POST /ingest : endpoint direct pour tester manuellement (démo/curl).
- GET  /healthz : vérification de santé pour Cloud Run.
"""
import base64
import json
import logging
import os

from flask import Flask, request, jsonify

from ewer_adk_agent import process_and_act
from monthly_report import generate_monthly_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.main")

app = Flask(__name__)


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/ingest", methods=["POST"])
def ingest():
    """Endpoint de test direct : POST {"report_text": "...", "source_id": "..."}"""
    payload = request.get_json(force=True, silent=True) or {}
    report_text = payload.get("report_text", "")
    source_id = payload.get("source_id", "manual")

    if not report_text:
        return jsonify({"error": "report_text manquant"}), 400

    result = process_and_act(report_text, source_id=source_id)
    return jsonify(result), 200


@app.route("/pubsub-push", methods=["POST"])
def pubsub_push():
    """
    Endpoint Pub/Sub push. Google Cloud Pub/Sub envoie ici chaque message
    publié sur le topic 'ewer-incoming-reports'. C'est ce mécanisme qui
    permet à l'agent de tourner de façon réellement asynchrone en
    arrière-plan, indépendamment de toute session de chat.
    """
    envelope = request.get_json(force=True, silent=True)
    if not envelope or "message" not in envelope:
        logger.error("Requête Pub/Sub invalide: %s", envelope)
        return jsonify({"error": "format Pub/Sub invalide"}), 400

    pubsub_message = envelope["message"]
    data_encoded = pubsub_message.get("data", "")
    try:
        data_decoded = base64.b64decode(data_encoded).decode("utf-8")
        payload = json.loads(data_decoded)
    except Exception as exc:
        logger.error("Échec du décodage du message Pub/Sub: %s", exc)
        return jsonify({"error": "décodage échoué"}), 400

    report_text = payload.get("report_text", "")
    source_id = payload.get("source_id", pubsub_message.get("messageId", "pubsub"))

    if not report_text:
        logger.error("report_text manquant dans le message Pub/Sub")
        return jsonify({"error": "report_text manquant"}), 400

    logger.info("Traitement asynchrone du rapport source_id=%s", source_id)
    result = process_and_act(report_text, source_id=source_id)
    logger.info("Résultat: alert_triggered=%s", result.get("alert_triggered"))

    # Toujours retourner 200 pour acquitter le message Pub/Sub
    return jsonify({"status": "processed", "alert_triggered": result.get("alert_triggered")}), 200


@app.route("/monthly-report-trigger", methods=["POST"])
def monthly_report_trigger():
    """
    Endpoint appelé par Cloud Scheduler le 1er de chaque mois (via un push
    Pub/Sub ou un appel HTTP direct authentifié). Génère la synthèse
    mensuelle des tendances et la cartographie des incidents, sans
    intervention humaine.
    """
    payload = request.get_json(force=True, silent=True) or {}
    year = payload.get("year")
    month = payload.get("month")

    logger.info("Déclenchement du rapport mensuel (year=%s, month=%s)", year, month)
    result = generate_monthly_report(year=year, month=month)
    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
