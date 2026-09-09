"""Client pour l'API Open Data ANFR (portail "data4C", format OpenDataSoft
Explore v2.1) : récupère les sites/antennes radio à proximité d'un point.

Le schéma exact du dataset (noms de champs, id du dataset) n'a pas pu être
vérifié en environnement de développement car l'accès réseau à data.anfr.fr
y est bloqué. Les noms de champs par défaut (voir app/config.py) sont une
best guess à confirmer une fois le programme exécuté avec un accès réseau
normal — voir README, section "Vérifier le schéma ANFR".
"""
from __future__ import annotations

from typing import Optional

import requests

from app.config import (
    ANFR_BASE_URL,
    ANFR_DATASET_ID,
    ANFR_FIELD_GENERATION,
    ANFR_FIELD_LAT,
    ANFR_FIELD_LON,
    ANFR_FIELD_OPERATOR,
    ANFR_OPERATOR_LABELS,
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
    de sites radio dans le rayon donné. Renvoie [] si l'API est injoignable
    (l'appelant doit alors traiter l'environnement radio ANFR comme
    "indisponible", pas comme "aucune couverture")."""
    url = f"{ANFR_BASE_URL}/{ANFR_DATASET_ID}/records"
    where_clause = f"distance({ANFR_FIELD_LAT}, geom'POINT({lon} {lat})', {radius_m}m)"
    if technology_filter:
        where_clause += f" AND {ANFR_FIELD_GENERATION} LIKE '%{technology_filter}%'"

    try:
        response = requests.get(
            url,
            params={"where": where_clause, "limit": 100},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return []

    return data.get("results", [])


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

    données_disponibles=False signifie que l'API n'a pas répondu : le moteur
    de décision ne doit pas conclure à une absence de couverture dans ce cas,
    seulement le signaler comme donnée manquante à vérifier manuellement.
    """
    records = fetch_nearby_sites(lat, lon, radius_m)
    if not records:
        return [], False
    return summarize_by_operator(records), True
