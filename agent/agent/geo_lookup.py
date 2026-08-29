"""
EWER-Agent — Coordonnées géographiques approximatives des communes du Bénin
Utilisées pour la génération de la cartographie mensuelle des incidents.
Source : centroïdes communaux approximatifs (à affiner avec des données
officielles IGN/INSAE si disponibles pour une version de production).
"""

BENIN_COMMUNE_COORDS = {
    "Banikoara": (11.3000, 2.4333),
    "Kandi": (11.1342, 2.9386),
    "Malanville": (11.8628, 3.3856),
    "Cotonou": (6.3703, 2.3912),
    "Porto-Novo": (6.4969, 2.6289),
    "Parakou": (9.3372, 2.6303),
    "Abomey-Calavi": (6.4489, 2.3556),
    "Natitingou": (10.3042, 1.3792),
    "Djougou": (9.7085, 1.6660),
    "Bohicon": (7.1781, 2.0667),
    "Kérou": (10.8000, 2.5833),
    "Karimama": (12.0667, 3.2000),
    "Ségbana": (10.9333, 3.7000),
    "Gogounou": (10.8333, 2.8333),
}

# Variantes d'écriture sans accents pour tolérance aux réponses LLM
_NORMALIZED_ALIASES = {
    "kerou": "Kérou",
    "segbana": "Ségbana",
    "porto novo": "Porto-Novo",
    "abomey calavi": "Abomey-Calavi",
}


def get_coords(zone_name: str | None):
    """Retourne (lat, lon) pour une zone connue, ou None si non répertoriée.
    Tolérant aux majuscules/minuscules, préfixes 'Commune de ...' et variantes d'accentuation."""
    if not zone_name or not isinstance(zone_name, str):
        return None

    cleaned = zone_name.strip()
    if cleaned in BENIN_COMMUNE_COORDS:
        return BENIN_COMMUNE_COORDS[cleaned]

    cleaned_lower = cleaned.lower()

    # Vérification avec les alias normalisés
    if cleaned_lower in _NORMALIZED_ALIASES:
        return BENIN_COMMUNE_COORDS[_NORMALIZED_ALIASES[cleaned_lower]]

    # Recherche insensible à la casse et par sous-chaîne (ex. "Commune de Banikoara")
    for name, coords in BENIN_COMMUNE_COORDS.items():
        name_lower = name.lower()
        if name_lower == cleaned_lower or name_lower in cleaned_lower:
            return coords

    # Recherche inversée sur les alias (ex. "Commune de Kerou")
    for alias, canonical in _NORMALIZED_ALIASES.items():
        if alias in cleaned_lower:
            return BENIN_COMMUNE_COORDS[canonical]

    return None

