"""Lecture du fichier Excel d'éligibilité FTTO et recherche par adresse/site.

Le schéma exact du fichier (noms de colonnes) sera confirmé quand le fichier
réel sera fourni. En attendant, la recherche essaie plusieurs noms de
colonnes usuels et une correspondance approximative sur l'adresse.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

import pandas as pd

from app.models import FttoEligibility

# Noms de colonnes candidats (insensibles à la casse), dans l'ordre de
# priorité. À ajuster une fois le fichier réel connu.
CANDIDATE_ADDRESS_COLUMNS = ["adresse", "adresse magasin", "address", "adresse complete"]
CANDIDATE_SITE_CODE_COLUMNS = ["code site", "site", "code magasin", "id site"]
CANDIDATE_ELIGIBLE_COLUMNS = ["eligible ftto", "eligibilite ftto", "ftto", "eligible"]


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    normalized_columns = {_normalize(str(c)): c for c in df.columns}
    for candidate in candidates:
        if candidate in normalized_columns:
            return normalized_columns[candidate]
    return None


def _parse_eligible_value(value) -> Optional[bool]:
    if pd.isna(value):
        return None
    text = _normalize(str(value))
    if text in {"oui", "yes", "true", "1", "eligible"}:
        return True
    if text in {"non", "no", "false", "0", "non eligible", "not eligible"}:
        return False
    return None


def load_ftto_table(excel_path: str) -> pd.DataFrame:
    return pd.read_excel(excel_path)


def check_eligibility(
    excel_path: str,
    adresse: Optional[str] = None,
    site_code: Optional[str] = None,
) -> FttoEligibility:
    try:
        df = load_ftto_table(excel_path)
    except Exception as exc:  # fichier illisible / absent
        return FttoEligibility(eligible=None, trouve=False, detail=f"Fichier FTTO illisible : {exc}")

    address_col = _find_column(df, CANDIDATE_ADDRESS_COLUMNS)
    site_col = _find_column(df, CANDIDATE_SITE_CODE_COLUMNS)
    eligible_col = _find_column(df, CANDIDATE_ELIGIBLE_COLUMNS)

    if eligible_col is None:
        return FttoEligibility(
            eligible=None,
            trouve=False,
            detail="Colonne d'éligibilité FTTO non trouvée dans le fichier Excel.",
        )

    match_row = None

    if site_code and site_col is not None:
        norm_target = _normalize(site_code)
        matches = df[df[site_col].astype(str).map(_normalize) == norm_target]
        if not matches.empty:
            match_row = matches.iloc[0]

    if match_row is None and adresse and address_col is not None:
        norm_target = _normalize(adresse)
        target_tokens = set(norm_target.split())
        best_score = 0
        for _, row in df.iterrows():
            row_addr = _normalize(str(row[address_col]))
            row_tokens = set(row_addr.split())
            score = len(target_tokens & row_tokens)
            if score > best_score:
                best_score = score
                match_row = row
        if best_score < 2:
            match_row = None

    if match_row is None:
        return FttoEligibility(eligible=None, trouve=False, detail="Site non trouvé dans le fichier FTTO.")

    eligible = _parse_eligible_value(match_row[eligible_col])
    return FttoEligibility(
        eligible=eligible,
        trouve=True,
        detail=None if eligible is not None else "Valeur d'éligibilité ambiguë dans le fichier.",
    )
