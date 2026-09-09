"""Lecture du fichier de suivi d'éligibilité FTTO et recherche par code DSR.

Calibré sur un export réel "Suivi_Eligibilités_CRF_XWAN_ORION" (CSV,
séparateur ';', encodage Windows-1252) :
- Colonne clé : "Code_DSR" (colonne C), format FR-XXNNNNN (XX = CS/SU/HY/
  AT/CC/..., NNNNN = 5 chiffres) — même format que le code site trouvé
  dans les rapports d'audit/MES (ex: "FR-CS00891_7499_MACON..." -> on
  extrait juste le préfixe "FR-CS00891").
- Éligibilité : déterminée à partir des colonnes "opérateur" spécifiques
  (FTTO Eurofiber/Covage/IELO/SFR ZV/SFR Clink/Orange/Axione, IELO Burst,
  Covage BPEA), pas de la colonne de synthèse "Préconisation FTTO" qui ne
  fait que dupliquer l'une d'elles. Chaque offre non-"NON" est éligible ;
  elles sont ensuite chiffrées via app/ftto_pricing.py et classées de la
  moins chère à la plus chère (voir build_priced_offers).
- Si un même Code_DSR apparaît plusieurs fois, on garde la ligne à la
  date d'éligibilité la plus récente (colonne "Dernière éligibilité").

Un fichier Excel (.xlsx) avec les mêmes colonnes fonctionne aussi.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from app.models import FttoEligibility

CODE_DSR_COLUMN_CANDIDATES = ["code_dsr", "code dsr"]
MULTI_PTO_COLUMN_CANDIDATES = ["multi pto"]
DATE_ELIGIBILITE_COLUMN_CANDIDATES = ["derniere eligibilite", "dernière éligibilité"]

# Colonnes "opérateur" spécifiques : chacune peut porter une offre FTTO
# distincte. On s'appuie sur celles-ci (pas sur les colonnes "Préconisation
# FTTO"/"Préconisation FTTO Burst", qui ne font que dupliquer l'une
# d'elles) pour établir la liste complète des offres éligibles à chiffrer
# et classer par prix.
SPECIFIC_OFFER_COLUMNS = [
    "FTTO Eurofiber",
    "FTTO Covage",
    "FTTO IELO",
    "FTTO SFR ZV",
    "FTTO SFR Clink",
    "FTTO Orange",
    "FTTO Axione",
    "IELO Burst",
    "Covage BPEA",
]

# Colonnes affichées telles quelles à titre de référence (vue brute du
# fichier), y compris les synthèses "Préconisation ...".
FTTO_OFFER_COLUMNS = ["Préconisation FTTO", "Préconisation FTTO Burst"] + SPECIFIC_OFFER_COLUMNS

_CODE_DSR_RE = re.compile(r"FR-?([A-Z]{2})(\d{5})", re.IGNORECASE)


def extract_code_dsr(text: str) -> Optional[str]:
    """Extrait le code DSR (format FR-XXNNNNN) d'un code site ou d'un texte
    plus long (ex: "FR-CS00891_7499_MACON - LACRETELLE" -> "FR-CS00891")."""
    if not text:
        return None
    match = _CODE_DSR_RE.search(text)
    if not match:
        return None
    return f"FR-{match.group(1).upper()}{match.group(2)}"


def _normalize_col(name) -> str:
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


def _load_table(file_path: str) -> pd.DataFrame:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)

    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(file_path, sep=";", encoding=encoding, low_memory=False)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error  # toutes les tentatives d'encodage ont échoué


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    normalized_columns = {_normalize_col(c): c for c in df.columns}
    for candidate in candidates:
        if candidate in normalized_columns:
            return normalized_columns[candidate]
    return None


def _parse_date_fr(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _collect_eligible_offers(row: pd.Series, df: pd.DataFrame) -> tuple[list[str], bool]:
    """Renvoie (offres éligibles dédupliquées, site étudié ?) à partir des
    colonnes opérateur spécifiques. "Étudié" = au moins une de ces
    colonnes est renseignée (même si toutes valent "NON")."""
    offers: list[str] = []
    seen_keys: set[str] = set()
    studied = False

    for label in SPECIFIC_OFFER_COLUMNS:
        col = _find_column(df, [_normalize_col(label)])
        if col is None:
            continue
        value = row[col]
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        studied = True
        if text.lower() == "non":
            continue
        key = _normalize_col(text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        offers.append(text)

    return offers, studied


def _parse_multi_pto(value) -> tuple[Optional[bool], str]:
    """La colonne "Multi PTO" ne contient pas littéralement "OK"/"KO" mais
    des valeurs comme "Possible (OI Orange)", "NON", "NC", "#N/A" : on les
    traduit en OK (multi PTO possible) / KO / inconnu."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, "non renseigné"
    text = str(value).strip()
    if not text:
        return None, "non renseigné"
    low = text.lower()
    if low.startswith("possible"):
        return True, text
    if low == "non":
        return False, text
    return None, text  # NC, #N/A, ?, ... : statut réellement inconnu


