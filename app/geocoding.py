"""Géocodage d'adresses françaises via l'API Base Adresse Nationale (BAN).

API publique, gratuite, sans clé : https://api-adresse.data.gouv.fr/
"""
from __future__ import annotations

from typing import Optional

import requests

from app.config import BAN_GEOCODE_URL


class GeocodeResult:
    def __init__(self, lat: float, lon: float, label: str, score: float):
        self.lat = lat
        self.lon = lon
        self.label = label
        self.score = score


def geocode_address(adresse: str, timeout: float = 10.0) -> Optional[GeocodeResult]:
    """Renvoie la meilleure correspondance géocodée pour l'adresse donnée.

    Renvoie None si l'adresse est vide, si l'API est injoignable, ou si
    aucun résultat n'est trouvé.
    """
    if not adresse or not adresse.strip():
        return None

    try:
        response = requests.get(
            BAN_GEOCODE_URL,
            params={"q": adresse.strip(), "limit": 1},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    features = data.get("features") or []
    if not features:
        return None

    best = features[0]
    coords = best.get("geometry", {}).get("coordinates")
    if not coords or len(coords) != 2:
        return None

    lon, lat = coords
    props = best.get("properties", {})
    return GeocodeResult(
        lat=lat,
        lon=lon,
        label=props.get("label", adresse),
        score=props.get("score", 0.0),
    )
