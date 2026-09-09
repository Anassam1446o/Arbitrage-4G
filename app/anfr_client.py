"""Client pour l'API Open Data ANFR (API "records" v2.0, portail "d4c").

resource_id et noms de champs vérifiés à partir d'un appel réel et
fonctionnel observé dans un projet tiers open-source
(RealTux678/Generateur_ANFR, java/A_ANFR_Downloader.java) qui télécharge le
dataset "observatoire_2g_3g_4g" en CSV :
    https://data.anfr.fr/d4c/api/records/2.0/downloadfile/?format=csv
      &refine.generation=4G&refine.generation=5G
      &resource_id=88ef0887-6b0f-4d3f-8545-6d64c8f597da

Ce module suppose qu'un endpoint JSON filtrable par géolocalisation existe
sur le même préfixe records/2.0 (convention standard de ce type d'API) —
seul ce point précis (chemin exact de la recherche géographique + forme de
la réponse JSON) n'a pas pu être vérifié en environnement de développement
(accès réseau à data.anfr.fr bloqué). Le resource_id et les noms de champs,
eux, sont vérifiés (pas devinés). Voir README, section ANFR.
"""
from __future__ import annotations

from typing import Optional

import requests

from app.config import (
    ANFR_BASE_URL,
    ANFR_FIELD_GENERATION,
    ANFR_FIELD_OPERATOR,
    ANFR_OPERATOR_LABELS,
    ANFR_RESOURCE_ID,
    ANFR_SEARCH_RADIUS_M,
)
from app.models import AnfrSiteSummary


def _label_to_operator_key(label: str) -> Optional[str]:
    label_up = (label or "").strip().upper()
    for key, aliases in ANFR_OPERATOR_LABELS.items():
        if any(alias in label_up for alias in aliases):
            return key
    return None


def fetch_nearby_sites(
    lat: float,
    lon: float,
    radius_m: int = ANFR_SEARCH_RADIUS_M,
    technology_filter: str = "4G",
    timeout: float = 10.0,
) -> list[dict]:
    """Interroge l'API ANFR et renvoie la liste brute des enregistrements
    (dicts de champs) de sites radio dans le rayon donné. Renvoie [] si
    l'API est injoignable ou si le format de réponse est inattendu :
    l'appelant doit alors traiter l'environnement radio ANFR comme
    "indisponible", pas comme "aucune couverture"."""
    url = f"{ANFR_BASE_URL}/search/"
    params = {
        "resource_id": ANFR_RESOURCE_ID,
        "geofilter.distance": f"{lat},{lon},{radius_m}",
        "rows": 100,
    }
    if technology_filter:
        params[f"refine.{ANFR_FIELD_GENERATION}"] = technology_filter

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return []

    records = data.get("records")
    if records is None:
        return []
    return [r.get("fields", {}) for r in records if isinstance(r, dict)]


def summarize_by_operator(records: list[dict]) -> list[AnfrSiteSummary]:
    """Agrège les enregistrements bruts ANFR en nombre de sites par
    opérateur (clé interne orange/sfr/bouygues/free)."""
    counts: dict[str, int] = {}
    for record in records:
        label = record.get(ANFR_FIELD_OPERATOR, "")
        operator_key = _label_to_operator_key(label)
        if operator_key is None:
            continue
        counts[operator_key] = counts.get(operator_key, 0) + 1

    return [
        AnfrSiteSummary(operateur=op, nb_sites=count)
        for op, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def get_radio_environment(
    lat: float, lon: float, radius_m: int = ANFR_SEARCH_RADIUS_M
) -> tuple[list[AnfrSiteSummary], bool]:
    """Renvoie (résumé par opérateur, données_disponibles).

    données_disponibles=False signifie que l'API n'a pas répondu (ou dans
    un format inattendu) : le moteur de décision ne doit pas conclure à une
    absence de couverture dans ce cas, seulement le signaler comme donnée
    manquante à vérifier manuellement.
    """
    records = fetch_nearby_sites(lat, lon, radius_m)
    if not records:
        return [], False
    return summarize_by_operator(records), True
