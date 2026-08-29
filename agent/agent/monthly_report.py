"""
EWER-Agent — Rapport mensuel et cartographie des incidents

Déclenché automatiquement le 1er de chaque mois (via Cloud Scheduler →
Pub/Sub), ce module :
1. Récupère tous les rapports et alertes du mois écoulé depuis Firestore
2. Demande à Gemini une synthèse des tendances (zones à risque croissant,
   catégories dominantes, comparaison au mois précédent)
3. Génère une carte interactive (HTML) des incidents géolocalisés, colorée
   par niveau de risque
4. Stocke la carte sur Cloud Storage et produit un rapport texte complet
5. Peut pousser ce rapport vers un système d'alerte existant (ECOWARN,
   WANEP-NEWS, ou tout autre) via l'adaptateur d'intégration
"""
import datetime
import json
import logging
import os

import folium
from google import genai
from google.genai import types
from google.cloud import storage

from geo_lookup import get_coords
from indicators import RISK_LEVELS
import memory_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.monthly_report")

_RISK_COLORS = {
    "low": "green",
    "moderate": "orange",
    "high": "red",
    "critical": "darkred",
}


def _fetch_month_reports(db, year: int, month: int) -> list[dict]:
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    end_month = month + 1 if month < 12 else 1
    end_year = year if month < 12 else year + 1
    end = datetime.datetime(end_year, end_month, 1, tzinfo=datetime.timezone.utc)

    query = (
        db.collection("ewer_reports")
        .where("received_at", ">=", start)
        .where("received_at", "<", end)
    )
    return [doc.to_dict() for doc in query.stream()]


def _synthesize_trends(reports: list[dict]) -> dict:
    """Demande à Gemini une synthèse narrative des tendances du mois."""
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

    simplified = [
        {
            "zone": r.get("zone"),
            "risk_level": r.get("risk_level"),
            "composite_score": r.get("composite_score"),
            "indicators_detected": [
                i.get("category") for i in (r.get("indicators_detected") or []) if isinstance(i, dict)
            ],
        }
        for r in reports
    ]

    prompt = (
        "Voici la liste des rapports d'alerte précoce reçus ce mois-ci "
        "(format JSON). Produis une synthèse mensuelle structurée en JSON "
        "avec ce schéma :\n"
        '{"total_reports": <int>, "zones_a_surveiller": [<liste des zones '
        'avec tendance croissante>], "categories_dominantes": [<liste des '
        'catégories d\'indicateurs les plus fréquentes>], "narrative_fr": '
        '"<synthèse en 3-5 phrases pour un rapport institutionnel>"}\n\n'
        f"Données :\n{json.dumps(simplified, ensure_ascii=False)}"
    )

    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    raw_text = (response.text or "").strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    return json.loads(raw_text.strip())


def _build_incident_map(reports: list[dict]) -> str:
    """Génère une carte HTML interactive (folium) des incidents géolocalisés.
    Retourne le HTML sous forme de chaîne de caractères."""
    center = (9.3077, 2.3158)  # centre approximatif du Bénin
    fmap = folium.Map(location=center, zoom_start=7, tiles="CartoDB positron")

    plotted = 0
    for r in reports:
        coords = get_coords(r.get("zone"))
        if not coords:
            continue
        level = r.get("risk_level") or "low"
        color = _RISK_COLORS.get(level, "gray")
        popup = (
            f"<b>{r.get('zone') or 'non précisé'}</b><br>"
            f"Niveau : {level}<br>"
            f"Score : {r.get('composite_score', 'N/A')}<br>"
            f"{r.get('summary_fr') or ''}"
        )
        folium.CircleMarker(
            location=coords,
            radius=8 + 2 * (RISK_LEVELS.get(level, {}).get("min_score", 0)),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup, max_width=250),
        ).add_to(fmap)
        plotted += 1

    logger.info("Carte générée avec %d incidents géolocalisés (sur %d rapports).",
                plotted, len(reports))
    return fmap.get_root().render()


def _upload_map_to_storage(html_content: str, year: int, month: int) -> str:
    """Upload la carte HTML sur Cloud Storage et retourne l'URL publique."""
    bucket_name = os.environ.get("EWER_REPORTS_BUCKET")
    if not bucket_name:
        raise RuntimeError("EWER_REPORTS_BUCKET manquant dans l'environnement.")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob_name = f"monthly-maps/{year}-{month:02d}-incidents-map.html"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html_content, content_type="text/html")
    try:
        blob.make_public()
    except Exception as exc:
        logger.info("make_public() non applicable ou UBLA activé sur le bucket: %s", exc)

    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    logger.info("Carte mensuelle uploadée: %s", public_url)
    return public_url


def generate_monthly_report(year: int | None = None, month: int | None = None) -> dict:
    """
    Point d'entrée principal : génère le rapport mensuel complet
    (synthèse + carte) pour le mois donné (par défaut, le mois écoulé).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    if year is None or month is None:
        # Par défaut, le mois précédent
        first_of_this_month = now.replace(day=1)
        last_month_end = first_of_this_month - datetime.timedelta(days=1)
        target_year, target_month = last_month_end.year, last_month_end.month
    else:
        try:
            target_year = int(year)
            target_month = int(month)
        except (ValueError, TypeError):
            first_of_this_month = now.replace(day=1)
            last_month_end = first_of_this_month - datetime.timedelta(days=1)
            target_year, target_month = last_month_end.year, last_month_end.month

    db = memory_store.get_client()
    reports = _fetch_month_reports(db, target_year, target_month)

    if not reports:
        logger.info("Aucun rapport trouvé pour %04d-%02d, rapport vide généré.", target_year, target_month)
        return {
            "year": target_year, "month": target_month, "total_reports": 0,
            "narrative_fr": "Aucun signal enregistré ce mois-ci.",
            "map_url": None,
        }

    trends = _synthesize_trends(reports)
    map_html = _build_incident_map(reports)
    map_url = _upload_map_to_storage(map_html, target_year, target_month)

    result = {
        "year": target_year,
        "month": target_month,
        **trends,
        "map_url": map_url,
    }

    # Enregistrement du rapport mensuel lui-même dans Firestore pour historique
    db.collection("ewer_monthly_reports").document(f"{target_year}-{target_month:02d}").set({
        **result,
        "generated_at": now,
    })

    logger.info("Rapport mensuel %04d-%02d généré: %d rapports, carte: %s",
                target_year, target_month, result.get("total_reports", len(reports)), map_url)
    return result

