#!/usr/bin/env bash
# EWER-Agent — Script de déploiement Google Cloud
# À exécuter depuis Google Cloud Shell (ou tout terminal avec gcloud CLI
# authentifié et configuré sur le bon projet).
#
# Usage:
#   export PROJECT_ID="ton-project-id"
#   export GEMINI_API_KEY="ta-cle-gemini"
#   bash deploy/deploy.sh

set -euo pipefail

: "${PROJECT_ID:?Variable PROJECT_ID requise. Fais: export PROJECT_ID=ton-project-id}"
: "${GEMINI_API_KEY:?Variable GEMINI_API_KEY requise. Fais: export GEMINI_API_KEY=ta-cle}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REGION="${REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-ewer-agent}"
TOPIC_NAME="${TOPIC_NAME:-ewer-incoming-reports}"
SUB_NAME="${SUB_NAME:-ewer-incoming-reports-push}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-ewer-reports}"
SCHEDULER_JOB_NAME="${SCHEDULER_JOB_NAME:-ewer-monthly-report}"

echo "=== 1/8 Configuration du projet ==="
gcloud config set project "$PROJECT_ID"

echo "=== 2/8 Activation des APIs nécessaires ==="
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  aiplatform.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  cloudscheduler.googleapis.com

echo "=== 3/8 Création de la base Firestore (mode natif) si absente ==="
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  gcloud firestore databases create --location="$REGION" --type=firestore-native

echo "=== 4/8 Création du bucket Cloud Storage (cartographie mensuelle) ==="
gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET_NAME}" --location="$REGION" --uniform-bucket-level-access

# Permet l'accès public en lecture aux cartes HTML générées mensuellement
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="allUsers" \
  --role="roles/storage.objectViewer" >/dev/null 2>&1 || true

echo "=== 5/8 Déploiement sur Cloud Run ==="
gcloud run deploy "$SERVICE_NAME" \
  --source "$REPO_ROOT/agent" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GEMINI_MODEL=gemini-3.5-flash,EWER_REPORTS_BUCKET=${BUCKET_NAME}"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)")
echo "Service déployé: $SERVICE_URL"

echo "=== 6/8 Création du topic Pub/Sub (ingestion asynchrone) ==="
gcloud pubsub topics describe "$TOPIC_NAME" >/dev/null 2>&1 || \
  gcloud pubsub topics create "$TOPIC_NAME"

echo "=== 7/8 Création de la souscription push vers l'agent ==="
gcloud pubsub subscriptions describe "$SUB_NAME" >/dev/null 2>&1 || \
  gcloud pubsub subscriptions create "$SUB_NAME" \
    --topic="$TOPIC_NAME" \
    --push-endpoint="${SERVICE_URL}/pubsub-push" \
    --ack-deadline=60

echo "=== 8/8 Création du job Cloud Scheduler (rapport mensuel automatique) ==="
gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --location="$REGION" >/dev/null 2>&1 || \
  gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
    --location="$REGION" \
    --schedule="0 6 1 * *" \
    --uri="${SERVICE_URL}/monthly-report-trigger" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body="{}" \
    --time-zone="Africa/Porto-Novo"

echo ""
echo "=========================================="
echo "Déploiement terminé."
echo "URL du service : $SERVICE_URL"
echo "Test rapide (endpoint direct) :"
echo "  curl -X POST ${SERVICE_URL}/ingest -H 'Content-Type: application/json' \\"
echo "    -d '{\"report_text\": \"Tensions signalées entre deux communautés...\", \"source_id\": \"test-1\"}'"
echo ""
echo "Test asynchrone (via Pub/Sub) :"
echo "  gcloud pubsub topics publish $TOPIC_NAME --message='{\"report_text\": \"...\", \"source_id\": \"test-2\"}'"
echo "=========================================="