def check_eligibility(
    file_path: str,
    adresse: Optional[str] = None,
    site_code: Optional[str] = None,
) -> FttoEligibility:
    try:
        df = _load_table(file_path)
    except Exception as exc:  # fichier illisible / absent / encodage inattendu
        return FttoEligibility(eligible=None, trouve=False, detail=f"Fichier FTTO illisible : {exc}")

    code_dsr_col = _find_column(df, CODE_DSR_COLUMN_CANDIDATES)
    multi_pto_col = _find_column(df, MULTI_PTO_COLUMN_CANDIDATES)
    date_col = _find_column(df, DATE_ELIGIBILITE_COLUMN_CANDIDATES)

    if code_dsr_col is None:
        return FttoEligibility(
            eligible=None, trouve=False, detail="Colonne 'Code_DSR' non trouvée dans le fichier."
        )

    target_code = extract_code_dsr(site_code or "") or extract_code_dsr(adresse or "")
    if not target_code:
        return FttoEligibility(
            eligible=None, trouve=False, detail="Code DSR non identifiable pour ce site (format FR-XXNNNNN attendu)."
        )

    matches = df[df[code_dsr_col].astype(str).str.strip().str.upper() == target_code]
    if matches.empty:
        return FttoEligibility(
            eligible=None,
            trouve=False,
            detail=f"NC — code DSR {target_code} absent du fichier d'éligibilité FTTO.",
        )

    if len(matches) > 1 and date_col is not None:
        # Le site apparaît plusieurs fois (mises à jour successives) : on
        # garde la ligne à la date d'éligibilité la plus récente.
        parsed_dates = matches[date_col].map(_parse_date_fr)
        row = matches.loc[parsed_dates.sort_values(ascending=False, na_position="last").index[0]]
    else:
        row = matches.iloc[0]

    eligible_offers, studied = _collect_eligible_offers(row, df)
    if eligible_offers:
        eligible = True
        detail = f"{len(eligible_offers)} offre(s) FTTO éligible(s)."
    elif studied:
        eligible = False
        detail = "NON Eligible"
    else:
        eligible = None
        detail = "NC — site présent dans le fichier mais pas encore étudié."

    offres_disponibles: dict[str, str] = {}
    for offer_label in FTTO_OFFER_COLUMNS:
        col = _find_column(df, [_normalize_col(offer_label)])
        if col is None:
            continue
        value = row[col]
        offres_disponibles[offer_label] = "" if pd.isna(value) else str(value).strip()

    multi_pto, multi_pto_detail = (None, "colonne 'Multi PTO' non trouvée")
    if multi_pto_col is not None:
        multi_pto, multi_pto_detail = _parse_multi_pto(row[multi_pto_col])

    return FttoEligibility(
        eligible=eligible,
        trouve=True,
        detail=detail,
        offres_disponibles=offres_disponibles,
        multi_pto=multi_pto,
        multi_pto_detail=multi_pto_detail,
        offres_eligibles_brutes=eligible_offers,
    )
