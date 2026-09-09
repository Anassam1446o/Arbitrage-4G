"""Grille de qualification du signal 4G (RSRP x SNR).

Reprend telle quelle la grille utilisée sur le terrain par le prestataire
Adista/Waycom (visible dans les rapports de MES) : c'est le référentiel
"métier" le plus fiable dont on dispose pour transformer un couple
(RSRP, SNR) en verdict bon/moyen/mauvais, plutôt que d'inventer des seuils.
"""
from __future__ import annotations

import unicodedata
from typing import Optional


def _rsrp_band(rsrp_dbm: float) -> int:
    if rsrp_dbm > -85:
        return 0
    if rsrp_dbm > -100:
        return 1
    if rsrp_dbm > -115:
        return 2
    return 3


def _snr_band(snr_db: float) -> int:
    if snr_db > 15:
        return 0  # Excellent
    if snr_db > 5:
        return 1  # Bon
    if snr_db > 0:
        return 2  # Moyen
    return 3  # Faible


# [ligne RSRP][colonne SNR] -> verdict simplifié.
# Vert -> "bon", Jaune -> "moyen", Triangle bleu (limite/utilisable) -> "moyen",
# Rouge -> "mauvais".
_VERDICT_MATRIX = [
    ["bon", "bon", "moyen", "mauvais"],
    ["bon", "bon", "moyen", "mauvais"],
    ["bon", "moyen", "moyen", "mauvais"],
    ["moyen", "moyen", "mauvais", "mauvais"],
]

# Libellé qualitatif détaillé, pour affichage (repris de la grille terrain).
_LABEL_MATRIX = [
    ["Performance optimale", "Très bonne", "Correcte", "Dégradée"],
    ["Très bonne", "Bonne", "Acceptable", "Problématique"],
    ["Bonne", "Acceptable", "Limite", "Très dégradée"],
    ["Utilisable", "Limite", "Critique", "Inutilisable"],
]


def classify_signal(rsrp_dbm: Optional[float], snr_db: Optional[float]) -> Optional[str]:
    """Renvoie "bon" / "moyen" / "mauvais", ou None si une valeur manque."""
    if rsrp_dbm is None or snr_db is None:
        return None
    return _VERDICT_MATRIX[_rsrp_band(rsrp_dbm)][_snr_band(snr_db)]


def describe_signal(rsrp_dbm: Optional[float], snr_db: Optional[float]) -> Optional[str]:
    if rsrp_dbm is None or snr_db is None:
        return None
    return _LABEL_MATRIX[_rsrp_band(rsrp_dbm)][_snr_band(snr_db)]


_QUALITATIVE_TO_VERDICT = {
    "excellent": "bon",
    "bien": "bon",
    "bon": "bon",
    "tres bon": "bon",
    "moyen": "moyen",
    "correct": "moyen",
    "mauvais": "mauvais",
    "faible": "mauvais",
    "degrade": "mauvais",
    "degradee": "mauvais",
}


def normalize_qualitative_verdict(raw: Optional[str]) -> Optional[str]:
    """Convertit un verdict texte saisi par un technicien (EXCELLENT, BIEN,
    MOYEN, MAUVAIS, ...) vers bon/moyen/mauvais."""
    if not raw:
        return None
    key = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    key = key.strip().lower()
    return _QUALITATIVE_TO_VERDICT.get(key)
