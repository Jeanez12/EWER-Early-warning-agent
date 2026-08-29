"""
EWER-Agent — Module d'analyse Gemini
Extrait les indicateurs de risque d'un rapport de terrain brut et produit
un score de risque structuré (JSON) via l'API Gemini.
"""
import json
import logging
import os

from google import genai
from google.genai import types

from indicators import INDICATOR_CATEGORIES, RISK_LEVELS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ewer.gemini_analysis")

# NOTE: Gemini 3.5 Flash est le modèle GA (disponibilité générale) confirmé
# publiquement dans l'API Gemini au moment de l'écriture (août 2026).
# Gemini 3.5 Pro n'a pas encore d'ID de modèle public stable — ne pas le
# coder en dur. Vérifie le modèle disponible avec:
#   from google import genai; [m.name for m in genai.Client().models.list() if "3.5" in m.name]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def _build_system_prompt() -> str:
    categories_desc = "\n".join(
        f"- {key} ({v['label_fr']}): {v['description']}"
        for key, v in INDICATOR_CATEGORIES.items()
    )
    levels_desc = "\n".join(
        f"- {key} ({v['label_fr']}): score {v['min_score']}-{v['max_score']}"
        for key, v in RISK_LEVELS.items()
    )
    return f"""Tu es un analyste d'alerte précoce pour un système EWER
(Early Warning Early Response) inspiré des méthodologies CEWARN/ECOWARN/WANEP.

Tu reçois un rapport de terrain brut (texte libre ou données de formulaire).
Tu dois extraire les indicateurs de risque de conflit présents, selon les
catégories suivantes :
{categories_desc}

Pour chaque catégorie détectée, attribue une intensité de 0 (absent) à 10
(extrêmement grave). Calcule ensuite un score composite pondéré global de 0 à 10.

Niveaux de risque :
{levels_desc}

Réponds STRICTEMENT en JSON valide, sans aucun texte autour, avec ce schéma :
{{
  "zone": "<nom de la localité/zone extraite du rapport, ou 'non précisé'>",
  "summary_fr": "<résumé factuel en 1-2 phrases>",
  "indicators_detected": [
    {{"category": "<clé de catégorie>", "intensity": <0-10>, "evidence": "<courte justification extraite du texte>"}}
  ],
  "composite_score": <0-10, nombre décimal>,
  "risk_level": "<low|moderate|high|critical>",
  "recommended_action": "<action concrète recommandée en 1 phrase>"
}}

N'invente aucun fait absent du rapport. Si une information est absente, ne
la mentionne pas dans indicators_detected."""


def analyze_report(raw_report_text: str, source_id: str = "") -> dict:
    """
    Envoie un rapport brut à Gemini et retourne l'analyse structurée.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY manquant dans l'environnement.")

    client = genai.Client(api_key=api_key)

    system_prompt = _build_system_prompt()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=raw_report_text)],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    raw_text = response.text or ""
    logger.info("Réponse brute Gemini (source=%s): %s", source_id, raw_text[:500])

    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Échec du parsing JSON Gemini: %s (texte brut: %s)", exc, raw_text)
        raise

    if not isinstance(parsed, dict):
        raise ValueError(f"Réponse Gemini inattendue (attendu dict, reçu {type(parsed)})")

    parsed["source_id"] = source_id
    return parsed

