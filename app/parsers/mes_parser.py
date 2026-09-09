"""Parseur de rapports de Mise en Service (MES) 4G.

Calibré sur deux formats réels observés :
- Linkt (Praxedo) : tableaux PDF propres à 2 colonnes "libellé / valeur" ;
  les 2 relevés RSRP/SNR par opérateur (SFR + Orange) sont dans le
  commentaire libre du technicien, pas dans des champs dédiés.
- Adista (Waycom) : rapport "checklist" en texte à plat, un verdict
  qualitatif ("EXCELLENT/BIEN/MOYEN/MAUVAIS") est saisi en texte réel pour
  chaque opérateur testé, mais les valeurs RSRP/SNR numériques ne sont
  visibles que sur une capture d'écran photographiée (donc pas extractibles
  sans OCR) : on ne dispose que du verdict qualitatif dans ce cas.

Tout rapport ne correspondant à aucun de ces deux gabarits tombe sur un
parseur générique best-effort.
"""
from __future__ import annotations

import re
from typing import Optional

from app.models import MesReport, OperatorReading
from app.parsers.common import (
    enrich_adista_readings_with_ocr,
    extract_label_value_pairs,
    extract_line_value,
    extract_text,
    find_per_operator_readings,
    find_site_code,
    get_label,
    oneline,
)
from app.signal_quality import normalize_qualitative_verdict

_ANTENNA_TYPE_RE = re.compile(r"antennes?\s+(cierge|panneau|passive|active|omni\w*)", re.IGNORECASE)


def _to_float(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", raw)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def _detect_provider(text: str) -> Optional[str]:
    low = text.lower()
    if "linkt" in low:
        return "linkt"
    if "adista" in low or "waycom" in low:
        return "adista"
    return None


def parse_mes(file_path: str) -> MesReport:
    text = extract_text(file_path)
    provider = _detect_provider(text)
    if provider == "linkt":
        return _parse_linkt(file_path, text)
    if provider == "adista":
        return _parse_adista(file_path, text)
    return _parse_generic(text)


def _parse_linkt(file_path: str, text: str) -> MesReport:
    pairs = extract_label_value_pairs(file_path)

    site_code = oneline(get_label(pairs, "Site") or find_site_code(text))
    adresse = oneline(get_label(pairs, "Adresse"))

    rsrp_routeur = _to_float(
        get_label(pairs, "Valeur RSRP remontée par le routeur", "Valeur RSRP remontee par le routeur")
    )
    snr_routeur = _to_float(
        get_label(pairs, "Valeur SNR remontée par le routeur", "Valeur SNR remontee par le routeur")
    )

    antenne_raw = get_label(
        pairs,
        "Des antennes déportées ont-elles été installées ?",
        "Des antennes déportées ont-elles été installées",
    )
    antenne_installee = antenne_raw.lower().startswith("oui") if antenne_raw else None
    type_antenne = None
    if antenne_raw:
        match = _ANTENNA_TYPE_RE.search(antenne_raw)
        type_antenne = match.group(1).lower() if match else None

    commentaire = get_label(pairs, "Commentaire du technicien :", "Commentaire du technicien") or text

    lectures = [OperatorReading(**r) for r in find_per_operator_readings(commentaire)]

    operateur_retenu = None
    match = re.search(
        r"routeur\s+laiss\w*\s+sur\s+r[ée]seau\s+(orange|sfr|bouygues)", commentaire, re.IGNORECASE
    )
    if match:
        operateur_retenu = match.group(1).lower()

    resultat = get_label(pairs, "Résultat de l'intervention", "Résultat de l'intervention")

    return MesReport(
        site_code=site_code,
        adresse=adresse,
        prestataire="linkt",
        operateur_retenu=operateur_retenu,
        antenne_installee=antenne_installee,
        type_antenne=type_antenne,
        lectures=lectures,
        rsrp_routeur_dbm=rsrp_routeur,
        snr_routeur_db=snr_routeur,
        resultat_intervention=resultat,
        texte_brut=text,
    )


def _parse_adista(file_path: str, text: str) -> MesReport:
    site_code = extract_line_value(text, "Référence site client") or find_site_code(text)
    adresse = extract_line_value(text, "Adresse")
    resultat = extract_line_value(text, "Résultat de l'intervention")
    commentaire = extract_line_value(text, "Commentaires du technicien")

    first_operator_match = re.search(
        r"TEST AVEC L'OPERATEUR\s+(BOUYGUES|ORANGE|SFR)", text, re.IGNORECASE
    )
    operators_tested = [first_operator_match.group(1)] if first_operator_match else []
    operators_tested += re.findall(r"passer le routeur sur la sim (\w+)", text, re.IGNORECASE)

    qualities = re.findall(
        r"QUALIFERIEZ-VOUS LE SIGNAL\s*\?\s*\n\s*(EXCELLENT|BIEN|BON|MOYEN|MAUVAIS)",
        text,
        re.IGNORECASE,
    )

    lectures_dicts = [
        {
            "operateur": operateur.lower(),
            "qualite_signal": normalize_qualitative_verdict(qualite),
            "avec_antenne": True,
            "emplacement": "baie",  # seul emplacement testé lors d'une MES (routeur dans la baie)
        }
        for operateur, qualite in zip(operators_tested, qualities)
    ]
    lectures_dicts = enrich_adista_readings_with_ocr(file_path, lectures_dicts)
    lectures = [OperatorReading(**r) for r in lectures_dicts]

    final_match = re.search(
        r"QUEL OPERATEUR A FINALEMENT ETE ACTIVE\s*\?\s*\n\s*(\w+)", text, re.IGNORECASE
    )
    operateur_retenu = final_match.group(1).lower() if final_match else None

    antenne_installee = bool(
        re.search(r"installation d'une antenne", text, re.IGNORECASE)
        or re.search(r"antenne\s+d[ée]port[ée]e", text, re.IGNORECASE)
    )

    return MesReport(
        site_code=site_code,
        adresse=adresse,
        prestataire="adista",
        operateur_retenu=operateur_retenu,
        antenne_installee=antenne_installee or None,
        type_antenne="déportée" if antenne_installee else None,
        lectures=lectures,
        resultat_intervention=resultat,
        texte_brut=(commentaire or "") + "\n" + text,
    )


def _parse_generic(text: str) -> MesReport:
    from app.parsers.common import find_address, find_single_rsrp, find_single_snr

    lectures = [OperatorReading(**r) for r in find_per_operator_readings(text)]
    rsrp = find_single_rsrp(text)
    snr = find_single_snr(text)

    return MesReport(
        site_code=find_site_code(text),
        adresse=find_address(text),
        prestataire=None,
        lectures=lectures,
        rsrp_routeur_dbm=rsrp,
        snr_routeur_db=snr,
        texte_brut=text,
    )
